# -*- coding: utf-8 -*-
import datetime
import json
from collections import namedtuple

from django.db import models, connection
from django.db.models import Q
from django import forms
from django.db.models.functions import Coalesce
from django.forms.models import fields_for_model, inlineformset_factory, BaseInlineFormSet
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest, Http404
from django.core.exceptions import PermissionDenied
from django.utils.functional import curry
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.html import strip_tags
from django.http import JsonResponse
from django.views.generic import ListView, DetailView, FormView, DeleteView
from django.contrib.admin import widgets as adminwidgets
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.urls import reverse
from django.template.loader import get_template
from django.template import Context
from sendfile import sendfile
from django.utils.translation import get_language
from tracker.services import get_request
from social_django.models import UserSocialAuth
from io import TextIOWrapper
import csv

from tracker.models import Ticket, Topic, Subtopic, Grant, FinanceStatus, MediaInfo, MediaInfoOld, Expediture, Preexpediture, Transaction, Cluster, TrackerPreferences, TrackerProfile, Document, TicketAck, PossibleAck, Watcher, Signature
from tracker.models import ACK_TYPES, NOTIFICATION_TYPES
from users.models import UserWrapper
from socialauth.api import MediaWiki

TICKET_EXCLUDE_FIELDS = (
            'created', 'media_updated', 'updated', 'requested_user', 'requested_text',
            'custom_state', 'rating_percentage', 'supervisor_notes', 'cluster', 'payment_status',
            'mandatory_report', 'imported', 'enable_comments', 'statutory_declaration_date', 'is_completed'
        )


def ticket_list(request, page=1):
    response = render(request, 'tracker/index.html', {"LANGUAGE": get_language()})
    response["Access-Control-Allow-Origin"] = "*"
    return response


def tickets_json(request, lang):
    return JsonResponse({"data": [ticket.get_cached_ticket() for ticket in Ticket.objects.order_by('-id')]})


class CommentPostedCatcher(object):
    """
    View mixin that catches 'c' GET argument from comment framework
    and turns in into a success message.
    """
    def get(self, request, **kwargs):
        if 'c' in request.GET:
            messages.success(request, _('Comment posted, thank you.'))
            return HttpResponseRedirect(request.path)
        return super(CommentPostedCatcher, self).get(request, **kwargs)


class TicketDetailView(CommentPostedCatcher, DetailView):
    model = Ticket

    def get_context_data(self, **kwargs):
        user = self.request.user
        ticket = self.object
        context = super(TicketDetailView, self).get_context_data(**kwargs)
        context['user_can_edit_ticket'] = ticket.can_edit(user)
        context['user_can_edit_ticket_media'] = ticket.can_edit(user) and ticket.topic.ticket_media
        admin_edit = user.is_staff and (user.has_perm('tracker.supervisor') or user.topic_set.filter(id=ticket.topic_id).exists())
        context['user_can_edit_ticket_in_admin'] = admin_edit
        context['user_can_edit_documents'] = ticket.is_editable(user)
        context['user_can_see_all_documents'] = ticket.can_see_all_documents(user)
        if user.is_authenticated:
            context['user_selfuploaded_docs'] = ticket.document_set.filter(uploader=user)
        else:
            context['user_selfuploaded_docs'] = ticket.document_set.none()
        context['user_can_copy_preexpeditures'] = ticket.can_copy_preexpeditures(user)
        context['user_admin_of_topic'] = user in ticket.topic.admin.all()
        return context


ticket_detail = TicketDetailView.as_view()


class TicketAckAddForm(forms.Form):
    comment = forms.CharField(required=False, max_length=255)


class TicketAckAddView(FormView):
    template_name = 'tracker/ticketack_add.html'
    form_class = TicketAckAddForm

    def get_form(self, form_class=None):
        ticket = get_object_or_404(Ticket, id=self.kwargs['pk'])
        if not (ticket.can_edit(self.request.user) and self.kwargs['ack_type'] in ticket.possible_user_ack_types()):
            raise PermissionDenied(_('You cannot add ack to a ticket you do not own.'))
        return super().get_form(form_class)

    def form_valid(self, form):
        ticket = get_object_or_404(Ticket, id=self.kwargs['pk'])
        ack = TicketAck.objects.create(
            ticket=ticket,
            ack_type=self.kwargs['ack_type'],
            added_by=self.request.user,
            comment=form.cleaned_data['comment'],
        )
        msg = _('Ticket %(ticket_id)s confirmation "%(confirmation)s" has been added.') % {
            'ticket_id': ticket.id, 'confirmation': ack.get_ack_type_display(),
        }
        messages.success(self.request, msg)
        return HttpResponseRedirect(ticket.get_absolute_url())

    def get_context_data(self, **kwargs):
        kwargs.update({
            'ticket': get_object_or_404(Ticket, id=self.kwargs['pk']),
            'ticketack': PossibleAck(self.kwargs['ack_type']),
        })
        return kwargs


ticket_ack_add = TicketAckAddView.as_view()


class TicketAckDeleteView(DeleteView):
    model = TicketAck

    def get_object(self, queryset=None):
        try:
            self.ticket = Ticket.objects.get(id=self.kwargs['pk'])
            ack = self.ticket.ticketack_set.get(id=self.kwargs['ack_id'])
        except (Ticket.DoesNotExist, TicketAck.DoesNotExist):
            raise Http404
        return ack

    def delete(self, request, *args, **kwargs):
        ack = self.get_object()
        if not (self.ticket.can_edit(request.user) and ack.user_removable):
            raise PermissionDenied('You cannot edit this')

        ack_display = ack.get_ack_type_display()
        ack.delete()

        msg = _('Ticket %(ticket_id)s confirmation "%(confirmation)s" has been deleted.') % {
            'ticket_id': self.ticket.id, 'confirmation': ack_display,
        }
        messages.success(request, msg)
        return HttpResponseRedirect(self.ticket.get_absolute_url())


ticket_ack_delete = TicketAckDeleteView.as_view()


def grant_list(request):
    return render(request, 'tracker/grant_list.html', {
        'open_grants': [g for g in Grant.objects.all() if g.open_for_tickets()],
        'closed_grants': [g for g in Grant.objects.all() if not g.open_for_tickets()],
    })


def topic_list(request):
    return render(request, 'tracker/topic_list.html', {
        'open_topics': Topic.objects.filter(open_for_tickets=True),
        'closed_topics': Topic.objects.filter(open_for_tickets=False),
    })


class TopicDetailView(CommentPostedCatcher, DetailView):
    model = Topic

    def get_context_data(self, **kwargs):
        context = super(TopicDetailView, self).get_context_data(**kwargs)
        context['user_admin_of_topic'] = self.request.user in self.object.admin.all()
        return context


topic_detail = TopicDetailView.as_view()


class SubtopicDetailView(CommentPostedCatcher, DetailView):
    model = Subtopic


subtopic_detail = SubtopicDetailView.as_view()


class TicketForm(forms.ModelForm):
    statutory_declaration = forms.BooleanField(label=ugettext_lazy('Statutory declaration'), help_text=settings.STATUTORY_DECLARATION_TEXT, required=False)

    def __init__(self, *args, **kwargs):
        super(TicketForm, self).__init__(*args, **kwargs)
        self.fields['topic'].queryset = self.get_topic_queryset()
        self.fields['statutory_declaration'].initial = self.instance.signature_set.filter(user=self.instance.requested_user).exists()

    def get_topic_queryset(self):
        return Topic.objects.filter(open_for_tickets=True)

    def save(self, commit=True):
        instance = super(TicketForm, self).save(commit=commit)
        if self.cleaned_data.get('statutory_declaration') and instance.car_travel and not instance.signature_set.filter(user=get_request().user).exists():
            Signature.objects.create(signed_text=settings.STATUTORY_DECLARATION_TEXT, user=get_request().user, signed_ticket=instance)
        elif not self.cleaned_data.get('statutory_declaration') or not instance.car_travel:
            instance.signature_set.filter(user=self.instance.requested_user).delete()
        return instance

    def _media(self):
        return super(TicketForm, self).media + forms.Media(js=('ticketform/common.js', 'ticketform/subtopics.js', 'ticketform/form.js'))
    media = property(_media)

    class Meta:
        model = Ticket
        exclude = TICKET_EXCLUDE_FIELDS
        widgets = {
            'event_date': adminwidgets.AdminDateWidget(),
            'name': forms.TextInput(attrs={'size': '40'}),
            'description': forms.Textarea(attrs={'rows': '4', 'cols': '60'}),
        }


def check_ticket_form_deposit(ticketform, preexpeditures):
    """
    Checks ticket deposit form field against preexpediture form.
    Injects error there if there is a problem.
    """
    if not (ticketform.is_valid() and preexpeditures.is_valid()):
        return

    deposit = ticketform.cleaned_data.get('deposit')
    if deposit is None:
        return

    total_preexpeditures = sum([pe.cleaned_data.get('amount', 0) for pe in preexpeditures])
    if deposit > total_preexpeditures:
        ticketform.add_error('deposit', forms.ValidationError(
            _("Your deposit is bigger than your preexpeditures")
        ))


def check_statutory_declaration(ticketform):
    """
    Checks if both car_travel and statutory_declaration fields (if required)
    were checked when saving the ticket.
    """
    if not ticketform.is_valid():
        return

    car_travel = ticketform.cleaned_data.get('car_travel')
    statutory_declaration = ticketform.cleaned_data.get('statutory_declaration')

    if ticketform.cleaned_data.get('topic').ticket_statutory_declaration and car_travel and not statutory_declaration:
        ticketform.add_error('statutory_declaration', forms.ValidationError(
            _('You are required to do statutory declaration')
        ))


def check_subtopic(ticketform):
    """
    Checks if subtopic belongs to given topic.
    """
    if not ticketform.is_valid():
        return

    topic = ticketform.cleaned_data.get('topic')
    subtopic = ticketform.cleaned_data.get('subtopic')

    if subtopic is not None and subtopic not in topic.subtopic_set.all():
        ticketform.add_error('subtopic', forms.ValidationError(
            _('Subtopic must belong to the topic you used. You probably have JavaScript turned off.')
        ))


def get_edit_ticket_form_class(ticket):
    class EditTicketForm(TicketForm):
        def get_topic_queryset(self):
            return Topic.objects.filter(Q(open_for_tickets=True) | Q(id=ticket.topic.id))

    class PrecontentEditTicketForm(EditTicketForm):
        """ Ticket edit form with disabled deposit field """
        # NOTE in Django 1.9+, this can be set directly on the field:
        # https://docs.djangoproject.com/en/dev/ref/forms/fields/#disabled
        def __init__(self, *args, **kwargs):
            super(PrecontentEditTicketForm, self).__init__(*args, **kwargs)
            self.fields['deposit'].widget.attrs['disabled'] = True
            self.fields['deposit'].required = False

        def clean_deposit(self):
            return self.instance.deposit

    if "precontent" in ticket.ack_set():
        return PrecontentEditTicketForm
    else:
        return EditTicketForm


adminCore = forms.Media(js=(
    settings.ADMIN_MEDIA_PREFIX + "js/vendor/jquery/jquery.min.js",
    settings.STATIC_URL + "jquery.both.js",
    settings.ADMIN_MEDIA_PREFIX + "js/core.js",
    settings.ADMIN_MEDIA_PREFIX + "js/inlines.js",
))


class ExtraItemFormSet(BaseInlineFormSet):
    """
    Inline formset class patched to always have one extra form when bound.
    This prevents hiding of the b0rked field in the javascript-hidden area
    when validation fails.
    """
    def total_form_count(self):
        original_count = super(ExtraItemFormSet, self).total_form_count()
        if self.is_bound:
            return original_count + 1
        else:
            return original_count


EXPEDITURE_FIELDS = ('description', 'amount', 'wage')
expeditureformset_factory = curry(
    inlineformset_factory, Ticket, Expediture,
    formset=ExtraItemFormSet, fields=EXPEDITURE_FIELDS
)

PREEXPEDITURE_FIELDS = ('description', 'amount', 'wage')
preexpeditureformset_factory = curry(
    inlineformset_factory, Ticket, Preexpediture,
    formset=ExtraItemFormSet, fields=PREEXPEDITURE_FIELDS
)


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = TrackerPreferences
        exclude = ('muted_notifications', 'muted_ack', 'user')


@login_required()
def preferences(request):
    if request.method == 'POST':
        muted = []
        ack_muted = []
        if 'muted' not in request.POST:
            for notification_type in NOTIFICATION_TYPES:
                if notification_type[0] in request.POST:
                    muted.append(notification_type[0])
                    del request.POST[notification_type[0]]
        else:
            muted.append('muted')
        for ack_type in ACK_TYPES:
            if ack_type[0] in request.POST:
                ack_muted.append(ack_type[0])
                del request.POST[ack_type[0]]
        request.user.trackerpreferences.muted_notifications = json.dumps(muted)
        request.user.trackerpreferences.muted_ack = json.dumps(ack_muted)
        request.user.trackerpreferences.save()

        pref_form = PreferencesForm(request.POST, instance=request.user.trackerpreferences)
        if pref_form.is_valid():
            pref_form.save()
            messages.success(request, _("We've updated your preferences"))
        return HttpResponseRedirect(request.path)
    else:
        notification_types = []
        ack_types = []
        muted = request.user.trackerpreferences.get_muted_notifications()
        ack_muted = request.user.trackerpreferences.get_muted_ack()
        for notification_type in NOTIFICATION_TYPES:
            notification_types.append((
                notification_type[0],
                notification_type[1],
                notification_type[0] in muted,
            ))
        for ack_type in ACK_TYPES:
            ack_types.append((
                ack_type[0],
                ack_type[1].capitalize(),
                ack_type[0] in ack_muted,
            ))

        account_has_mediawiki_connection = True
        try:
            user_social_auth_object = UserSocialAuth.objects.get(user_id=request.user.id)
        except UserSocialAuth.DoesNotExist:
            account_has_mediawiki_connection = False
        else:
            if user_social_auth_object.provider != "mediawiki":
                account_has_mediawiki_connection = False
        mediawiki_connect_data = {
            'is_connected': account_has_mediawiki_connection,
            'username': request.user.trackerprofile.mediawiki_username,
            'has_password': request.user.has_usable_password()
        }

        preferences_form = PreferencesForm(
            instance=request.user.trackerpreferences,
            initial=dict((pref.name, getattr(request.user.trackerpreferences, pref.name)) for pref in request.user.trackerpreferences._meta.fields if pref.name not in ('id', 'user'))
        )
        return render(request, 'tracker/preferences.html', {
            "notification_types": notification_types,
            "ack_types": ack_types,
            "mediawiki_connect_data": mediawiki_connect_data,
            "preferences_form": preferences_form
        })


class DeactivateForm(forms.Form):
    password = forms.CharField(
        label=_("Please enter your password to confirm the deactivation of your account."),
        widget=forms.PasswordInput
    )


@login_required
def deactivate_account(request):
    if request.method == "POST":
        form = DeactivateForm(request.POST)
        if form.is_valid():
            form_password = form.cleaned_data['password']
            if request.user.check_password(form_password):
                request.user.is_active = False
                request.user.save()
                if request.user.email:
                    email_subject = "[WMCZ Tracker] %s" % _("Account deactivation")
                    email_html_tempate = get_template('tracker/user_deactivate_email.html')
                    html_context_dict = {"username": request.user.username}
                    email_context = Context(html_context_dict)
                    request.user.email_user(email_subject,
                                            strip_tags(email_html_tempate.render(email_context)),
                                            html_message=email_html_tempate.render(email_context))
                messages.success(request, _('Your account has been deactivated.'))
                return HttpResponseRedirect(reverse('tracker_logout'))
            else:
                form.add_error("password", _("Password is incorrect."))
    else:
        form = DeactivateForm()
    return render(request, 'tracker/user_deactivate.html', {'form': form,
                                                            'username': request.user.username,
                                                            'email': request.user.email})


@login_required
def watch_ticket(request, pk):
    ticket = get_object_or_404(Ticket, id=pk)
    hidden_notifications = ["ticket_new", "muted"]
    if request.method == 'POST':
        create_watchers = True
        if request.user in ticket.topic.admin.all() or request.user == ticket.requested_user:
            all_notification_types_in_post = True
            for notification_type in NOTIFICATION_TYPES:
                if not notification_type[0] in request.POST and notification_type[0] not in hidden_notifications:
                    all_notification_types_in_post = False
            if all_notification_types_in_post:
                create_watchers = False
        for watcher in Watcher.objects.filter(watcher_type='Ticket', object_id=ticket.id, user=request.user):
            watcher.delete()
        if create_watchers:
            has_created_watcher = False
            for notification_type in NOTIFICATION_TYPES:
                if notification_type[0] in request.POST:
                    has_created_watcher = True
                    Watcher.objects.create(watcher_type='Ticket', watched=ticket, user=request.user, notification_type=notification_type[0])
            if not has_created_watcher and (request.user in ticket.topic.admin.all() or request.user == ticket.requested_user):
                Watcher.objects.create(watcher_type='Ticket', watched=ticket, user=request.user,
                                       notification_type="muted")
        messages.success(request, _("Ticket's %s watching settings are changed.") % ticket)
        return HttpResponseRedirect(ticket.get_absolute_url())
    else:
        notification_types = []
        user_is_admin_or_owner_and_no_watcher = (request.user in ticket.topic.admin.all() or request.user == ticket.requested_user) and not Watcher.objects.filter(watcher_type='Ticket', object_id=ticket.id, user=request.user).exists()
        watches_all_notifications = True
        for notification_type in NOTIFICATION_TYPES:
            if notification_type[0] in hidden_notifications:
                continue
            notification_type_watched = ticket.watches(request.user, notification_type[0]) if not user_is_admin_or_owner_and_no_watcher else True
            if not notification_type_watched:
                watches_all_notifications = False
            notification_types.append((
                notification_type[0],
                notification_type[1],
                notification_type_watched
            ))
        return render(request, 'tracker/watch.html', {
            "object": get_object_or_404(Ticket, id=pk),
            "objecttype": _("ticket"),
            "notification_types": notification_types,
            "watches_all_notifications": watches_all_notifications
        })


@login_required
def watch_topic(request, pk):
    topic = get_object_or_404(Topic, id=pk)
    hidden_notifications = ["muted"]
    if request.method == 'POST':
        create_watchers = True
        if request.user in topic.admin.all():
            all_notification_types_in_post = True
            for notification_type in NOTIFICATION_TYPES:
                if not notification_type[0] in request.POST and notification_type[0] not in hidden_notifications:
                    all_notification_types_in_post = False
            if all_notification_types_in_post:
                create_watchers = False
        for watcher in Watcher.objects.filter(watcher_type='Topic', object_id=topic.id, user=request.user):
            watcher.delete()
        if create_watchers:
            has_created_watcher = False
            for notification_type in NOTIFICATION_TYPES:
                if notification_type[0] in request.POST:
                    has_created_watcher = True
                    Watcher.objects.create(watcher_type='Topic', watched=topic, user=request.user, notification_type=notification_type[0])
            if not has_created_watcher and request.user in topic.admin.all():
                Watcher.objects.create(watcher_type='Topic', watched=topic, user=request.user,
                                       notification_type="muted")
        messages.success(request, _("Topic's %s watching settings are changed.") % topic)
        return HttpResponseRedirect(topic.get_absolute_url())
    else:
        notification_types = []
        user_is_admin_and_no_watcher = request.user in topic.admin.all() and not Watcher.objects.filter(watcher_type='Topic', object_id=topic.id, user=request.user).exists()
        for notification_type in NOTIFICATION_TYPES:
            if notification_type[0] in hidden_notifications:
                continue
            notification_types.append((
                notification_type[0],
                notification_type[1],
                topic.watches(request.user, notification_type[0]) if not user_is_admin_and_no_watcher else True
            ))
        return render(request, 'tracker/watch.html', {
            "object": topic,
            "objecttype": _("topic"),
            "notification_types": notification_types
        })


@login_required
def watch_grant(request, pk):
    grant = get_object_or_404(Grant, id=pk)
    hidden_notifications = ["muted"]
    if request.method == 'POST':
        for watcher in Watcher.objects.filter(watcher_type='Grant', object_id=grant.id, user=request.user):
            watcher.delete()
        for notification_type in NOTIFICATION_TYPES:
            if notification_type[0] in request.POST:
                Watcher.objects.create(watcher_type='Grant', watched=grant, user=request.user, notification_type=notification_type[0])
        messages.success(request, _("%s's watching settings are changed.") % grant)
        return HttpResponseRedirect(grant.get_absolute_url())
    else:
        notification_types = []
        for notification_type in NOTIFICATION_TYPES:
            if notification_type[0] in hidden_notifications:
                continue
            notification_types.append((
                notification_type[0],
                notification_type[1],
                grant.watches(request.user, notification_type[0])
            ))
        return render(request, 'tracker/watch.html', {
            "object": grant,
            "objecttype": _("grant"),
            "notification_types": notification_types
        })


@login_required
def create_ticket(request):
    ExpeditureFormSet = expeditureformset_factory(extra=2, can_delete=False)
    PreexpeditureFormSet = preexpeditureformset_factory(extra=2, can_delete=False)

    if request.method == 'POST':
        ticketform = TicketForm(request.POST)
        try:
            expeditures = ExpeditureFormSet(request.POST, prefix='expediture')
            preexpeditures = PreexpeditureFormSet(request.POST, prefix='preexpediture')
            expeditures.media  # this seems to be a regression between Django 1.3 and 1.6
            preexpeditures.media  # test
        except forms.ValidationError as e:
            return HttpResponseBadRequest(str(e))

        check_ticket_form_deposit(ticketform, preexpeditures)
        check_statutory_declaration(ticketform)
        check_subtopic(ticketform)
        if ticketform.is_valid() and expeditures.is_valid() and preexpeditures.is_valid():
            ticket = ticketform.save()
            ticket.requested_user = request.user
            ticket.save()
            if ticket.topic.ticket_expenses:
                expeditures.instance = ticket
                expeditures.save()
            if ticket.topic.ticket_preexpenses:
                preexpeditures.instance = ticket
                preexpeditures.save()
            messages.success(request, _('Ticket %s is created') % ticket)
            return HttpResponseRedirect(ticket.get_absolute_url())
    else:
        initial = {'event_date': datetime.date.today()}
        if 'topic' in request.GET:
            initial['topic'] = request.GET['topic']
        if 'subtopic' in request.GET:
            initial['topic'] = get_object_or_404(Subtopic, id=request.GET['subtopic']).topic.id
            initial['subtopic'] = request.GET['subtopic']
        if 'ticket' in request.GET:
            ticket = get_object_or_404(Ticket, id=request.GET['ticket'])
            initial['name'] = ticket.name
            initial['topic'] = ticket.topic
            initial['description'] = ticket.description
            initial['deposit'] = ticket.deposit
        ticketform = TicketForm(initial=initial)
        initialExpeditures = []
        if 'ticket' in request.GET:
            for e in Expediture.objects.filter(ticket=ticket):
                initialE = {}
                initialE['description'] = e.description
                initialE['amount'] = e.amount
                initialE['wage'] = e.wage
                initialExpeditures.append(initialE)
        ExpeditureFormSet = expeditureformset_factory(extra=2 + len(initialExpeditures), can_delete=False)
        expeditures = ExpeditureFormSet(prefix='expediture', initial=initialExpeditures)
        initialPreexpeditures = []
        if 'ticket' in request.GET:
            for pe in Preexpediture.objects.filter(ticket=ticket):
                initialPe = {}
                initialPe['description'] = pe.description
                initialPe['amount'] = pe.amount
                initialPe['wage'] = pe.wage
                initialPreexpeditures.append(initialPe)
        PreexpeditureFormSet = preexpeditureformset_factory(extra=2 + len(initialPreexpeditures), can_delete=False)
        preexpeditures = PreexpeditureFormSet(prefix='preexpediture', initial=initialPreexpeditures)

    return render(request, 'tracker/create_ticket.html', {
        'ticketform': ticketform,
        'expeditures': expeditures,
        'preexpeditures': preexpeditures,
        'form_media': adminCore + ticketform.media + expeditures.media,
    })


class SignTicketForm(forms.Form):
    statutory_declaration = forms.BooleanField(label=_('I confirm the above'), required=False)


@login_required
def sign_ticket(request, pk):
    ticket = get_object_or_404(Ticket, id=pk)
    if not ticket.topic.ticket_statutory_declaration or not ticket.car_travel:
        raise PermissionDenied(_('You cannot add statutory declaration to a ticket that does not support it.'))
    elif request.user == ticket.requested_user:
        raise PermissionDenied(_('You cannot use this view to add a statutory declaration to a ticket you created. Use edit ticket button for this.'))

    if request.method == 'POST':
        form = SignTicketForm(request.POST)
        if form.is_valid():
            if form.cleaned_data.get('statutory_declaration') and not Signature.objects.filter(signed_ticket=ticket, user=request.user).exists():
                Signature.objects.create(signed_ticket=ticket, user=request.user, signed_text=settings.STATUTORY_DECLARATION_TEXT)
                messages.success(request, _('You successfully added a statutory declaration to this ticket.'))
            else:
                Signature.objects.filter(signed_ticket=ticket, user=request.user).delete()
                messages.success(request, _('You successfully removed a statutory declaration from this ticket.'))
            return HttpResponseRedirect(ticket.get_absolute_url())
    else:
        initial = {
            'statutory_declaration': Signature.objects.filter(signed_ticket=ticket, user=request.user).exists()
        }
        form = SignTicketForm(initial=initial)
    return render(request, 'tracker/sign_ticket.html', {
        'form': form,
        'ticket': ticket,
        'declaration': settings.STATUTORY_DECLARATION_TEXT,
    })


@login_required
def manage_media(request, ticket_id):
    if not request.user.social_auth.filter(provider='mediawiki').exists():
        return render(request, 'tracker/connect_account.html', {
            'next': reverse('manage_media', kwargs={'ticket_id': ticket_id})
        }, status=403)

    ticket = get_object_or_404(Ticket, id=ticket_id)
    if not ticket.can_edit(request.user) or not ticket.topic.ticket_media:
        raise PermissionDenied(_('You cannot edit this ticket'))

    return render(request, 'tracker/ticket_media.html', {
        'ticket': ticket
    })


@login_required
def edit_ticket(request, pk):
    ticket = get_object_or_404(Ticket, id=pk)
    if not ticket.can_edit(request.user):
        raise PermissionDenied('You cannot edit this ticket')

    TicketEditForm = get_edit_ticket_form_class(ticket)

    ExpeditureFormSet = expeditureformset_factory(extra=1, can_delete=True)
    PreexpeditureFormSet = preexpeditureformset_factory(extra=1, can_delete=True)

    if request.method == 'POST':
        ticketform = TicketEditForm(request.POST, instance=ticket)
        try:
            if 'content' not in ticket.ack_set():
                expeditures = ExpeditureFormSet(request.POST, prefix='expediture', instance=ticket)
            else:
                expeditures = None
            if 'precontent' not in ticket.ack_set() and 'content' not in ticket.ack_set():
                preexpeditures = PreexpeditureFormSet(request.POST, prefix='preexpediture', instance=ticket)
            else:
                preexpeditures = None
        except forms.ValidationError as e:
            return HttpResponseBadRequest(str(e))

        if 'precontent' not in ticket.ack_set() and 'content' not in ticket.ack_set():
            check_ticket_form_deposit(ticketform, preexpeditures)

        check_statutory_declaration(ticketform)
        check_subtopic(ticketform)

        if ticketform.is_valid() \
                and (expeditures.is_valid() if 'content' not in ticket.ack_set() else True) \
                and (preexpeditures.is_valid() if 'precontent' not in ticket.ack_set() and 'content' not in ticket.ack_set() else True):
            ticket = ticketform.save()
            if expeditures is not None:
                expeditures.save()
            if preexpeditures is not None:
                preexpeditures.save()

            messages.success(request, _('Ticket %s saved.') % ticket)
            return HttpResponseRedirect(ticket.get_absolute_url())
    else:
        ticketform = TicketEditForm(instance=ticket)
        if 'content' not in ticket.ack_set():
            expeditures = ExpeditureFormSet(prefix='expediture', instance=ticket)
        else:
            expeditures = None  # Hide expeditures in the edit form
        if 'precontent' not in ticket.ack_set() and 'content' not in ticket.ack_set():
            preexpeditures = PreexpeditureFormSet(prefix='preexpediture', instance=ticket)
        else:
            preexpeditures = None  # Hide preexpeditures in the edit form

    form_media = adminCore + ticketform.media
    if 'content' not in ticket.ack_set():
        form_media += expeditures.media
    if 'precontent' not in ticket.ack_set() and 'content' not in ticket.ack_set():
        form_media += preexpeditures.media

    return render(request, 'tracker/edit_ticket.html', {
        'ticket': ticket,
        'ticketform': ticketform,
        'expeditures': expeditures,
        'preexpeditures': preexpeditures,
        'form_media': form_media,
        'user_can_edit_documents': request.user.is_authenticated,
        'user_can_copy_preexpeditures': ticket.can_copy_preexpeditures(request.user),
    })


class UploadDocumentForm(forms.Form):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={'size': '60'}), label=_('file'))
    name = forms.RegexField(r'^[-_\.A-Za-z0-9]+\.[A-Za-z0-9]+$', error_messages={'invalid': ugettext_lazy('We need a sane file name, such as my-invoice123.jpg')}, widget=forms.TextInput(attrs={'size': '30'}), label=_('name'))
    description = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'size': '60'}), label=_('description'))


DOCUMENT_FIELDS = ('filename', 'description')


def document_formfield(f, **kwargs):
    if f.name == 'description':
        kwargs['widget'] = forms.TextInput(attrs={'size': '60'})
    return f.formfield(**kwargs)


documentformset_factory = curry(
    inlineformset_factory, Ticket, Document,
    fields=DOCUMENT_FIELDS, formfield_callback=document_formfield
)


def document_view_required(access, ticket_id_field='pk', document_name_field=None):
    """ Wrapper for document-accessing views (access=read|write)"""
    def actual_decorator(view):
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.path)

            ticket = get_object_or_404(Ticket, id=kwargs[ticket_id_field])

            if not ticket.is_editable(request.user):
                raise PermissionDenied(_("You cannot edit this ticket documents, as it's no longer editable"))

            if document_name_field:
                uploader = get_object_or_404(ticket.document_set, filename=kwargs[document_name_field]).uploader
            else:
                uploader = None
            if (access == 'read' and (ticket.can_see_all_documents(request.user) or uploader == request.user)) or (access == 'write' and request.user.is_authenticated):
                return view(request, *args, **kwargs)
            else:
                raise PermissionDenied("You cannot see this ticket's documents.")
        return wrapped_view

    return actual_decorator


@document_view_required(access='write')
def edit_ticket_docs(request, pk):
    DocumentFormSet = documentformset_factory(extra=0, can_delete=True)

    ticket = get_object_or_404(Ticket, id=pk)

    filter = {
        'ticket': ticket
    }

    if not ticket.can_see_all_documents(request.user):
        filter['uploader'] = request.user

    if request.method == 'POST':
        try:
            documents = DocumentFormSet(request.POST, prefix='docs', instance=ticket, queryset=Document.objects.filter(**filter))
        except forms.ValidationError as e:
            return HttpResponseBadRequest(str(e))

        if documents.is_valid():
            documents.save()
            messages.success(request, _('Document changes for ticket %s saved.') % ticket)
            return HttpResponseRedirect(ticket.get_absolute_url())
    else:
        documents = DocumentFormSet(prefix='docs', instance=ticket, queryset=Document.objects.filter(**filter))

    return render(request, 'tracker/edit_ticket_docs.html', {
        'ticket': ticket,
        'documents': documents,
    })


@document_view_required(access='write')
def upload_ticket_doc(request, pk):
    ticket = get_object_or_404(Ticket, id=pk)

    if request.method == 'POST':
        upload = UploadDocumentForm(request.POST, request.FILES)
        if upload.is_valid():
            doc = Document(ticket=ticket)
            payload = upload.cleaned_data['file']
            filename = upload.cleaned_data['name']
            existingDocuments = Document.objects.filter(filename=filename, ticket=ticket)
            if existingDocuments.count() > 0:
                messages.error(request, _('There is already a document with that name. Please try to reupload with a different name.'))
                return render(request, 'tracker/upload_ticket_doc.html', {
                    'ticket': ticket,
                    'upload': upload,
                    'form_media': adminCore + upload.media,
                })
            doc.filename = filename
            doc.size = payload.size
            doc.content_type = payload.content_type
            doc.description = upload.cleaned_data['description']
            doc.payload.save(filename, payload)
            doc.save()
            messages.success(request, _('File %(filename)s has been saved.') % {'filename': filename})

            if 'add-another' in request.POST:
                next_view = 'upload_ticket_doc'
            else:
                next_view = 'ticket_detail'
            return HttpResponseRedirect(reverse(next_view, kwargs={'pk': ticket.id}))
    else:
        upload = UploadDocumentForm()

    return render(request, 'tracker/upload_ticket_doc.html', {
        'ticket': ticket,
        'upload': upload,
        'form_media': adminCore + upload.media,
    })


@document_view_required(access='read', ticket_id_field='ticket_id', document_name_field='filename')
def download_document(request, ticket_id, filename):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    doc = get_object_or_404(ticket.document_set, filename=filename)
    return sendfile(request, doc.payload.path, mimetype=doc.content_type)


def topic_finance(request):
    grants_out = []
    for grant in Grant.objects.all():
        topics = []
        grant_finance = FinanceStatus()
        for topic in grant.topic_set.all():
            topic_finance = topic.payment_summary()
            grant_finance.add_finance(topic_finance)
            topics.append({'topic': topic, 'finance': topic_finance})
        grants_out.append({'grant': grant, 'topics': topics, 'finance': grant_finance, 'rows': len(topics) + 1})

    return render(request, 'tracker/topic_finance.html', {
        'grants': grants_out,
        'have_fuzzy': any([row['finance'].fuzzy for row in grants_out]),
    })


class HttpResponseCsv(HttpResponse):
    def __init__(self, fields, *args, **kwargs):
        kwargs['content_type'] = 'text/csv'
        super(HttpResponseCsv, self).__init__(*args, **kwargs)
        self.writerow(fields)

    def writerow(self, row):
        self.write(u';'.join(map(lambda s: u'"' + str(s).replace('"', "'").replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ') + u'"', row)))
        self.write(u'\r\n')


def _get_topic_content_acks_per_user():
    """ Returns content acks counts per user and topic """
    cursor = connection.cursor()
    cursor.execute("""
        select
            ack.added_by_id user_id, topic.grant_id grant_id, ticket.topic_id topic_id, count(1) ack_count
        from
            tracker_ticketack ack
            left join tracker_ticket ticket on ack.ticket_id = ticket.id
            left join tracker_topic topic on ticket.topic_id = topic.id
        where
            ack_type = 'content'
            and added_by_id is not null
        group by user_id, grant_id, topic_id order by user_id, grant_id, topic_id
    """)
    row_tuple_type = namedtuple('Result', [col[0] for col in cursor.description])
    result = [row_tuple_type(*row) for row in cursor]
    users = User.objects.in_bulk([r.user_id for r in result])
    grants = Grant.objects.in_bulk([r.grant_id for r in result])
    topics = Topic.objects.in_bulk([r.topic_id for r in result])

    final_row_type = namedtuple('AckRow', ('user', 'grant', 'topic', 'ack_count'))
    return [
        final_row_type(UserWrapper(users.get(r.user_id)), grants.get(r.grant_id), topics.get(r.topic_id), r.ack_count)
        for r in result
    ]


def topic_content_acks_per_user(request):
    return render(request, 'tracker/topic_content_acks_per_user.html', {
        'acks': _get_topic_content_acks_per_user(),
    })


def topic_content_acks_per_user_csv(request):
    response = HttpResponseCsv(['user', 'grant', 'topic', 'ack_count'])
    for row in _get_topic_content_acks_per_user():
        response.writerow([row.user, row.grant, row.topic, row.ack_count])
    return response


def transaction_list(request):
    return render(request, 'tracker/transaction_list.html', {
        'transaction_list': Transaction.objects.all(),
        'total': Transaction.objects.aggregate(amount=models.Sum('amount'))['amount'],
    })


def transactions_csv(request):
    response = HttpResponseCsv(
        ['DATE', 'OTHER PARTY', 'AMOUNT ' + settings.TRACKER_CURRENCY, 'DESCRIPTION', 'TICKETS', 'GRANTS', 'ACCOUNTING INFO']
    )

    for tx in Transaction.objects.all():
        response.writerow([
            tx.date.strftime('%Y-%m-%d'),
            tx.other_party(),
            tx.amount,
            tx.description,
            u' '.join([t.id for t in tx.tickets.all()]),
            u' '.join([g.short_name for g in tx.grant_set()]),
            tx.accounting_info,
        ])
    return response


def user_list(request):
    totals = {
        'ticket_count': Ticket.objects.count(),
        'media_count': MediaInfoOld.objects.aggregate(media=Coalesce(models.Sum('count'), 0))['media'] + MediaInfo.objects.aggregate(objects=models.Count('id'))['objects'],
        'accepted_expeditures': sum([t.accepted_expeditures() for t in Ticket.objects.filter(rating_percentage__gt=0)]),
        'transactions': Expediture.objects.filter(paid=True).aggregate(amount=models.Sum('amount'))['amount'],
    }

    userless = Ticket.objects.filter(requested_user=None)

    if userless.count() > 0:
        unassigned = {
            'ticket_count': userless.count(),
            'media': MediaInfoOld.objects.extra(where=['ticket_id in (select id from tracker_ticket where requested_user_id is null)']).aggregate(objects=models.Count('id'), media=models.Sum('count')),
            'accepted_expeditures': sum([t.accepted_expeditures() for t in userless]),
        }
    else:
        unassigned = None

    return render(request, 'tracker/user_list.html', {
        'user_list': User.objects.all(),
        'unassigned': unassigned,
        'totals': totals,
    })


def user_detail(request, username):
    user = get_object_or_404(User, username=username)

    return render(request, 'tracker/user_detail.html', {
        'user_obj': user,
        # ^ NOTE 'user' means session user in the template, so we're using user_obj
        'ticket_list': user.ticket_set.all(),
    })


class UserDetailsChange(FormView):
    template_name = 'tracker/user_details_change.html'
    user_fields = ('first_name', 'last_name', 'email')
    profile_fields = [f.name for f in TrackerProfile._meta.fields if f.name not in ('id', 'user', 'mediawiki_username')]

    def make_user_details_form(self):
        fields = fields_for_model(User, fields=self.user_fields)
        fields['email'].required = True
        fields.update(fields_for_model(TrackerProfile, exclude=('user', 'mediawiki_username')))
        return type('UserDetailsForm', (forms.BaseForm,), {'base_fields': fields})

    def get_form_class(self):
        return self.make_user_details_form()

    def get_initial(self):
        user = self.request.user
        out = {}
        for f in self.user_fields:
            out[f] = getattr(user, f)
        for f in self.profile_fields:
            out[f] = getattr(user.trackerprofile, f)
        return out

    def form_valid(self, form):
        user = self.request.user
        for f in self.user_fields:
            setattr(user, f, form.cleaned_data[f])
        user.save()

        profile = user.trackerprofile
        for f in self.profile_fields:
            setattr(profile, f, form.cleaned_data[f])
        profile.save()

        messages.success(self.request, _('Your details have been saved.'))
        return HttpResponseRedirect(reverse('index'))


user_details_change = login_required(UserDetailsChange.as_view())


def cluster_detail(request, pk):
    id = int(pk)
    try:
        cluster = Cluster.objects.get(id=id)
    except Cluster.DoesNotExist:
        try:
            ticket = Ticket.objects.get(id=id)
            if ticket.cluster is None:
                raise Http404
            return HttpResponseRedirect(reverse('cluster_detail', kwargs={'pk': ticket.cluster.id}))
        except Ticket.DoesNotExist:
            raise Http404

    return render(request, 'tracker/cluster_detail.html', {
        'cluster': cluster,
        'ticket_summary': {'accepted_expeditures': cluster.total_tickets},
    })


class AdminUserListView(ListView):
    model = User
    template_name = 'tracker/admin_user_list.html'

    def get_context_data(self, **kwargs):
        context = super(AdminUserListView, self).get_context_data(**kwargs)
        context['is_tracker_supervisor'] = self.request.user.has_perm('tracker.supervisor')
        return context


admin_user_list = login_required(AdminUserListView.as_view())


def export(request):
    if request.method == 'POST':
        typ = request.POST['type']
        if typ == 'ticket':
            states = ['draft', 'wfpreapproval', 'wfsubmiting', 'wfapproval', 'wfdocssub', 'wffill', 'complete', 'archived', 'closed', 'custom']
            tickets = []
            for state in states:
                if state in request.POST:
                    tickets += Ticket.get_tickets_with_state(request.POST[state])
            if len(tickets) == 0:
                tickets = list(Ticket.objects.all())
            tickets = list(set(tickets))
            topics = []
            for item in request.POST:
                if item.startswith('ticket-topic-'):
                    topics.append(Topic.objects.get(id=int(request.POST[item])))
            tmp = []
            if len(topics) != 0:
                for topic in topics:
                    for ticket in tickets:
                        if ticket.topic == topic:
                            tmp.append(ticket)
                tickets = tmp
                tmp = []
            users = []
            for item in request.POST:
                if item.startswith('ticket-user-'):
                    users.append(User.objects.get(id=int(request.POST[item])))
            if len(users) != 0:
                for user in users:
                    for ticket in tickets:
                        if ticket.requested_user == user:
                            tmp.append(ticket)
                    tickets = tmp
                    tmp = []
            larger = request.POST['preexpeditures-larger']
            smaller = request.POST['preexpeditures-smaller']
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.preexpeditures()['amount']
                    if real is None:
                        real = 0
                    if real >= larger and real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger != '' and smaller == '':
                larger = int(larger)
                for ticket in tickets:
                    real = ticket.preexpeditures()['amount']
                    if real is None:
                        real = 0
                    if real >= larger:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.preexpeditures()['amount']
                    if real is None:
                        real = 0
                    if real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            larger = request.POST['expeditures-larger']
            smaller = request.POST['expeditures-smaller']
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.expeditures()['amount']
                    if real is None:
                        real = 0
                    if real >= larger and real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger != '' and smaller == '':
                larger = int(larger)
                for ticket in tickets:
                    real = ticket.expeditures()['amount']
                    if real is None:
                        real = 0
                    if real >= larger:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.expeditures()['amount']
                    if real is None:
                        real = 0
                    if real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            larger = request.POST['acceptedexpeditures-larger']
            smaller = request.POST['acceptedexpeditures-smaller']
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.accepted_expeditures()
                    if real >= larger and real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger != '' and smaller == '':
                larger = int(larger)
                for ticket in tickets:
                    real = ticket.accepted_expeditures()
                    if real >= larger:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                for ticket in tickets:
                    real = ticket.accepted_expeditures()
                    if real <= smaller:
                        tmp.append(ticket)
                tickets = tmp
                tmp = []
            mandatory_report = 'ticket-report-mandatory' in request.POST
            if mandatory_report:
                tmp = []
                for ticket in tickets:
                    if ticket.mandatory_report:
                        tmp.append(ticket)
                tickets = tmp
                del(tmp)
            response = HttpResponseCsv(['id', 'created', 'updated', 'event_date', 'event_url', 'name', 'requested_by', 'grant', 'topic', 'subtopic', 'state', 'deposit', 'description', 'mandatory_report', 'accepted_expeditures', 'preexpeditures', 'expeditures', 'paid_expeditures'])
            response['Content-Disposition'] = 'attachment; filename="exported-tickets.csv"'
            for ticket in tickets:
                response.writerow([ticket.id, ticket.created, ticket.updated, ticket.event_date, ticket.event_url, ticket.name, ticket.requested_by(), ticket.topic.grant.full_name, ticket.topic.name, str(ticket.subtopic), ticket.state_str(), ticket.deposit, ticket.description, ticket.mandatory_report, ticket.accepted_expeditures(), ticket.preexpeditures()['amount'], ticket.expeditures()['amount'], ticket.paid_expeditures()])
            return response
        elif typ == 'grant':
            response = HttpResponseCsv(['full_name', 'short_name', 'slug', 'description'])
            grants = Grant.objects.all()
            for grant in grants:
                response.writerow([grant.full_name, grant.short_name, grant.slug, grant.description])
            return response
        elif typ == 'preexpediture':
            larger = request.POST['preexpediture-amount-larger']
            smaller = request.POST['preexpediture-amount-larger']
            wage = 'preexpediture-wage' in request.POST
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                preexpeditures = Preexpediture.objects.filter(amount__gte=larger, amount__lte=smaller, wage=wage)
            elif larger != '' and smaller == '':
                larger = int(larger)
                preexpeditures = Preexpediture.objects.filter(amount__gte=larger, wage=wage)
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                preexpeditures = Preexpediture.objects.filter(amount__lte=smaller, wage=wage)
            else:
                preexpeditures = Preexpediture.objects.filter(wage=wage)
            response = HttpResponseCsv(['ticket_id', 'description', 'amount', 'wage'])
            response['Content-Disposition'] = 'attachment; filename="exported-preexpeditures.csv"'
            for preexpediture in preexpeditures:
                response.writerow([preexpediture.ticket_id, preexpediture.description, preexpediture.amount, preexpediture.wage])
            return response
        elif typ == 'expediture':
            larger = request.POST['expediture-amount-larger']
            smaller = request.POST['expediture-amount-smaller']
            wage = 'expediture-wage' in request.POST
            paid = 'expediture-paid' in request.POST
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                expeditures = Expediture.objects.filter(amount__gte=larger, amount__lte=smaller, wage=wage, paid=paid)
            elif larger != '' and smaller == '':
                larger = int(larger)
                expeditures = Expediture.objects.filter(amount__gte=larger, wage=wage, paid=paid)
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                expeditures = Expediture.objects.filter(amount__lte=smaller, wage=wage, paid=paid)
            else:
                expeditures = Expediture.objects.filter(wage=wage, paid=paid)
            response = HttpResponseCsv(['ticket_id', 'description', 'amount', 'wage', 'paid'])
            response['Content-Disposition'] = 'attachment; filename="exported-expeditures.csv"'
            for expediture in expeditures:
                response.writerow([expediture.ticket_id, expediture.description, expediture.amount, expediture.wage, expediture.paid])
            return response
        elif typ == 'topic':
            users = []
            for item in request.POST:
                if item.startswith('topics-user-'):
                    users.append(User.objects.get(id=int(request.POST[item])))
            topics = Topic.objects.all()
            if len(users) != 0:
                tmp = []
                for user in users:
                    for topic in topics:
                        if user in topic.admin.all():
                            tmp.append(topic)
                topics = list(set(tmp))
                tmp = []
            larger = request.POST['topics-tickets-larger']
            smaller = request.POST['topics-tickets-smaller']
            if larger != '' and smaller != '':
                larger = int(larger)
                smaller = int(smaller)
                tmp = []
                for topic in topics:
                    if topic.ticket_set.count >= larger and topic.ticket_set.count <= smaller:
                        tmp.append(topic)
                topics = tmp
                tmp = []
            elif larger != '' and smaller == '':
                larger = int(larger)
                tmp = []
                for topic in topics:
                    if topic.ticket_set.count >= larger:
                        tmp.append(topic)
                topics = tmp
                tmp = []
            elif larger == '' and smaller != '':
                smaller = int(smaller)
                tmp = []
                for topic in topics:
                    if topic.ticket_set.count <= smaller:
                        tmp.append(topic)
                topics = tmp
                tmp = []
            if request.POST['topics-paymentstate'] != 'default':
                paymentstatus = request.POST['topics-paymentstate']
                larger = request.POST['topics-paymentstate-larger']
                smaller = request.POST['topics-paymentstate-smaller']
                if larger != '' and smaller != '':
                    larger = int(larger)
                    smaller = int(smaller)
                    tmp = []
                    for topic in topics:
                        number = -1
                        if paymentstatus in topic.tickets_per_payment_status():
                            number = topic.tickets_per_payment_status()[paymentstatus]
                        else:
                            number = 0
                        if number >= larger and number <= smaller:
                            tmp.append(topic)
                    topics = tmp
                    del(tmp)
                elif larger != '' and smaller == '':
                    larger = int(larger)
                    tmp = []
                    for topic in topics:
                        number = -1
                        if paymentstatus in topic.tickets_per_payment_status():
                            number = topic.tickets_per_payment_status()[paymentstatus]
                        else:
                            number = 0
                        if number >= larger:
                            tmp.append(topic)
                    topics = tmp
                    del(tmp)
                elif larger == '' and smaller != '':
                    smaller = int(smaller)
                    tmp = []
                    for topic in topics:
                        number = -1
                        if paymentstatus in topic.tickets_per_payment_status():
                            number = topic.tickets_per_payment_status()[paymentstatus]
                        else:
                            number = 0
                        if number <= smaller:
                            tmp.append(topic)
                    topics = tmp
                    del(tmp)
            response = HttpResponseCsv(['name', 'grant', 'open_for_new_tickets', 'media', 'expenses', 'preexpenses', 'description', 'form_description', 'admins'])
            response['Content-Disposition'] = 'attachment; filename="exported-topics.csv"'
            for topic in topics:
                names = []
                for ad in topic.admin.all():
                    names.append(ad.username)
                admins = ", ".join(names)
                response.writerow([topic.name, topic.grant.full_name, topic.open_for_tickets, topic.ticket_media, topic.ticket_expenses, topic.ticket_preexpenses, topic.description, topic.form_description, admins])
            return response
        elif typ == 'user':
            if request.user.is_authenticated:
                if request.user.is_staff:
                    users = TrackerProfile.objects.all()
                    larger = request.POST['users-created-larger']
                    smaller = request.POST['users-created-smaller']
                    if larger != '' and smaller != '':
                        larger = int(larger)
                        smaller = int(smaller)
                        tmp = []
                        for user in users:
                            real = user.count_ticket_created()
                            if real >= larger and real <= smaller:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger != '' and smaller == '':
                        larger = int(larger)
                        tmp = []
                        for user in users:
                            real = user.count_ticket_created()
                            if real >= larger:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger == '' and smaller != '':
                        smaller = int(smaller)
                        tmp = []
                        for user in users:
                            real = user.count_ticket_created()
                            if real <= smaller:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    larger = request.POST['users-accepted-larger']
                    smaller = request.POST['users-accepted-smaller']
                    if larger != '' and smaller != '':
                        larger = int(larger)
                        smaller = int(smaller)
                        tmp = []
                        for user in users:
                            real = user.accepted_expeditures()
                            if real >= larger and real <= smaller:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger != '' and smaller == '':
                        larger = int(larger)
                        tmp = []
                        for user in users:
                            real = user.accepted_expeditures()
                            if real >= larger:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger == '' and smaller != '':
                        smaller = int(smaller)
                        tmp = []
                        for user in users:
                            real = user.accepted_expeditures()
                            if real <= smaller:
                                tmp.append(user)
                        users = tmp
                        del(tmp)

                    larger = request.POST['users-paid-larger']
                    smaller = request.POST['users-paid-larger']
                    if larger != '' and smaller != '':
                        larger = int(larger)
                        smaller = int(larger)
                        tmp = []
                        for user in users:
                            real = user.paid_expeditures()
                            if real >= larger and real <= smaller:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger != '' and smaller == '':
                        larger = int(larger)
                        tmp = []
                        for user in users:
                            real = user.paid_expeditures()
                            if real >= larger:
                                tmp.append(user)
                        users = tmp
                        del(tmp)
                    elif larger == '' and smaller != '':
                        smaller = int(smaller)
                        tmp = []
                        for user in users:
                            real = user.paid_expeditures()
                            if real <= smaller:
                                tmp.append(user)
                            users = tmp
                            del(tmp)

                    if 'user-permision' in request.POST:
                        priv = request.POST['user-permision']
                        tmp = []
                        if priv == 'normal':
                            for user in users:
                                if not user.user.is_staff and not user.user.is_superuser:
                                    tmp.append(user)
                        elif priv == 'staff':
                            for user in users:
                                if user.user.is_staff:
                                    tmp.append(user)
                        elif priv == 'superuser':
                            for user in users:
                                if user.user.is_superuser:
                                    tmp.append(user)
                        else:
                            return HttpResponseBadRequest('You must fill the form validly')
                        users = tmp
                        del(tmp)

                    response = HttpResponseCsv(['id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined', 'created_tickets', 'accepted_expeditures', 'paid_expeditures', 'bank_account', 'other_contact', 'other_identification'])
                    response['Content-Disposition'] = 'attachment; filename="exported-users.csv"'
                    for user in users:
                        response.writerow([user.user.id, user.user.username, user.user.first_name, user.user.last_name, user.user.email, user.user.is_active, user.user.is_staff, user.user.is_superuser, user.user.last_login, user.user.date_joined, user.count_ticket_created(), user.accepted_expeditures(), user.paid_expeditures(), user.bank_account, user.other_contact, user.bank_account])
                    return response
            raise PermissionDenied('You must be staffer in order to export users')

        return HttpResponseBadRequest(_('You must fill the form validly'))
    else:
        return render(
            request,
            'tracker/export.html',
            {
                'topics': Topic.objects.all(),
                'users': User.objects.all(),
                'tickets': Ticket.objects.all(),
            })


@login_required
def importcsv(request):
    if request.method == 'POST' and not request.FILES['csvfile']:
        return render(request, 'tracker/import.html')
    elif request.method == 'POST' and request.FILES['csvfile']:
        import_limit = settings.MAX_NUMBER_OF_ROWS_ON_IMPORT
        import_unlimited = not import_limit
        too_much_rows_message = _('You do not have permission to import more than %(input_row_limit)s rows. First %(input_row_limit)s rows have already been imported.') % {'input_row_limit': str(import_limit)}
        imported = 0
        csvfile = TextIOWrapper(request.FILES['csvfile'].file, encoding=request.encoding)
        header = None
        with csvfile:
            reader = csv.reader(csvfile, delimiter=';', quotechar='"')
            header = next(reader)
            imported = 0
            if request.POST['type'] == 'ticket':
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    event_date = line[header.index('event_date')]
                    if event_date == "None":
                        event_date = None
                    name = line[header.index('name')]
                    topic = Topic.objects.filter(name=line[header.index('topic')])[0]
                    event_url = line[header.index('event_url')]
                    description = line[header.index('description')]
                    deposit = float(line[header.index('deposit')])
                    ticket = Ticket.objects.create(event_date=event_date, name=name, topic=topic, event_url=event_url, description=description, deposit=deposit)
                    ticket.requested_user = request.user
                    ticket.save()
            elif request.POST['type'] == 'topic':
                if not request.user.is_staff:
                    raise PermissionDenied('You must be a staffer in order to be able to import topics.')
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    name = line[header.index('name')]
                    grant = Grant.objects.get(full_name=line[header.index('grant')]).id
                    new_tickets = line[header.index('open_for_new_tickets')]
                    if new_tickets == "False":
                        new_tickets = False
                    else:
                        new_tickets = True
                    media = line[header.index('media')]
                    if media == "False":
                        media = False
                    else:
                        media = True
                    preexpenses = line[header.index('preexpenses')]
                    if preexpenses == "False":
                        preexpenses = False
                    else:
                        preexpenses = True
                    expenses = line[header.index('expenses')]
                    if expenses == "False":
                        expenses = False
                    else:
                        expenses = True
                    description = line[header.index('description')]
                    form_description = line[header.index('form_description')]
                    Topic.objects.create(name=name, grant_id=grant, open_for_tickets=new_tickets, ticket_media=media, ticket_preexpenses=preexpenses, ticket_expenses=expenses, description=description, form_description=form_description)
            elif request.POST['type'] == 'grant':
                if not request.user.is_staff:
                    raise PermissionDenied('You must be a staffer in order to be able to import grants.')
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    full_name = line[header.index('full_name')]
                    short_name = line[header.index('short_name')]
                    slug = line[header.index('slug')]
                    description = line[header.index('description')]
                    Grant.objects.create(full_name=full_name, short_name=short_name, slug=slug, description=description)
            elif request.POST['type'] == 'expense':
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    ticket = Ticket.objects.get(id=line[header.index('ticket_id')])
                    description = line[header.index('description')]
                    amount = line[header.index('amount')]
                    wage = line[header.index('wage')]
                    if request.user.is_staff:
                        accounting_info = line[header.index('accounting_info')]
                        paid = line[header.index('paid')]
                    else:
                        accounting_info = ''
                        paid = False
                    if ticket.can_edit(request.user) or request.user.is_staff:
                        Expediture.objects.create(ticket=ticket, description=description, amount=amount, wage=wage, accounting_info=accounting_info, paid=paid)
                    else:
                        raise PermissionDenied("You can't add preexpenses to a ticket that you did not create.")
            elif request.POST['type'] == 'preexpense':
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    ticket = Ticket.objects.get(id=line[header.index('ticket_id')])
                    description = line[header.index('description')]
                    amount = line[header.index('amount')]
                    wage = line[header.index('wage')]
                    if ticket.can_edit(request.user) or request.user.is_staff:
                        Preexpediture.objects.create(ticket=ticket, description=description, amount=amount, wage=wage)
                    else:
                        raise PermissionDenied("You can't add preexpenses to a ticket that you did not create.")
            elif request.POST['type'] == 'media':
                for line in reader:
                    imported += 1
                    if (imported > import_limit and not import_unlimited) and not request.user.has_perm('tracker.import_unlimited_rows'):
                        messages.warning(request, too_much_rows_message)
                        break
                    ticket = Ticket.objects.get(id=line[header.index('ticket_id')])
                    name = line[header.index('name')]
                    if ticket.can_edit(request.user) or request.user.is_staff:
                        MediaInfo.objects.create(ticket=ticket, name=name)
                        ticket.save()
                    else:
                        raise PermissionDenied("You can't add media items to a ticket that you did not create.")
            elif request.POST['type'] == 'user':
                if not request.user.is_superuser:
                    raise PermissionDenied('You must be a superuser in order to be able to import users.')
                for line in reader:
                    username = line[header.index('username')]
                    password = line[header.index('password')]
                    first_name = line[header.index('first_name')]
                    last_name = line[header.index('last_name')]
                    is_superuser = line[header.index('is_superuser')]
                    is_staff = line[header.index('is_staff')]
                    is_active = line[header.index('is_active')]
                    email = line[header.index('email')]
                    user = User.objects.create_user(username=username, password=password, email=email)
                    user.first_name = first_name
                    user.last_name = last_name
                    user.is_superuser = is_superuser
                    user.is_staff = is_staff
                    user.is_active = is_active
                    user.save()
            else:
                messages.error(request, _('The form has returned strange values. Please contact the systemadmin and tell him what you tried to do.'))
                return render(request, 'tracker/import.html', {})
        messages.success(request, _('Your CSV file was imported.'))
        return HttpResponseRedirect(reverse('index'))
    else:
        if 'examplefile' in request.GET:
            giveexample = request.GET['examplefile']
            if giveexample == 'ticket':
                response = HttpResponseCsv(['event_date', 'name', 'topic', 'event_url', 'description', 'deposit'])
                response['Content-Disposition'] = 'attachment; filename="example-ticket.csv"'
                response.writerow([u'2010-04-23', _('Name of a ticket'), _('Name of a topic'), u'http://wikimedia.cz', _('Description'), u'0'])
                return response
            elif giveexample == 'topic':
                response = HttpResponseCsv(['name', 'grant', 'open_for_new_tickets', 'media', 'preexpenses', 'expenses', 'description', 'form_description'])
                response['Content-Disposition'] = 'attachment; filename="example-topic.csv"'
                response.writerow([_('Name of a topic'), _('Name of a grant'), u'True', u'True', u'True', u'True', _('Description'), _('Form description')])
                return response
            elif giveexample == 'grant':
                response = HttpResponseCsv(['full_name', 'short_name', 'slug', 'description'])
                response['Content-Disposition'] = 'attachment; filename="example-grant.csv"'
                response.writerow([_('Full name'), _('Short name'), _('Slug'), _('Description')])
                return response
            elif giveexample == 'expense':
                fields = ['ticket_id', 'description', 'amount', 'wage']
                if request.user.is_staff:
                    fields.append('accounting_info')
                    fields.append('paid')
                response = HttpResponseCsv(fields)
                response['Content-Disposition'] = 'attachment; filename="example-expense.csv"'
                row = [_('Ticket ID'), _('Description'), u'100', u'False']
                if request.user.is_staff:
                    row.append(_('Accounting info'))
                    row.append(u'False')
                response.writerow(row)
                return response
            elif giveexample == 'preexpense':
                response = HttpResponseCsv(['ticket_id', 'description', 'amount', 'wage'])
                response['Content-Disposition'] = 'attachment; filename="example-preexpense.csv"'
                response.writerow([_('Ticket ID'), _('Description'), u'100', u'False'])
                return response
            elif giveexample == 'user':
                response = HttpResponseCsv(['username', 'password', 'first_name', 'last_name', 'is_superuser', 'is_staff', 'is_active', 'email'])
                response['Content-Disposition'] = 'attachment; filename="example-user.csv"'
                response.writerow([_('Username'), _('Password'), _('First name'), _('Last name'), u'False', u'False', u'True', u'mail@address.example'])
                return response
            elif giveexample == 'media':
                response = HttpResponseCsv(['ticket_id', 'name'])
                response['Content-Disposition'] = 'attachment; filename="example-media.csv"'
                response.writerow([_('Ticket ID'), 'File:Name.jpg'])
                return response
            else:
                return HttpResponseBadRequest("You can't download an example file of an invalid object")
        else:
            return render(request, 'tracker/import.html', {'MAX_NUMBER_OF_ROWS_ON_IMPORT': settings.MAX_NUMBER_OF_ROWS_ON_IMPORT})


@login_required
def copypreexpeditures(request, pk):
    ticket = get_object_or_404(Ticket, id=pk)
    if not ticket.can_edit(request.user) or 'content' in ticket.ack_set():
        raise PermissionDenied('You cannot edit this')
    for e in ticket.expediture_set.all():
        e.delete()
    for pe in ticket.preexpediture_set.all():
        e = Expediture.objects.create(ticket=ticket, description=pe.description, amount=pe.amount, wage=pe.wage)
    messages.success(request, _('Preexpeditures were succesfully copied to expeditures.'))
    return HttpResponseRedirect(ticket.get_absolute_url())


@csrf_exempt
def mediawiki_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
    else:
        data = request.GET

    if data.get('action') not in ('query', ):
        raise PermissionDenied(_('Executing API call with any action than whitelisted is prohibited.'))

    user = None
    if request.user.is_authenticated:
        user = request.user
    return HttpResponse(MediaWiki(user=user).request(payload=data, method=request.method).content, content_type='application/json')


def show_media(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    if ticket.mediainfo_set.count() == 0:
        raise PermissionDenied(_('No media to show are available'))
    wikidata_usages = []
    for m in ticket.mediainfo_set.all():
        for usage in m.usages:
            if usage[2] == "www.wikidata.org":
                wikidata_usages.append(usage[1])
    return render(request, 'tracker/ticket_show_media.html', {
        'ticket': ticket,
        'medias': ticket.mediainfo_set.all(),
        'usages_count': sum([len(m.usages) for m in ticket.mediainfo_set.all()]),
        'wikidata_usages_count': len(wikidata_usages),
        'unique_wikidata_usages_count': len(set(wikidata_usages)),
        'photos_per_category': ticket.photos_per_category(),
        'MEDIAINFO_MEDIAWIKI_ARTICLE': settings.MEDIAINFO_MEDIAWIKI_ARTICLE,
    })


@login_required
def update_media(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)  # this is here to ensure 404 when ticket doesn't exist
    Ticket.update_media(ticket.id)
    messages.success(request, _('Updating of medias for this ticket was successfully scheduled.'))
    return HttpResponseRedirect(reverse('show_media', kwargs={"ticket_id": ticket_id}))


def update_media_success(request, ticket_id):
    messages.success(request, _('List of media was successfully updated'))
    return HttpResponseRedirect(reverse('ticket_detail', kwargs={"pk": ticket_id}))


def update_media_error(request, ticket_id):
    messages.error(request, _('There was an error while processing your request'))
    return HttpResponseRedirect(reverse('ticket_detail', kwargs={"pk": ticket_id}))


@csrf_exempt
def email_all_users(request):
    if request.GET.get('token') != settings.MAIL_ALL_TOKEN:
        raise PermissionDenied()
    mail_html = request.POST['body-html'] + "<hr><small>" + _('This mandatory notice was sent to all active Tracker users.') + "</small>"
    mail_text = strip_tags(mail_html)
    mail_subject = '[Tracker] ' + request.POST['Subject']
    for u in User.objects.filter(is_active=True):
        u.email_user(mail_subject, mail_text, html_message=mail_html)
    return HttpResponse('Ok')


@csrf_exempt
def email_all_admins(request):
    if request.GET.get('token') != settings.MAIL_ALL_TOKEN:
        raise PermissionDenied()
    mail_html = request.POST['body-html'] + "<hr><small>" + _('This mandatory notice was sent to all active Tracker administrators.') + "</small>"
    mail_text = strip_tags(mail_html)
    mail_subject = '[Tracker] ' + request.POST['Subject']
    users = set()
    for topic in Topic.objects.filter(open_for_tickets=True):
        for u in topic.admin.filter(is_active=True):
            users.add(u)

    for u in users:
        u.email_user(mail_subject, mail_text, html_message=mail_html)

    return HttpResponse('Ok')
