# -*- coding: utf-8 -*-
import datetime
import decimal
import json
import logging
import re
from collections import OrderedDict

from background_task import background
from background_task.models import Task
from background_task.signals import task_error
from django import template
from django.conf import settings
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth.models import User
from social_django.models import UserSocialAuth
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils import timezone
from django.utils import translation
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from django.utils.translation import ugettext_lazy as _
from django_comments.moderation import CommentModerator, moderator
from django_comments.signals import comment_was_posted
from pytz import utc

from socialauth.api import MediaWiki
from tracker.services import get_request
from tracker.utils import notify_on_failure
from users.models import UserWrapper

PAYMENT_STATUS_CHOICES = (
    ('n_a', _('n/a')),
    ('unpaid', _('unpaid')),
    ('partially_paid', _('partially paid')),
    ('paid', _('paid')),
    ('overpaid', _('overpaid')),
)

ACK_TYPES = (
    ('user_precontent', _('presubmitted')),
    ('precontent', _('preaccepted')),
    ('user_content', _('submitted')),
    ('content', _('accepted')),
    ('user_docs', _('expense documents submitted')),
    ('docs', _('expense documents filed')),
    ('archive', _('archived')),
    ('close', _('closed')),
)

NOTIFICATION_TYPES = [
    ('muted', _('All notifications')),
    ('comment', _('Comment added')),
    ('supervisor_notes', _('Supervisor notes changed')),
    ('ticket_new', _('New ticket was created')),
    ('ticket_delete', _('Ticket was deleted')),
    ('ack_add', _('Ack added')),
    ('ack_remove', _('Ack removed')),
    ('ticket_change', _('Ticket changed')),
    ('preexpeditures_new', _('New preexpediture was created')),
    ('preexpeditures_change', _('Preexpeditures changed')),
    ('expeditures_new', _('New expediture was created')),
    ('expeditures_change', _('Expeditures changed')),
    ('media_new', _('New media was created')),
    ('media_change', _('Media changed')),
    ('document', _('Document changed')),
]

LANGUAGE_CHOICES = settings.LANGUAGES

USER_EDITABLE_ACK_TYPES = ('user_precontent', 'user_content', 'user_docs')
WAIT_NEEDED_ACK_TYPES = ('precontent', 'content')


class ModelDiffMixin(object):
    """
    A model mixin that tracks model fields' values and provide some useful api
    to know what fields have been changed.
    Thanks to: https://stackoverflow.com/a/547714/5589365
    """

    def __init__(self, *args, **kwargs):
        super(ModelDiffMixin, self).__init__(*args, **kwargs)
        self.__initial = self._dict

    @property
    def diff(self):
        d1 = self.__initial
        d2 = self._dict
        diffs = [(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]]
        return dict(diffs)

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return self.diff.keys()

    def get_field_diff(self, field_name):
        """
        Returns a diff for field if it's changed and None otherwise.
        """
        return self.diff.get(field_name, None)

    def save(self, *args, **kwargs):
        """
        Saves model and set initial state.
        """
        super(ModelDiffMixin, self).save(*args, **kwargs)
        self.__initial = self._dict

    @property
    def _dict(self):
        return model_to_dict(self, fields=[field.name for field in
                                           self._meta.fields])


def get_user(support_none=False):
    r = get_request()
    if r is None:
        if support_none:
            return None
        else:
            return _('unknown')
    else:
        return r.user


def uber_ack(ack_type):
    """ Return 'super-ack' for given user-editable ack. """
    return {
        'user_precontent': 'precontent',
        'user_content': 'content',
        'user_docs': 'docs',
    }[ack_type]


def money(value):
    # TODO: Import this from tracker.templatetags.trackertags (Txxxxx)
    if value == 0:
        out = '0'
    else:
        out = number_format(value, 2)
    return mark_safe(u'%s&nbsp;%s' % (out, settings.TRACKER_CURRENCY))


class PercentageField(models.SmallIntegerField):
    """ Field that holds a percentage. """

    def formfield(self, **kwargs):
        defaults = {'min_value': 0, 'max_value': 100}
        defaults.update(kwargs)
        return super(PercentageField, self).formfield(**defaults)


class Model(models.Model):
    created = models.DateTimeField(_('created'), auto_now_add=True, null=True)

    class Meta:
        abstract = True


class CachedModel(Model):
    """ Model which has some values cached """

    def _get_item_key(self, name):
        return u'm:%s:%s:%s' % (self.__class__.__name__, self.id, name)

    def _get_version_key(self):
        return u'm:%s:%s:_version' % (self.__class__.__name__, self.id)

    def _cache_version(self):
        return cache.get(self._get_version_key()) or 1

    def flush_cache(self):
        cache.set(self._get_version_key(), self._cache_version() + 1)

    flush_cache.alters_data = True

    @staticmethod
    def cached_getter(raw_method):
        def wrapped(self):
            key = self._get_item_key(raw_method.__name__)
            version = self._cache_version()
            cached = cache.get(key, version=version)
            if cached is not None:
                return cached
            else:
                value = raw_method(self)
                cache.set(key, value, version=version)
                return value

        return wrapped

    class Meta:
        abstract = True


cached_getter = CachedModel.cached_getter


class DecimalRangeField(models.DecimalField):
    def __init__(self, verbose_name=None, name=None, min_value=None, max_value=None, **kwargs):
        self.min_value, self.max_value = min_value, max_value
        models.DecimalField.__init__(self, verbose_name, name, **kwargs)

    def formfield(self, **kwargs):
        defaults = {'min_value': self.min_value, 'max_value': self.max_value}
        defaults.update(kwargs)
        return super(DecimalRangeField, self).formfield(**defaults)


class Watcher(Model):
    watcher_type = models.CharField('watcher_type', max_length=50, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    watched = GenericForeignKey('content_type', 'object_id')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    notification_type = models.CharField('notification_type', max_length=50, choices=NOTIFICATION_TYPES)
    ack_type = models.CharField('ack_type', max_length=50, null=True, choices=ACK_TYPES)

    def __str__(self):
        return 'User %s is watching event %s on %s %s' % (
            self.user, self.notification_type, self.watcher_type, self.watched)


class Signature(Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    signed_ticket = models.ForeignKey('tracker.Ticket', on_delete=models.CASCADE)
    signed_text = models.TextField(_('Signed text'))


class Ticket(CachedModel, ModelDiffMixin):
    """ One unit of tracked / paid stuff. """
    updated = models.DateTimeField(_('updated'))
    media_updated = models.DateTimeField(_('media updated'), default=None, null=True, help_text=_(
        'Date when cached information about media were last updated. Used in "show media" view.'))
    event_date = models.DateField(_('event date'), blank=True, null=True,
                                  help_text=_('Date of the event this ticket is about'))
    requested_user = models.ForeignKey('auth.User', verbose_name=_('requested by'), blank=True, null=True,
                                       help_text=_('User who created/requested for this ticket'),
                                       on_delete=models.SET_NULL)
    requested_text = models.CharField(verbose_name=_('requested by (text)'), blank=True, max_length=30, help_text=_(
        'Text description of who requested for this ticket, in case user is not filled in'))
    name = models.CharField(_('name'), max_length=100, help_text=_('Name for the ticket'))
    topic = models.ForeignKey('tracker.Topic', verbose_name=_('topic'),
                              help_text=_('Project topic this ticket belongs to'), on_delete=models.CASCADE)
    subtopic = models.ForeignKey('tracker.Subtopic', blank=True, null=True, verbose_name=_('subtopic'),
                                 help_text=_('Subtopic this ticket belongs to (if you don\'t know, leave this empty)'),
                                 on_delete=models.SET_NULL)
    rating_percentage = PercentageField(_('rating percentage'), blank=True, null=True,
                                        help_text=_('Rating percentage set by topic administrator'), default=100)
    mandatory_report = models.BooleanField(_('report mandatory'), default=False, help_text=_('Is report mandatory?'))
    report_url = models.CharField(_('report url'), blank=True, max_length=255, default='', help_text=_(
        'URL to your report, if you want to report something (or if your report is mandatory per topic administrator).'))
    event_url = models.URLField(_('event url'), blank=True,
                                help_text=_('Link to a public page describing the event, if it exist'))
    description = models.TextField(_('description'), blank=True, help_text=_(
        "Space for further notes. If you're entering a trip tell us where did you go and what you did there. You can link to another tickets by adding #ticketid in your description. You may use a limited subset of HTML."))
    supervisor_notes = models.TextField(_('supervisor notes'), blank=True, help_text=_(
        "This space is for notes of project supervisors and accounting staff."))
    deposit = DecimalRangeField(_('deposit'), default=0, min_value=0,
                                decimal_places=2, max_digits=8,
                                help_text=_(
                                    "If you are requesting a financial deposit, please fill here its amount. Maximum amount is sum of preexpeditures. If you aren't requesting a deposit, fill here 0."))
    cluster = models.ForeignKey('Cluster', blank=True, null=True, on_delete=models.SET_NULL)
    payment_status = models.CharField(_('payment status'), max_length=20, default='n/a', choices=PAYMENT_STATUS_CHOICES)
    imported = models.BooleanField(_('imported'), default=False,
                                   help_text=_('Was this ticket imported from older Tracker version?'))
    enable_comments = models.BooleanField(_('enable comments'), default=True,
                                          help_text=_('Can users comment on this ticket?'))
    car_travel = models.BooleanField(_('Did you travel by car?'), default=False,
                                     help_text=_('Do you request reimbursement of car-type travel expense?'))
    is_completed = models.BooleanField(_('Is this ticket completed?'), default=False)

    @staticmethod
    def currency():
        return settings.TRACKER_CURRENCY

    def update_payment_status(self, save_afterwards=True):
        paid_len = len(self.expediture_set.filter(paid=True))
        all_len = len(self.expediture_set.all())

        if all_len == 0:
            self.payment_status = 'n/a'
        elif paid_len == 0 and all_len > 0:
            self.payment_status = 'unpaid'
        elif paid_len < all_len:
            self.payment_status = 'partially_paid'
        elif paid_len == all_len:
            self.payment_status = 'paid'

        if save_afterwards:
            self.save(just_payment_status=True)

    update_payment_status.alters_data = True

    def save(self, *args, **kwargs):
        saved_from_admin = kwargs.pop('saved_from_admin', False)
        just_payment_status = kwargs.pop('just_payment_status', False)
        if self.has_changed and get_request() and not saved_from_admin and not just_payment_status:
            change_message = 'Changed ' + ', '.join(self.changed_fields) + "."
            ct = ContentType.objects.get_for_model(self)
            LogEntry.objects.log_action(
                user_id=get_request().user.id,
                content_type_id=ct.pk,
                object_id=self.pk,
                object_repr=force_text(self),
                action_flag=CHANGE,
                change_message=change_message
            )

        statutory_declaration_diff = self.get_field_diff('statutory_declaration')
        if statutory_declaration_diff and not statutory_declaration_diff[0] and statutory_declaration_diff[1]:
            self.statutory_declaration_date = datetime.datetime.now()  # the statutory declaration was made, store when this happened
        elif statutory_declaration_diff and statutory_declaration_diff[0] and not statutory_declaration_diff[1]:
            self.statutory_declaration_date = None  # the statutory declaration was revoked, clear the date field

        if not self.car_travel:
            self.statutory_declaration = False

        if not just_payment_status:
            self.updated = datetime.datetime.now(tz=utc)

        if self.event_date is None:
            self.event_date = datetime.date.today()

        if not just_payment_status:
            self.update_payment_status(save_afterwards=False)

        acks = self.ack_set()
        self.is_completed = ('archive' in acks) or ('close' in acks)

        super(Ticket, self).save(*args, **kwargs)

        self.flush_cache()

    def _note_comment(self, **kwargs):
        self.save()

    @staticmethod
    def get_tickets_with_state(state):
        tickets = Ticket.objects.all()
        result = []
        for ticket in tickets:
            if ticket.state_str() == state:
                result.append(ticket)
        return result

    def admin_topic(self):
        return '%s (%s)' % (self.topic, self.topic.grant)

    def is_concept(self):
        return len(self.ack_set()) == 0

    def state_str(self):
        if self.imported:
            return _('historical')

        acks = self.ack_set()
        if 'close' in acks:
            return _('closed')
        elif 'archive' in acks:
            return _('archived')
        elif 'content' in acks:
            if not self.rating_percentage:
                return _('waiting for content rating')

            if 'docs' in acks:
                return _('complete')
            elif 'user_docs' in acks:
                return _('waiting for filing of documents')
            else:
                return _('waiting for document submission')
        elif 'precontent' in acks:
            if 'user_content' in acks:
                return _('waiting for approval')
            else:
                return _('waiting for submitting')
        else:
            if 'user_precontent' in acks:
                return _('waiting for preapproval')
            elif 'user_content' in acks:
                return _('waiting for approval')
            else:
                return _('draft')

    state_str.admin_order_field = 'state'
    state_str.short_description = _('state')

    def __str__(self):
        return '%s: %s' % (self.id, self.name)

    @cached_getter
    def requested_by(self):
        if self.requested_user is not None:
            return self.requested_user.username
        else:
            return self.requested_text

    requested_by.short_description = _('requested by')

    def requested_by_html(self):
        if self.requested_user is not None:
            return UserWrapper(self.requested_user).get_html_link()
        else:
            return escape(self.requested_text)

    @cached_getter
    def requested_user_details(self):
        if self.requested_user is not None:
            out = u'%s: %s<br />%s: %s' % (
                _('E-mail'), escape(self.requested_user.email),
                _('Other contact'), escape(self.requested_user.trackerprofile.other_contact),
            )
            return mark_safe(out)
        else:
            return _('no tracker account listed')

    requested_user_details.short_description = _('Requester details')

    def get_absolute_url(self):
        return reverse('ticket_detail', kwargs={'pk': self.id})

    @cached_getter
    def media_count(self):
        return (self.mediainfoold_set.aggregate(media=models.Sum('count'))['media'] or 0) + self.mediainfo_set.count()

    @cached_getter
    def media_old_count(self):
        return self.mediainfoold_set.aggregate(objects=models.Count('id'), media=models.Sum('count'))

    def expeditures_amount(self):
        return self.expeditures()['amount'] or 0

    def preexpeditures_amount(self):
        return self.preexpeditures()['amount'] or 0

    @cached_getter
    def expeditures(self):
        return self.expediture_set.aggregate(count=models.Count('id'), amount=models.Sum('amount'))

    @cached_getter
    def preexpeditures(self):
        return self.preexpediture_set.aggregate(count=models.Count('id'), amount=models.Sum('amount'))

    @cached_getter
    def accepted_expeditures(self):
        if not self.has_all_acks('content') or (self.rating_percentage is None):
            return decimal.Decimal(0)
        else:
            total = sum([x.amount for x in self.expediture_set.all()], decimal.Decimal(0))
            reduced = total * self.rating_percentage / 100
            return reduced.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)

    @cached_getter
    def paid_expeditures(self):
        if self.rating_percentage is None:
            return decimal.Decimal(0)
        else:
            total = sum([x.amount for x in self.expediture_set.filter(paid=True)], decimal.Decimal(0))
            reduced = total * self.rating_percentage / 100
            return reduced.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)

    def watches(self, user, event):
        """Watches given user this ticket?"""
        if self.topic.watches(user, event) and not Watcher.objects.filter(watcher_type='Ticket', object_id=self.id,
                                                                          user=user).exists():
            return True
        if user.is_authenticated and Watcher.objects.filter(watcher_type='Ticket', object_id=self.id, user=user,
                                                            notification_type=event).exists():
            return True
        return False

    def is_editable(self, user=None):
        """Is this ticket editable through a non-admin interface?"""
        acks = self.ack_set()
        if user is not None and user.has_perm('tracker.change_ticket'):
            return True
        return ('archive' not in acks) and ('close' not in acks) and user.is_authenticated

    def can_edit(self, user):
        """ Can given user edit this ticket through a non-admin interface? """
        return self.is_editable(user) and (user == self.requested_user)

    def can_see_all_documents(self, user):
        """ Can given user see documents belonging to this ticket? """
        return (user == self.requested_user) or user.has_perm('tracker.see_all_docs') or user.has_perm(
            'tracker.edit_all_docs')

    def can_edit_documents(self, user):
        """ Can given user edit documents belonging to this ticket? """
        return (user == self.requested_user) or user.has_perm('tracker.edit_all_docs')

    def can_see_comments(self, user):
        return self.topic.ticket_comments_public or self.can_always_see_comments(user)

    def can_always_see_comments(self, user):
        return user.is_authenticated and (
            (user == self.requested_user) or user.has_perm('tracker.change_ticket') or user.trackerprofile.is_socialauth_connected('chapterwiki')
        )

    def can_copy_preexpeditures(self, user):
        return self.can_edit(user) and 'content' not in self.ack_set()

    @cached_getter
    def associated_transactions_total(self):
        return self.transaction_set.all().aggregate(amount=models.Sum('amount'))['amount']

    @cached_getter
    def ack_set(self):
        return set([x.ack_type for x in self.ticketack_set.only('ack_type')])

    def has_ack(self, ack_type):
        return ack_type in self.ack_set()

    def has_all_acks(self, *wanted_acks):
        acks = self.ack_set()
        for wanted in wanted_acks:
            if wanted not in acks:
                return False
        return True

    def add_acks(self, *acks):
        """ Adds acks, mostly for testing. """
        for ack in acks:
            self.ticketack_set.create(ack_type=ack, comment='system operation')
        self.flush_cache()

    @cached_getter
    def possible_user_ack_types(self):
        """ List of possible ack types, that can be added by ticket requester. """
        out = []
        for ack_type in USER_EDITABLE_ACK_TYPES:
            if not self.has_ack(ack_type) and not self.has_ack(uber_ack(ack_type)):
                out.append(ack_type)
        return out

    @cached_getter
    def possible_user_acks(self):
        """ List of PossibleAck objects, that can be added by ticket requester. """
        return [PossibleAck(ack_type) for ack_type in self.possible_user_ack_types()]

    @staticmethod
    @background(schedule=10)
    def update_media(ticket_id):
        ticket = Ticket.objects.get(id=ticket_id)
        for media in ticket.mediainfo_set.all():
            media.store_mediawiki_data_internal()
        ticket.media_updated = datetime.datetime.now(tz=utc)
        ticket.save()

    def get_cached_ticket(self):
        subtopic = self.subtopic
        if subtopic:
            subtopic = '<a href="%s">%s</a>' % (self.subtopic.get_absolute_url(), self.subtopic)
        else:
            subtopic = ''
        return [
            '<a href="%s">%s</a>' % (self.get_absolute_url(), self.pk),
            str(self.event_date),
            '<a class="ticket-summary" href="%s">%s</a>' % (self.get_absolute_url(), escape(self.name)),
            '<a href="%s">%s</a>' % (self.topic.grant.get_absolute_url(), str(self.topic.grant)),
            '<a href="%s">%s</a>' % (self.topic.get_absolute_url(), str(self.topic)),
            str(subtopic),
            self.requested_by_html(),
            money(self.preexpeditures()['amount'] or 0),
            money(self.expeditures()['amount'] or 0),
            money(self.accepted_expeditures()),
            money(self.paid_expeditures()),
            str(self.state_str()),
            str(self.updated),
        ]

    def photos_per_category(self):
        photos_per_category = {}
        for m in self.mediainfo_set.all():
            for category in m.mediainfocategory_set.all():
                if category.title in photos_per_category:
                    photos_per_category[category.title] += 1
                else:
                    photos_per_category[category.title] = 1
        return OrderedDict(sorted(photos_per_category.items(), key=lambda t: t[1], reverse=True))

    def flush_cache(self):
        super(Ticket, self).flush_cache()
        self.topic.flush_cache()

    def can_ack_be_added(self, ack):
        """
        A waiting period (defined in settings.py under TRACKER_MIN_WAIT_DAYS) must pass before
        certain acks (defined here as WAIT_NEEDED_ACK_TYPES) can be added. This period
        shall be counted when adding that ack is requested. This method calculates if
        such ack can be added, so this policy is satisfied.
        """
        if ack not in WAIT_NEEDED_ACK_TYPES:
            return True

        acks = self.ack_set()
        if ack == "precontent" and "content" in acks:
            return False  # HACK: To not include approved tickets that are "waiting for preapproval"

        not_archived = ('archive' not in acks) and ('close' not in acks)
        not_added = ack not in acks

        user_ack = self.ticketack_set.filter(ack_type='user_%s' % ack)
        if user_ack.exists():
            user_ack = user_ack[0]
        else:
            return False

        can_be_added_on = user_ack.added + datetime.timedelta(days=settings.TRACKER_MIN_WAIT_DAYS)

        return not_archived and not_added and timezone.now() > can_be_added_on

    class Meta:
        verbose_name = _('Ticket')
        verbose_name_plural = _('Tickets')
        ordering = ['-id']


class TicketModerator(CommentModerator):
    enable_field = 'enable_comments'

    def allow(self, comment, content_object, request):
        is_allowed = super(TicketModerator, self).allow(comment, content_object, request)
        if not is_allowed:
            if request.user.has_perm("tracker.bypass_disabled_comments"):
                is_allowed = True
        return is_allowed


moderator.register(Ticket, TicketModerator)


class FinanceStatus(object):
    """ This is not a model, but rather a representation of topic finance status. """

    def __init__(self, fuzzy=False, unpaid=0, paid=0, overpaid=0):
        self.fuzzy = fuzzy
        # we set fuzzy flag if there is partially paid/overpaid cluster that involves more tickets
        # and hence our sums may not make much sense

        self.unpaid = unpaid
        self.paid = paid
        self.overpaid = overpaid

        self.seen_cluster_ids = set()

    def __repr__(self):
        return 'FinanceStatus(fuzzy=%s, unpaid=%s, paid=%s, overpaid=%s)' % (
            self.fuzzy, self.unpaid, self.paid, self.overpaid)

    def _equals(self, other):
        return self.fuzzy == other.fuzzy and self.unpaid == other.unpaid and self.paid == other.paid and self.overpaid == other.overpaid

    def __eq__(self, other):
        try:
            return self._equals(other)
        except AttributeError:
            return NotImplemented

    def __ne__(self, other):
        try:
            return not self._equals(other)
        except AttributeError:
            return NotImplemented

    def add_ticket(self, ticket):
        if ticket.payment_status == 'unpaid':
            self.unpaid += ticket.accepted_expeditures()
        elif ticket.payment_status == 'paid':
            self.paid += ticket.accepted_expeditures()
        elif ticket.payment_status == 'partially_paid':
            self.paid += sum([e.amount for e in Expediture.objects.filter(ticket_id=ticket.id,
                                                                          paid=True)]) * ticket.rating_percentage / 100
            self.unpaid += sum([e.amount for e in Expediture.objects.filter(ticket_id=ticket.id,
                                                                            paid=False)]) * ticket.rating_percentage / 100

    def add_finance(self, other):
        self.fuzzy = self.fuzzy or other.fuzzy
        self.unpaid += decimal.Decimal(other.unpaid)
        self.paid += other.paid
        self.overpaid += other.overpaid
        self.seen_cluster_ids = self.seen_cluster_ids.union(other.seen_cluster_ids)

    def as_dict(self):
        return {'fuzzy': self.fuzzy, 'unpaid': self.unpaid, 'paid': self.paid, 'overpaid': self.overpaid}


class Subtopic(CachedModel):
    name = models.CharField(_('name'), max_length=80)
    description = models.TextField(_('description'), blank=True,
                                   help_text=_('Description shown to users who enter tickets for this subtopic'))
    form_description = models.TextField(_('form description'), blank=True,
                                        help_text=_('Description shown to users who enter tickets for this subtopic'))
    topic = models.ForeignKey('tracker.Topic', verbose_name=_('topic'),
                              help_text=_('Topic where this subtopic belongs'), on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('subtopic_detail', kwargs={'pk': self.id})

    @cached_getter
    def media_count(self):
        return sum([len(t.mediainfo_set.all()) for t in self.ticket_set.all()])

    @cached_getter
    def expeditures(self):
        return Expediture.objects.extra(where=['ticket_id in (select id from tracker_ticket where subtopic_id = %s)'],
                                        params=[self.id]).aggregate(count=models.Count('id'),
                                                                    amount=models.Sum('amount'))

    @cached_getter
    def preexpeditures(self):
        return Preexpediture.objects.extra(
            where=['ticket_id in (select id from tracker_ticket where subtopic_id = %s)'], params=[self.id]).aggregate(
            count=models.Count('id'), amount=models.Sum('amount'))

    @cached_getter
    def accepted_expeditures(self):
        return sum([t.accepted_expeditures() for t in self.ticket_set.filter(rating_percentage__gt=0)])

    @cached_getter
    def tickets_per_payment_status(self):
        out = {}
        tickets = self.ticket_set.order_by()  # remove default ordering as it b0rks our aggregation
        for s in tickets.values('payment_status').annotate(models.Count('payment_status')):
            out[s['payment_status']] = s['payment_status__count']
        return out

    @cached_getter
    def paid_wages(self):
        tosum = []
        for ticket in self.ticket_set.filter(id__gt=0):
            ticketsum = []
            for expediture in ticket.expediture_set.filter(wage=True, paid=True):
                ticketsum.append(expediture.amount)
            if ticket.rating_percentage:
                tosum.append(sum(ticketsum) * ticket.rating_percentage / 100)
        return sum(tosum)

    @cached_getter
    def paid_together(self):
        tosum = []
        for ticket in self.ticket_set.filter(id__gt=0):
            ticketsum = []
            for expediture in ticket.expediture_set.filter(paid=True):
                ticketsum.append(expediture.amount)
            if ticket.rating_percentage:
                tosum.append(decimal.Decimal(sum(ticketsum)) * ticket.rating_percentage / 100)
        return sum(tosum)

    class Meta:
        verbose_name = _('Subtopic')
        verbose_name_plural = _('Subtopics')
        ordering = ['name']


class Topic(CachedModel):
    """ Topics according to which the tickets are grouped. """
    name = models.CharField(_('name'), max_length=80)
    grant = models.ForeignKey('tracker.Grant', verbose_name=_('grant'),
                              help_text=_('Grant project where this topic belongs'), on_delete=models.CASCADE)
    open_for_tickets = models.BooleanField(_('open for tickets'), default=True,
                                           help_text=_('Is this topic open for ticket submissions from users?'))
    ticket_media = models.BooleanField(_('ticket media'), default=True,
                                       help_text=_('Does this topic track ticket media items?'))
    ticket_expenses = models.BooleanField(_('ticket expenses'), default=True,
                                          help_text=_('Does this topic track ticket expenses?'))
    ticket_preexpenses = models.BooleanField(_('ticket preexpenses'), default=True,
                                             help_text=_('Does this topic track preexpenses?'))
    ticket_statutory_declaration = models.BooleanField(_('require statutory declaration'), default=False, help_text=_(
        'Does this topic require statutory declaration for car travelling?'))
    ticket_comments_public = models.BooleanField(_('make comments public'), default=True, help_text=_(
        'Are comments under tickets public?'
    ))
    description = models.TextField(_('description'), blank=True, help_text=_(
        'Detailed description; HTML is allowed for now, line breaks are auto-parsed'))
    form_description = models.TextField(_('form description'), blank=True,
                                        help_text=_('Description shown to users who enter tickets for this topic'))
    admin = models.ManyToManyField('auth.User', verbose_name=_('topic administrator'), blank=True,
                                   help_text=_('Selected users will have administration access to this topic.'))

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('topic_detail', kwargs={'pk': self.id})

    @cached_getter
    def media_count(self):
        return sum([len(t.mediainfo_set.all()) for t in self.ticket_set.all()]) + (MediaInfoOld.objects.extra(
            where=['ticket_id in (select id from tracker_ticket where topic_id = %s)'], params=[self.id]).aggregate(
            objects=models.Count('id'), media=models.Sum('count'))['media'] or 0)

    @cached_getter
    def expeditures(self):
        return Expediture.objects.extra(where=['ticket_id in (select id from tracker_ticket where topic_id = %s)'],
                                        params=[self.id]).aggregate(count=models.Count('id'),
                                                                    amount=models.Sum('amount'))

    @cached_getter
    def preexpeditures(self):
        return Preexpediture.objects.extra(where=['ticket_id in (select id from tracker_ticket where topic_id = %s)'],
                                           params=[self.id]).aggregate(count=models.Count('id'),
                                                                       amount=models.Sum('amount'))

    @cached_getter
    def accepted_expeditures(self):
        return sum([t.accepted_expeditures() for t in self.ticket_set.filter(rating_percentage__gt=0)])

    @cached_getter
    def tickets_per_payment_status(self):
        out = {}
        tickets = self.ticket_set.order_by()  # remove default ordering as it b0rks our aggregation
        for s in tickets.values('payment_status').annotate(models.Count('payment_status')):
            out[s['payment_status']] = s['payment_status__count']
        return out

    @cached_getter
    def paid_wages(self):
        tosum = []
        for ticket in self.ticket_set.filter(id__gt=0):
            ticketsum = []
            for expediture in ticket.expediture_set.filter(wage=True, paid=True):
                ticketsum.append(expediture.amount)
            if ticket.rating_percentage:
                tosum.append(decimal.Decimal(sum(ticketsum) * ticket.rating_percentage / 100))
        return sum(tosum)

    @cached_getter
    def paid_together(self):
        return sum([t.paid_expeditures() for t in self.ticket_set.all()])

    @cached_getter
    def payment_summary(self):
        finance = FinanceStatus()
        for ticket in self.ticket_set.all():
            finance.add_ticket(ticket)

        return finance

    def watches(self, user, event):
        """Watches given user this topic?"""
        return self.grant.watches(user, event) or (user.is_authenticated and len(
            Watcher.objects.filter(watcher_type='Topic', object_id=self.id, user=user, notification_type=event)) > 0)

    class Meta:
        verbose_name = _('Topic')
        verbose_name_plural = _('Topics')
        ordering = ['-open_for_tickets', 'name']
        permissions = (
            ("supervisor", "Can edit all topics and tickets"),
        )


class Grant(CachedModel):
    """ Grant is the bigger thing above topics """
    full_name = models.CharField(_('full name'), max_length=80, help_text=_('Full name for headlines and such'))
    short_name = models.CharField(_('short name'), max_length=16, help_text=_('Shorter name for use in tables'))
    slug = models.SlugField(_('slug'), help_text=_('Shortcut for usage in URLs'), unique=True)
    description = models.TextField(_('description'), blank=True, help_text=_(
        'Detailed description; HTML is allowed for now, line breaks are auto-parsed'))

    def __str__(self):
        return self.full_name

    def open_for_tickets(self):
        return len(self.topic_set.filter(open_for_tickets=True)) != 0

    open_for_tickets.boolean = True

    def get_absolute_url(self):
        return reverse('grant_detail', kwargs={'slug': self.slug})

    def watches(self, user, event):
        """Watches given user this grant?"""
        return user.is_authenticated and len(
            Watcher.objects.filter(watcher_type='Grant', object_id=self.id, user=user, notification_type=event)) > 0

    @cached_getter
    def total_tickets(self):
        return sum([x.ticket_set.count() for x in self.topic_set.all()])

    @cached_getter
    def total_paid_wages(self):
        return sum([x.paid_wages() for x in self.topic_set.all()])

    @cached_getter
    def total_paid_together(self):
        return sum([x.paid_together() for x in self.topic_set.all()])

    @cached_getter
    def tickets_per_payment_status(self):
        out = {}
        for topic in self.topic_set.all():
            tickets = topic.ticket_set.order_by()  # remove default ordering as it b0rks our aggregation
            for s in tickets.values('payment_status').annotate(models.Count('payment_status')):
                out[s['payment_status']] = s['payment_status__count']
        return out

    class Meta:
        verbose_name = _('Grant')
        verbose_name_plural = _('Grants')
        ordering = ['full_name']


@receiver(comment_was_posted)
def ticket_note_comment(sender, comment, **kwargs):
    obj = comment.content_object
    if type(obj) == Ticket:
        obj.save()


class MediaInfoOld(Model):
    """ Media related to particular tickets. """
    ticket = models.ForeignKey('tracker.Ticket', verbose_name=_('ticket'),
                               help_text=_('Ticket this media info belongs to'), on_delete=models.CASCADE)
    description = models.CharField(_('description'), max_length=255, help_text=_('Item description to show'))
    url = models.URLField(_('URL'), blank=True, help_text=_('Link to media files'))
    count = models.PositiveIntegerField(_('count'), blank=True, null=True, help_text=_('Number of files'))

    def __str__(self):
        return self.description

    class Meta:
        verbose_name = _('Ticket media')
        verbose_name_plural = _('Ticket media')


class MediaInfoUsage(models.Model):
    mediainfo = models.ForeignKey('tracker.MediaInfo', on_delete=models.CASCADE)
    url = models.URLField(_('URL'), help_text=_('Link to file usage'), max_length=512)
    title = models.CharField(_('title'), max_length=255)
    project = models.CharField(_('project'), max_length=255)


class MediaInfoCategory(models.Model):
    mediainfo = models.ForeignKey('tracker.MediaInfo', on_delete=models.CASCADE)
    title = models.CharField(_('title'), max_length=255)


class MediaInfo(Model):
    """ Media related to particular tickets. """
    ticket = models.ForeignKey('tracker.Ticket', verbose_name=_('ticket'),
                               help_text=_('Ticket this media info belongs to'), on_delete=models.CASCADE)
    page_title = models.CharField(_('cannonical title'), max_length=255, null=True)
    page_id = models.IntegerField(_('page id'), null=True)
    width = models.IntegerField(_('width'), null=True)
    height = models.IntegerField(_('height'), null=True)
    thumb_url = models.URLField(_('URL'), max_length=500, null=True, blank=True)

    @property
    def media_id(self):
        if not self.page_id:
            mw = MediaWiki(user=None)
            data = mw.request({
                "action": "query",
                "format": "json",
                "titles": self.page_title
            }).json()
            self.page_id = int(list(data['query']['pages'].keys())[0])
            self.save()
        return self.page_id

    @cached_property
    def _as_str(self):
        if self.page_title == '' or self.page_title is None:
            mw = MediaWiki(user=None)
            data = mw.request({
                "action": "query",
                "format": "json",
                "pageids": [self.media_id]
            }).json()
            try:
                self.page_title = data['query']['pages'][list(data['query']['pages'].keys())[0]]['title']
            except KeyError:
                self.page_title = ''
            self.save()
        return self.page_title

    def __str__(self):
        return self._as_str

    @staticmethod
    def strip_template(text):
        # TODO: First letter of template should be case-insensitive
        regex = r"\n?{{" + settings.MEDIAINFO_MEDIAWIKI_TEMPLATE + r"[^}]*}}"
        return re.sub(regex, "", text)

    @staticmethod
    def get_template_end_position(text, template):
        # TODO: First letter of template should be case-insensitive
        opening_tag = "{{" + template
        if opening_tag not in text:
            return -1

        position = text.find(opening_tag)
        open_brackets = 0

        for idx in range(position, len(text) - 1):
            if text[idx] == '{':
                open_brackets += 1
            elif text[idx] == '}':
                open_brackets -= 1
            if open_brackets == 0:
                return idx + 1

        return -1

    @staticmethod
    @background(schedule=10)
    def remove_from_mediawiki(media_id, user_id):
        try:
            mw = MediaWiki(User.objects.get(id=user_id), settings.MEDIAINFO_MEDIAWIKI_API)
        except User.DoesNotExist:
            return
        logging.getLogger(__name__).info('Removing MediaInfo %d from MediaWiki by user %d' % (media_id, user_id))
        try:
            mw.put_content(media_id, MediaInfo.strip_template(mw.get_content(media_id)), minor=True)
        except ValueError:
            # the edited page doesn't exist, ignore
            pass

    @staticmethod
    @background(schedule=10)
    def add_to_mediawiki(media_id, user_id):
        try:
            media = MediaInfo.objects.get(id=media_id)
        except MediaInfo.DoesNotExist:
            return
        parameters_unsorted = {
            'rok': datetime.date.today().year,
            'podtéma': media.ticket.subtopic or '',
            'tiket': media.ticket.id,
        }
        if media.created is not None:
            parameters_unsorted['rok'] = media.created.year
        parameters = OrderedDict(sorted(parameters_unsorted.items(), key=lambda t: t[0]))

        template = '{{%s' % settings.MEDIAINFO_MEDIAWIKI_TEMPLATE
        for param in parameters:
            template += "|%s=%s" % (param, str(parameters[param]))
        template += '}}'

        try:
            mw = MediaWiki(User.objects.get(id=user_id), settings.MEDIAINFO_MEDIAWIKI_API)
        except User.DoesNotExist:
            return

        old = mw.get_content(media.page_id)
        if old is None:
            return

        if template not in old:
            logging.getLogger(__name__).info('Adding MediaInfo %d from MediaWiki by user %d' % (media_id, user_id))

            old = MediaInfo.strip_template(old)
            insert_to = MediaInfo.get_template_end_position(old, settings.MEDIAINFO_MEDIAWIKI_INFO_TEMPLATE)

            if insert_to != -1:
                new = old[:insert_to] + u"\n" + template + old[insert_to:]
                mw.put_content(media.page_id, new)
                return

            mw.put_content(media.page_id, old + u"\n" + template, minor=True)

    def mediawiki_link(self):
        return settings.MEDIAINFO_MEDIAWIKI_ARTICLE + str(self)

    def get_mediawiki_data(self, width=None):
        if settings.MEDIAINFO_MEDIAWIKI_API:
            mw = MediaWiki(user=None)
            data = mw.request({
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "prop": "imageinfo|categories|globalusage",
                "pageids": [self.media_id],
                "iiprop": "dimensions|url|canonicaltitle",
                "iiurlwidth": width,
                "clprop": "hidden",
            }).json()['query']['pages'][0]
            imagedata = data['imageinfo'][0]

            if width:
                url = imagedata['thumburl']
            else:
                url = imagedata['url']

            return {
                "url": url,
                "page_title": imagedata['canonicaltitle'],
                'width': imagedata['width'],
                'height': imagedata['height'],
                'categories': data.get('categories', []),
                'globalusage': data.get("globalusage", [])
            }

    def store_mediawiki_data_internal(self):
        data = self.get_mediawiki_data(width=200)

        self.thumb_url = data['url']
        self.page_title = data['page_title']
        self.width = data.get('width')
        self.height = data.get('height')

        self.mediainfocategory_set.all().delete()
        for category in data.get("categories", []):
            if "hidden" not in category:
                MediaInfoCategory.objects.create(mediainfo=self, title=category['title'])

        self.mediainfousage_set.all().delete()
        for usage in data.get("globalusage", []):
            MediaInfoUsage.objects.create(
                mediainfo=self,
                url=usage["url"],
                title=usage["title"],
                project=usage["wiki"]
            )

        self.save(no_update=True)

    @staticmethod
    @background(schedule=10)
    def store_mediawiki_data(media_id):
        media = MediaInfo.objects.get(id=media_id)
        media.store_mediawiki_data_internal()

    def save(self, no_update=False, *args, **kwargs):
        if MediaInfo.objects.filter(ticket_id=self.ticket_id, page_title=self.page_title, page_id=self.page_id).exclude(id=self.id).exists():
            # we found a duplicate, self destruct instead
            self.delete()
            return

        super(MediaInfo, self).save(*args, **kwargs)

        if get_request() and settings.MEDIAINFO_MEDIAWIKI_TEMPLATE and not no_update:
            logging.getLogger(__name__).info('Scheduling adding MediaInfo %d' % self.id)
            MediaInfo.add_to_mediawiki(self.id, get_request().user.id)

        if not no_update:
            MediaInfo.store_mediawiki_data(self.id)
            if not Task.objects.filter(task_name="tracker.models.update_media",
                                       task_params="[[%s], {}]" % self.ticket.id).exists():
                Ticket.update_media(self.ticket.id)

    class Meta:
        verbose_name = _('Ticket media')
        verbose_name_plural = _('Ticket media')
        unique_together = ('page_title', 'ticket_id')


task_error.connect(notify_on_failure)


@receiver(pre_save, sender=MediaInfo)
def save_page_id(sender, instance, **kwargs):
    # Same as MediaInfo.media_id
    if not instance.page_id:
        mw = MediaWiki(user=None)
        data = mw.request({
            "action": "query",
            "format": "json",
            "titles": instance.page_title
        }).json()
        instance.page_id = int(list(data['query']['pages'].keys())[0])


@receiver(post_delete, sender=MediaInfo)
def delete_mediainfo(sender, instance, **kwargs):
    if get_request() and settings.MEDIAINFO_MEDIAWIKI_TEMPLATE:
        MediaInfo.remove_from_mediawiki(instance.media_id, get_request().user.id)


class Expediture(Model):
    """ Expenses related to particular tickets. """
    ticket = models.ForeignKey('tracker.Ticket', verbose_name=_('ticket'),
                               help_text=_('Ticket this expediture belongs to'), on_delete=models.CASCADE)
    description = models.CharField(_('description'), max_length=255, help_text=_('Description of this expediture'))
    amount = models.DecimalField(_('amount'), max_digits=8, decimal_places=2,
                                 help_text=format_lazy("{} {}", _('Expediture amount in'), settings.TRACKER_CURRENCY))
    accounting_info = models.CharField(_('accounting info'), max_length=255, blank=True,
                                       help_text=_('Accounting info, this is editable only through admin field'))
    paid = models.BooleanField(_('paid'), default=False)
    wage = models.BooleanField(_('wage'), default=False)

    def __str__(self):
        return _('%(description)s (%(amount)s %(currency)s)') % {'description': self.description, 'amount': self.amount,
                                                                 'currency': settings.TRACKER_CURRENCY}

    def save(self, *args, **kwargs):
        super(Expediture, self).save(*args, **kwargs)
        if self.ticket.id is not None:
            self.ticket.update_payment_status()

    class Meta:
        verbose_name = _('Ticket expediture')
        verbose_name_plural = _('Ticket expeditures')


class Preexpediture(Model):
    """Preexpeditures related to particular tickets. """
    ticket = models.ForeignKey('tracker.Ticket', verbose_name=_('ticket'),
                               help_text=_('Ticket this preexpediture belongs to'), on_delete=models.CASCADE)
    description = models.CharField(_('description'), max_length=255, help_text=_('Description of this preexpediture'))
    amount = models.DecimalField(_('amount'), max_digits=8, decimal_places=2,
                                 help_text=format_lazy("{} {}", _('Preexpediture amount in'), settings.TRACKER_CURRENCY))
    wage = models.BooleanField(_('wage'), default=False)

    def __str__(self):
        return _('%(description)s (%(amount)s %(currency)s)') % {'description': self.description, 'amount': self.amount,
                                                                 'currency': settings.TRACKER_CURRENCY}

    class Meta:
        verbose_name = _('Ticket preexpediture')
        verbose_name_plural = _('Ticket preexpeditures')


# introductory chunk for the template
_('uploader')  # FIXME: Workaround to make Django know "uploader" as localizable string
DOCUMENT_INTRO_TEMPLATE = template.Template(
    '{% load i18n %}<a href="{% url "download_document" doc.ticket.id doc.filename %}">{{doc.filename}}</a> {% if detail and doc.description %}: {{doc.description}}; {% endif %}{% if doc.uploader %}{% trans "uploader" %}: {{doc.uploader}}{% endif %} <small>({{doc.content_type}}; {{doc.size|filesizeformat}})</small>')


class Document(Model):
    """ Document related to particular ticket, not publicly accessible. """
    ticket = models.ForeignKey('tracker.Ticket', on_delete=models.CASCADE)
    filename = models.CharField(max_length=120, help_text='Document filename', validators=[
        RegexValidator(r'^[-_\.A-Za-z0-9]+\.[A-Za-z0-9]+$',
                       message=_(u'We need a sane file name, such as my-invoice123.jpg')),
    ])
    size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, help_text='Optional further description of the document')
    payload = models.FileField(upload_to='tickets/%Y/', storage=FileSystemStorage(location=settings.TRACKER_DOCS_ROOT))
    uploader = models.ForeignKey('auth.User', null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.filename

    def inline_intro(self):
        try:
            context = template.Context({'doc': self})
            return DOCUMENT_INTRO_TEMPLATE.render(context)
        except NoReverseMatch:
            return self.filename

    def html_item(self):
        context = template.Context({'doc': self, 'detail': True})
        return DOCUMENT_INTRO_TEMPLATE.render(context)

    def save(self, *args, **kwargs):
        request = get_request()
        if request:
            self.uploader = request.user
        else:
            self.uploader = None

        super(Document, self).save(*args, **kwargs)

    class Meta:
        # by default, everyone can see and edit documents that belong to his tickets
        permissions = (
            ("see_all_docs", "Can see all documents"),
            ("edit_all_docs", "Can edit all documents"),
        )


class TrackerPreferences(models.Model):
    user = models.OneToOneField(User, null=True, on_delete=models.CASCADE)
    muted_ack = models.CharField(_('Ignored acks'), max_length=300, blank=True)
    muted_notifications = models.CharField(_('Muted notifications'), max_length=300, blank=True)
    email_language = models.CharField(_('Email language'), max_length=7, blank=False, default="cs",
                                      choices=LANGUAGE_CHOICES)
    display_items = models.IntegerField(_('Display items'),
                                        help_text=_('How many items should we display in tables at once'), default=25)

    def get_muted_notifications(self):
        if self.muted_notifications == '':
            return []
        res = []
        for muted_notification in json.loads(self.muted_notifications):
            res.append(muted_notification)
        return res

    def get_muted_ack(self):
        if self.muted_ack == '':
            return []
        res = []
        for muted_ack in json.loads(self.muted_ack):
            res.append(muted_ack)
        return res

    class Meta:
        verbose_name = _('Tracker user preference')
        verbose_name_plural = _('Tracker user preferences')


class TrackerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    mediawiki_username = models.CharField(_('Username on mediawiki'), max_length=120, blank=True)
    chapter_username = models.CharField(_('Chapter-issued username'), max_length=120, blank=True)
    bank_account = models.CharField(_('Bank account'), max_length=120, blank=True,
                                    help_text=_('Bank account information for money transfers'))
    other_contact = models.CharField(_('Other contact'), max_length=120, blank=True, help_text=_(
        'Other contact such as wiki account; can be useful in case of topic administrators need to clarify some information'))
    other_identification = models.CharField(_('Other identification'), max_length=120, blank=True, help_text=_(
        'Address, or other identification information, so we know who are we sending money to'))

    def get_absolute_url(self):
        return reverse('user_detail', kwargs={'username': self.user.username})

    def media_count(self):
        return sum([len(t.mediainfo_set.all()) for t in self.user.ticket_set.all()]) + (MediaInfoOld.objects.extra(
            where=['ticket_id in (select id from tracker_ticket where requested_user_id = %s)'],
            params=[self.user.id]).aggregate(media=models.Sum('count'))['media'] or 0)

    def accepted_expeditures(self):
        return sum([t.accepted_expeditures() for t in self.user.ticket_set.filter(rating_percentage__gt=0)])

    def paid_expeditures(self):
        tickets = self.user.ticket_set.all()
        res = 0
        for ticket in tickets:
            res += sum(e.amount for e in Expediture.objects.filter(ticket_id=ticket.id, paid=True))
        return res

    def count_ticket_created(self):
        return len(self.user.ticket_set.all())

    def transactions(self):
        return Transaction.objects.filter(other=self.user).aggregate(count=models.Count('id'),
                                                                     amount=models.Sum('amount'))

    def is_socialauth_connected(self, type):
        try:
            UserSocialAuth.objects.get(user_id=self.user.id, provider=type)
            return True
        except UserSocialAuth.DoesNotExist:
            return False

    def __str__(self):
        return str(self.user)

    class Meta:
        verbose_name = _('Tracker profile')
        verbose_name_plural = _('Tracker profiles')
        permissions = (
            ("bypass_disabled_comments", "Can post comments even if they are not enabled."),
            ("import_unlimited_rows", "Can import more than a hundred rows at a time."),
        )


@receiver(post_save, sender=User)
def create_user_profile(sender, **kwargs):
    user = kwargs['instance']
    if len(TrackerProfile.objects.filter(user=user)) == 0:
        TrackerProfile.objects.create(user=user)
    if len(TrackerPreferences.objects.filter(user=user)) == 0:
        TrackerPreferences.objects.create(user=user)


class Transaction(Model):
    """ One payment to or from the user. """
    date = models.DateField(_('date'))
    other = models.ForeignKey('auth.User', verbose_name=_('other party'), blank=True, null=True,
                              help_text=_('The other party; user who sent or received the payment'), on_delete=models.SET_NULL)
    other_text = models.CharField(_('other party (text)'), max_length=60, blank=True,
                                  help_text=_('The other party; this text is used when user is not selected'))
    amount = models.DecimalField(_('amount'), max_digits=8, decimal_places=2, help_text=_(
        'Payment amount; Positive value means transaction to the user, negative is a transaction from the user'))
    description = models.CharField(_('description'), max_length=255, help_text=_('Description of this transaction'))
    accounting_info = models.CharField(_('accounting info'), max_length=255, blank=True, help_text=_('Accounting info'))
    tickets = models.ManyToManyField(Ticket, verbose_name=_('related tickets'), blank=True,
                                     help_text=_('Tickets this trackaction is related to'))
    cluster = models.ForeignKey('Cluster', blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        out = u'%s, %s %s' % (self.date, self.amount, settings.TRACKER_CURRENCY)
        if self.description is not None:
            out += ': ' + self.description
        return out

    def other_party(self):
        if self.other is not None:
            return self.other.username
        else:
            return self.other_text

    other_party.short_description = _('other party')

    def other_party_html(self):
        if self.other is not None:
            return UserWrapper(self.other).get_html_link()
        else:
            return escape(self.other_text)

    def ticket_ids(self):
        return u', '.join([str(t.id) for t in self.tickets.order_by('id')])

    def tickets_by_id(self):
        return self.tickets.order_by('id')

    def grant_set(self):
        return Grant.objects.extra(
            where=[
                'id in (select grant_id from tracker_topic topic where topic.id in (select topic_id from tracker_ticket ticket where ticket.id in (select ticket_id from tracker_transaction_tickets where transaction_id = %s)))'
            ],
            params=[self.id]
        ).order_by('id')

    @staticmethod
    def currency():
        return settings.TRACKER_CURRENCY

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')
        ordering = ['-date']


class Cluster(Model):
    """ This is an auxiliary/cache model used to track relationships between tickets and payments. """
    id = models.IntegerField(primary_key=True)  # cluster ID is always the id of its lowest-numbered ticket
    more_tickets = models.BooleanField()  # does this cluster have more tickets?
    total_tickets = models.DecimalField(max_digits=8, decimal_places=2, blank=True,
                                        null=True)  # refreshed on cluster status update
    total_transactions = models.DecimalField(max_digits=10, decimal_places=2, blank=True,
                                             null=True)  # refreshed on cluster status update

    def get_absolute_url(self):
        return reverse('cluster_detail', kwargs={'pk': self.id})

    def __str__(self):
        return self.id


class TicketAck(Model):
    """ Ack flag for given ticket. """
    ticket = models.ForeignKey('Ticket', on_delete=models.CASCADE)
    ack_type = models.CharField(max_length=20, choices=ACK_TYPES)
    added = models.DateTimeField(_('created'), auto_now_add=True)
    added_by = models.ForeignKey('auth.User', blank=True, null=True, on_delete=models.SET_NULL)
    comment = models.CharField(_('comment'), blank=True, max_length=255)

    def __str__(self):
        return u'%d %s by %s on %s' % (self.ticket_id, self.get_ack_type_display(), self.added_by, self.added)

    def added_by_html(self):
        if self.added_by is not None:
            return UserWrapper(self.added_by).get_html_link()
        else:
            return ''

    def save(self, *args, **kwargs):
        super(TicketAck, self).save(*args, **kwargs)

        old_is_completed = self.ticket.is_completed
        acks = self.ticket.ack_set()
        self.ticket.is_completed = ('archive' in acks) or ('close' in acks)
        if old_is_completed != self.ticket.is_completed:
            self.ticket.save()

    @property
    def user_removable(self):
        """ If this ack can be removed by user (provided the ticket is not locked, user has rights, etc) """
        return self.ack_type in USER_EDITABLE_ACK_TYPES

    class Meta:
        ordering = ['added']


@receiver(post_save, sender=TicketAck)
def flush_ticket_after_ack_save(sender, instance, created, raw, **kwargs):
    if not raw:
        instance.ticket.update_payment_status()


@receiver(post_delete, sender=TicketAck)
def flush_ticket_after_ack_delete(sender, instance, **kwargs):
    instance.ticket.update_payment_status()
    old_is_completed = instance.ticket.is_completed
    acks = instance.ticket.ack_set()
    instance.ticket.is_completed = ('archive' in acks) or ('close' in acks)
    if old_is_completed != instance.ticket.is_completed:
        instance.ticket.save()


class Notification(models.Model):
    """Notification that is supposed to be sent."""
    target_user = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)
    fired = models.DateTimeField('fired', auto_now_add=True)
    text = models.TextField('text', default="")
    notification_type = models.CharField('notification_type', max_length=50, choices=NOTIFICATION_TYPES, null=True)

    def __str__(self):
        return self.text

    @staticmethod
    def fire_notification(ticket, raw_text, notification_type, sender, additional=set(), text_data={}, ack_type=None):
        if sender is None:
            return
        users = set([])
        if ticket.requested_user is not None:
            users = {ticket.requested_user}
            if Watcher.objects.filter(watcher_type='Ticket', object_id=ticket.id, user=ticket.requested_user).exists() \
                    or Watcher.objects.filter(watcher_type='Topic', object_id=ticket.topic.id,
                                              user=ticket.requested_user).exists() \
                    or Watcher.objects.filter(watcher_type='Grant', object_id=ticket.topic.grant.id,
                                              user=ticket.requested_user).exists():
                users.remove(ticket.requested_user)
        admins = set(ticket.topic.admin.all())
        admins_to_be_removed_from_set = []
        for admin in admins:
            if Watcher.objects.filter(watcher_type='Ticket', object_id=ticket.id, user=admin).exists() \
                    or Watcher.objects.filter(watcher_type='Topic', object_id=ticket.topic.id, user=admin).exists() \
                    or Watcher.objects.filter(watcher_type='Grant', object_id=ticket.topic.grant.id,
                                              user=admin).exists():
                admins_to_be_removed_from_set.append(admin)
        for admin in admins_to_be_removed_from_set:
            admins.remove(admin)
        topicwatchers = set([tw.user for tw in Watcher.objects.filter(watcher_type='Topic', object_id=ticket.topic.id,
                                                                      notification_type=notification_type)])
        ticketwatchers = set([tw.user for tw in Watcher.objects.filter(watcher_type='Ticket', object_id=ticket.id,
                                                                       notification_type=notification_type)])
        grantwatchers = set([tw.user for tw in
                             Watcher.objects.filter(watcher_type='Grant', object_id=ticket.topic.grant.id,
                                                    notification_type=notification_type)])
        users = users.union(admins, additional, topicwatchers, ticketwatchers, grantwatchers)

        # Don't create a Notification again if there's already the exact same
        # notification in the database.
        if len(Notification.objects.filter(
                text=raw_text, notification_type=notification_type)) > 0:
            return

        for user in users:
            with translation.override(user.trackerpreferences.email_language):
                if user == sender:
                    continue
                if notification_type == 'comment' and not ticket.can_see_comments(user):
                    continue
                if notification_type in user.trackerpreferences.get_muted_notifications():
                    continue
                if 'muted' in user.trackerpreferences.get_muted_notifications():
                    continue
                if ack_type in user.trackerpreferences.get_muted_ack():
                    continue

                if text_data:
                    text = raw_text % text_data
                else:
                    text = raw_text

                Notification.objects.create(text=text, notification_type=notification_type, target_user=user)


@receiver(comment_was_posted)
def notify_comment(sender, comment, **kwargs):
    obj = comment.content_object
    if type(obj) == Ticket:
        if comment.user is None:
            user = comment.name
        else:
            if comment.user is not None and comment.name == comment.user.username:
                user = comment.name
            else:
                user = '%s (%s)' % (comment.name, comment.user.username)
        text = _(
            'Comment <tt>%(comment)s</tt> was added to ticket <a href="%(ticket_url)s">%(ticket)s</a> by user <tt>%(user)s</tt>')
        text_data = {
            'comment': ((comment.comment[:75] + '..') if len(comment.comment) > 75 else comment.comment).replace('\r\n',
                                                                                                                 ' '),
            'ticket_url': settings.BASE_URL + obj.get_absolute_url(),
            'ticket': obj,
            'user': user
        }
        usersmentioned = re.findall(r'@([-a-zA-Z0-9_.]+)', comment.comment)
        additional = set()
        for user_name in usersmentioned:
            users = User.objects.filter(username=user_name)
            if len(users) == 1:
                additional.add(users[0])
            else:
                continue
        Notification.fire_notification(obj, text, "comment", comment.user, additional=additional, text_data=text_data)


@receiver(comment_was_posted)
def add_commenting_user_to_watchers(sender, comment, **kwargs):
    obj = comment.content_object
    if type(obj) == Ticket and comment.user is not None:
        if comment.user != obj.requested_user and comment.user not in obj.topic.admin.all():
            Watcher.objects.create(watcher_type='Ticket', watched=obj, user=comment.user, notification_type="comment")


@receiver(post_save, sender=Ticket)
def notify_ticket(sender, instance, created, raw, **kwargs):
    if created:
        text = _(
            'User <tt>%(user)s</tt> created ticket <a href="%(ticket_url)s">%(ticket)s</a> in topic <tt>%(topic)s</tt>.')
        text_data = {
            'user': get_user(),
            'ticket_url': settings.BASE_URL + instance.get_absolute_url(),
            'ticket': instance,
            'topic': instance.topic
        }
        Notification.fire_notification(instance, text, "ticket_new", get_user(True), text_data=text_data)


@receiver(pre_save, sender=Ticket)
def notify_supervizor_notes(sender, instance, **kwargs):
    if instance.id is not None:
        old = Ticket.objects.get(id=instance.id)
        if old.supervisor_notes != instance.supervisor_notes:
            text = _(
                'User <tt>%(user)s</tt> changed supervisor notes of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            text_data = {
                'user': get_user(),
                'ticket_url': settings.BASE_URL + instance.get_absolute_url(),
                'ticket': instance
            }
            Notification.fire_notification(instance, text, "supervisor_notes", get_user(True), text_data=text_data)


@receiver(pre_save, sender=Ticket)
def notify_ticket_change(sender, instance, **kwargs):
    if instance.id is not None and len(Notification.objects.filter(text__contains=instance.get_absolute_url(),
                                                                   notification_type="ticket_new")) == 0:
        old = Ticket.objects.get(id=instance.id)
        text_data = {
            'ticket_url': settings.BASE_URL + instance.get_absolute_url(),
            'user': get_user(),
            'ticket': instance
        }
        if old.description != instance.description:
            text = _('User <tt>%(user)s</tt> changed description of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance, text, "ticket_change", get_user(True), text_data=text_data)
        if old.name != instance.name:
            text = _('User <tt>%(user)s</tt> changed name of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance, text, "ticket_change", get_user(True), text_data=text_data)
        if old.report_url != instance.report_url:
            text = _('User <tt>%(user)s</tt> changed link to report of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance, text, "ticket_change", get_user(True), text_data=text_data)
        if old.deposit != instance.deposit:
            text = _(
                'User <tt>%(user)s</tt> changed requested deposit of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance, text, "ticket_change", get_user(True), text_data=text_data)


@receiver(pre_save, sender=Ticket)
def notify_ticket_change_2(sender, instance, **kwargs):
    if instance.id is not None:
        old = Ticket.objects.get(id=instance.id)
        if old.mandatory_report != instance.mandatory_report:
            text = _(
                'User <tt>%(user)s</tt> changed "Is report mandatory?" field of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            text_data = {
                'ticket_url': settings.BASE_URL + instance.get_absolute_url(),
                'user': get_user(),
                'ticket': instance
            }
            Notification.fire_notification(instance, text, "ticket_change", get_user(True), text_data=text_data)


@receiver(post_delete, sender=Ticket)
def notify_ticket_delete(sender, instance, **kwargs):
    if instance.id is not None:
        text = _('Ticket "%(ticket)s" was deleted by user %(user)s')
        text_data = {
            'ticket': instance,
            'user': get_user()
        }
        Notification.fire_notification(instance, text, "ticket_delete", get_user(True), text_data=text_data)


@receiver(post_save, sender=TicketAck)
def notify_ack_add(sender, instance, created, **kwargs):
    text_data = {
        'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
        'user': instance.added_by,
        'ticket': instance.ticket,
        'ack_type': instance.get_ack_type_display()
    }
    text = _(
        'User <tt>%(user)s</tt> added ack <tt>%(ack_type)s</tt> to ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
    Notification.fire_notification(instance.ticket, text, "ack_add", get_user(True), text_data=text_data,
                                   ack_type=instance.ack_type)


@receiver(post_delete, sender=TicketAck)
def notify_ack_remove(sender, instance, **kwargs):
    text_data = {
        'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
        'user': get_user(),
        'ticket': instance.ticket,
        'ack_type': instance.get_ack_type_display()
    }
    text = _(
        'User <tt>%(user)s</tt> removed ack <tt>%(ack_type)s</tt> from ticket <a href="%(ticket_url)s">%(ticket)s</a>')
    Notification.fire_notification(instance.ticket, text, "ack_remove", get_user(True), text_data=text_data,
                                   ack_type=instance.ack_type)


@receiver(post_save, sender=Preexpediture)
def notify_preexpediture(sender, instance, created, raw, **kwargs):
    if (len(Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type="ticket_new")) == 0 and
            created):
        # HACK: It turns out `instance` and Preexpediture. objects.get(id=instance.id)
        # are different. Especially for the `Preexpediture.amount` field which
        # is intended to be a Decimal with precision of 2 digits.
        # For example if the wage was (2.00)
        # If we printed the stringified `instance.wage`, we'd get "2"
        # on the other hand, if we printed the stringified of
        # `Preexpediture.objects.get(id=instance.id)` (from the database)
        # we'd get "2.00".
        #
        # We use the data given by the database rather than the instance
        # because it will affect how `notify_preexpediture_change()`
        # and `notify_del_preexpediture()` will work.
        preexpediture_instance = Preexpediture.objects.get(id=instance.id)

        text_data = {
            'user': get_user(),
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'expeditures': preexpediture_instance,
            'ticket': instance.ticket
        }
        text = _(
            'User <tt>%(user)s</tt> added planned expeditures <tt>%(expeditures)s</tt> to ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "preexpeditures_new", get_user(True), text_data=text_data)


@receiver(pre_save, sender=Preexpediture)
def notify_preexpediture_change(sender, instance, **kwargs):
    if instance.id is not None:
        old = Preexpediture.objects.get(id=instance.id)
        if Notification.objects.filter(text__contains=str(old), notification_type="preexpeditures_new"):
            return

        text_data = {
            'user': get_user(),
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'expeditures': instance,
            'old_expediture': old,
            'ticket': instance.ticket
        }

        if old.amount != instance.amount or old.description != instance.description:
            text = _(
                'User <tt>%(user)s</tt> changed planned expediture from <tt>%(old_expediture)s</tt> to <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance.ticket, text, "preexpeditures_change", get_user(True),
                                           text_data=text_data)

        if old.wage != instance.wage:
            if instance.wage:
                text = _(
                    'User <tt>%(user)s</tt> set planned expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as wage.')
            else:
                text = _(
                    'User <tt>%(user)s</tt> set planned expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as not wage.')
            Notification.fire_notification(instance.ticket, text, "preexpeditures_change", get_user(True),
                                           text_data=text_data)


@receiver(post_delete, sender=Preexpediture)
def notify_del_preexpediture(sender, instance, **kwargs):
    if len(Ticket.objects.filter(id=instance.ticket.id)) > 0 and len(
            Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type="ticket_new")) == 0:
        text_data = {
            'user': get_user(),
            'expediture': instance,
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket
        }
        text = _(
            'User <tt>%(user)s</tt> removed planned expediture <tt>%(expediture)s</tt> from ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "preexpeditures_change", get_user(True),
                                       text_data=text_data)


@receiver(post_save, sender=Expediture)
def notify_expediture(sender, instance, created, raw, **kwargs):
    if (len(Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type__in=["ticket_new", "expeditures_new"])) == 0 and
            created):
        # HACK: See comments in `notify_preexpediture()`
        expediture_instance = Expediture.objects.get(id=instance.id)

        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
            'expeditures': expediture_instance
        }

        text = _(
            'User <tt>%(user)s</tt> added real expeditures <tt>%(expeditures)s</tt> to ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "expeditures_new", get_user(True), text_data=text_data)


@receiver(pre_save, sender=Expediture)
def notify_expediture_change(sender, instance, **kwargs):
    if instance.id is not None:
        old = Expediture.objects.get(id=instance.id)
        if Notification.objects.filter(text__contains=str(old), notification_type="expeditures_new"):
            return

        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
            'old_expediture': old,
            'expeditures': instance
        }

        if old.amount != instance.amount or old.description != instance.description or old.accounting_info != instance.accounting_info:
            text = _(
                'User <tt>%(user)s</tt> changed real expediture from <tt>%(old_expediture)s</tt> to <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance.ticket, text, "expeditures_change", get_user(True), text_data=text_data)

        if old.paid != instance.paid:
            if instance.paid:
                text = _(
                    'User <tt>%(user)s</tt> set real expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as paid.')
            else:
                text = _(
                    'User <tt>%(user)s</tt> set real expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as not paid.')
            Notification.fire_notification(instance.ticket, text, "expeditures_change", get_user(True), text_data=text_data)
        if old.wage != instance.wage:
            if instance.wage:
                text = _(
                    'User <tt>%(user)s</tt> set real expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as wage.')
            else:
                text = _(
                    'User <tt>%(user)s</tt> set real expediture <tt>%(expeditures)s</tt> of ticket <a href="%(ticket_url)s">%(ticket)s</a> as not wage.')
            Notification.fire_notification(instance.ticket, text, "expeditures_change", get_user(True), text_data=text_data)


@receiver(post_delete, sender=Expediture)
def notify_del_expediture(sender, instance, **kwargs):
    if len(Ticket.objects.filter(id=instance.ticket.id)) > 0 and len(
            Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type="ticket_new")) == 0:
        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
            'expeditures': instance
        }
        text = _(
            'User <tt>%(user)s</tt> removed real expeditures <tt>%(expeditures)s</tt> from ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "expeditures_change", get_user(True), text_data=text_data)


@receiver(post_save, sender=MediaInfo)
def notify_media(sender, instance, created, raw, **kwargs):
    if len(Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                       notification_type__in=["ticket_new", "media_new"])) == 0:
        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
        }
        if created:
            text = _('User <tt>%(user)s</tt> added media to ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance.ticket, text, "media_new", get_user(True), text_data=text_data)
        else:
            text = _('User <tt>%(user)s</tt> changed media of ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
            Notification.fire_notification(instance.ticket, text, "media_change", get_user(True), text_data=text_data)


@receiver(post_delete, sender=MediaInfo)
def notify_del_media(sender, instance, **kwargs):
    if len(Ticket.objects.filter(id=instance.ticket.id)) > 0 and len(
            Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type="ticket_new")) == 0:
        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
        }
        text = _('User <tt>%(user)s</tt> removed media from ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "media_change", get_user(True), text_data=text_data)


@receiver(post_save, sender=Document)
def notify_document(sender, instance, created, **kwargs):
    if len(Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                       notification_type__in=["ticket_new", "document"])) == 0:
        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
            'document_filename': instance.filename,
            'document_description': instance.description or _('no description'),
        }
        if created:
            text = _(
                'User <tt>%(user)s</tt> added document <tt>%(document_filename)s (%(document_description)s)</tt> to ticket <a href="%(ticket_url)s">%(ticket)s</a>')
        else:
            text = _('User <tt>%(user)s</tt> changed document <tt>%(document_filename)s</tt> assigned to ticket <a href="%(ticket_url)s">%(ticket)s</a>.')
        Notification.fire_notification(instance.ticket, text, "document", get_user(True), text_data=text_data)


@receiver(post_delete, sender=Document)
def notify_del_document(sender, instance, **kwargs):
    if len(Ticket.objects.filter(id=instance.ticket.id)) > 0 and len(
            Notification.objects.filter(text__contains=instance.ticket.get_absolute_url(),
                                        notification_type__in=["ticket_new", "document_new"])) == 0:
        text_data = {
            'ticket_url': settings.BASE_URL + instance.ticket.get_absolute_url(),
            'ticket': instance.ticket,
            'user': get_user(),
            'document_filename': instance.filename,
            'document_description': instance.description or _('no description'),
        }
        text = _(
            'User <tt>%(user)s</tt> removed document <tt>%(document_filename)s (%(document_description)s)</tt> from ticket <a href="%(ticket_url)s">%(ticket)s</a>')
        Notification.fire_notification(instance.ticket, text, "document", get_user(True), text_data=text_data)


class PossibleAck(object):
    """ Python representation of possible ack that can be added by user to a ticket. """
    _display_names = dict(ACK_TYPES)

    def __init__(self, ack_type):
        if ack_type not in self._display_names:
            raise ValueError(ack_type)
        self.ack_type = ack_type

    def __eq__(self, other):
        return self.ack_type == other.ack_type

    def __str__(self):
        return self.display

    @property
    def display(self):
        return self._display_names[self.ack_type]
