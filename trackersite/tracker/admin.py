# -*- coding: utf-8 -*-
import json

from django.conf.urls import url
from django.contrib import admin
from django import forms
from django.forms.formsets import DELETION_FIELD_NAME
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from tracker.services import PaymentService
from tracker.fio import FioPaymentManager
from tracker import models
from django.utils.translation import ugettext_lazy as _, get_language, activate
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.template.loader import get_template
from django.contrib.admin.helpers import ActionForm
from django.urls import reverse

from tracker.views import ExpediturePaymentMixin
from tracker.validators import validate_full_bank_account


class MediaInfoAdmin(admin.TabularInline):
    model = models.MediaInfo
    fields = ('page_title', 'width', 'height')
    readonly_fields = ('width', 'height')


class ExpeditureInlineFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)

        if self.can_delete and DELETION_FIELD_NAME in form.fields:
            if form.instance and form.instance.pk:
                is_internal = form.instance.payment_type == models.PaymentType.INTERNAL_TRANSFER

                if form.instance.paid or is_internal:
                    form.fields[DELETION_FIELD_NAME].disabled = True

    def clean(self):
        super().clean()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                instance = form.instance
                if instance.pk:
                    is_internal = instance.payment_type == models.PaymentType.INTERNAL_TRANSFER

                    if instance.paid or is_internal:
                        raise forms.ValidationError(
                            _('Cannot delete expenditure #%(id)s: It is either an internal transfer or already paid.')
                            % {'id': instance.pk}
                        )


class ExpeditureAdminForm(ExpediturePaymentMixin):
    AUTOMATED_PAYMENT_TYPES = (
        models.PaymentType.BANK_TRANSFER,
        models.PaymentType.INTERNAL_TRANSFER,
        models.PaymentType.INCOME,
        models.PaymentType.CARD
    )

    template_choice = forms.ModelChoiceField(
        queryset=models.Template.objects.all(),
        required=False,
        label=_('Load from a template')
    )

    class Meta:
        model = models.Expediture
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_payment_fields()

        if 'account_number' in self.fields:
            self.fields['account_number'].label = _('Or enter manually:')

        templates = models.Template.objects.all()
        templates_data = {}
        for t in templates:
            templates_data[t.id] = {
                'saved_account': t.saved_account_id or '',
                'account_number': t.account_number or '',
                'variable_symbol': t.variable_symbol or '',
                'specific_symbol': t.specific_symbol or '',
                'constant_symbol': t.constant_symbol or '',
                'amount': str(t.amount) if t.amount else '',
            }

        self.fields['template_choice'].widget.attrs['data-templates'] = json.dumps(templates_data)

        if 'payment_type' in self.fields:
            choices = [c for c in models.PaymentType.choices if c[0] != models.PaymentType.INCOME]
            self.fields['payment_type'].choices = choices

        if self.instance and self.instance.payment_type in self.AUTOMATED_PAYMENT_TYPES and 'paid' in self.fields:
            self.fields['paid'].disabled = True

        is_imported = self.instance.import_info and self.instance.import_info.imported_at and not self.instance.import_info.error
        is_internal = self.instance.payment_type == models.PaymentType.INTERNAL_TRANSFER

        if self.instance.paid or is_imported:
            for field_name, field in self.fields.items():
                field.disabled = True

        elif is_internal:
            for field_name, field in self.fields.items():
                if field_name != 'accounting_info':
                    field.disabled = True

    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')

        if account_number:
            validate_full_bank_account(account_number)

        return account_number

    def save(self, commit=True):
        expenditure = super(forms.ModelForm, self).save(commit=False)

        if self.instance.payment_type in self.AUTOMATED_PAYMENT_TYPES:
            expenditure = self.save_payment_details(expenditure, commit=False)

        if commit:
            if getattr(expenditure, 'payment_info', None) and expenditure.payment_type == models.PaymentType.BANK_TRANSFER:
                expenditure.payment_info.save()

            expenditure.save()

        return expenditure


class ExpeditureAdmin(admin.StackedInline):
    model = models.Expediture
    form = ExpeditureAdminForm
    formset = ExpeditureInlineFormSet
    exclude = ('payment_info',)
    extra = 0
    readonly_fields = ('get_linked_ticket_link',)

    fieldsets = (
        (None, {
            'fields': (
                ('template_choice', 'description', 'amount', 'wage', 'payment_type', 'accounting_info', 'paid', 'get_linked_ticket_link'),
            )
        }),
        (_('Payment Details (Bank Transfer)'), {
            'classes': ('collapse',),
            'fields': (
                ('saved_account', 'account_number'),
                ('variable_symbol', 'specific_symbol', 'constant_symbol')
            )
        })
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(payment_type=models.PaymentType.INCOME)

    def get_linked_ticket_link(self, obj):
        if obj.pk and obj.linked_expenditure:
            ticket_id = obj.linked_expenditure.ticket_id
            ticket_url = reverse('admin:tracker_ticket_change', args=[ticket_id])
            return format_html('<a href="{}" style="font-weight: bold; color: #0088cc;">Linked ticket #{}</a>', ticket_url, ticket_id)
        return "-"

    get_linked_ticket_link.short_description = _('Linked Co-financing')


class CofinancingAdminForm(forms.ModelForm):
    cofinance_filter_grant = forms.ModelChoiceField(queryset=models.Grant.objects.all(), required=False, label=_('Filter by Grant'))
    cofinance_source_ticket = forms.ModelChoiceField(queryset=models.Ticket.objects.all(), required=False, label=_('Source ticket'))
    cofinance_source_account = forms.ChoiceField(choices=[], required=False, label=_('Source account'))
    cofinance_amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False, label=_('Amount'))

    class Meta:
        model = models.Expediture
        fields = ('cofinance_filter_grant', 'cofinance_source_ticket', 'cofinance_source_account', 'cofinance_amount')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available_accounts = FioPaymentManager.get_available_accounts()
        self.fields['cofinance_source_account'].choices = [('', '---------')] + [(acc, acc) for acc in available_accounts]

        tickets = models.Ticket.objects.select_related('topic__grant').all()
        mapping = {t.id: t.topic.grant_id for t in tickets if t.topic and t.topic.grant_id}
        self.fields['cofinance_source_ticket'].widget.attrs['data-ticket-grants'] = json.dumps(mapping)

        if self.instance and self.instance.pk:
            self.fields['cofinance_amount'].initial = abs(self.instance.amount) if self.instance.amount else None

            if self.instance.linked_expenditure:
                source_ticket_id = self.instance.linked_expenditure.ticket_id
                self.fields['cofinance_source_ticket'].initial = source_ticket_id

                source_ticket = models.Ticket.objects.filter(id=source_ticket_id).select_related('topic__grant').first()
                if source_ticket and source_ticket.topic and source_ticket.topic.grant_id:
                    self.fields['cofinance_filter_grant'].initial = source_ticket.topic.grant_id

            elif self.instance.description and "account " in self.instance.description:
                parts = self.instance.description.split("account ")
                if len(parts) > 1:
                    self.fields['cofinance_source_account'].initial = parts[1].strip()

            is_imported = self.instance.import_info and self.instance.import_info.imported_at and not self.instance.import_info.error

            if self.instance.paid or is_imported:
                for field_name, field in self.fields.items():
                    field.disabled = True

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get('DELETE'):
            source_ticket = cleaned_data.get('cofinance_source_ticket')
            source_account = cleaned_data.get('cofinance_source_account')
            cof_amount = cleaned_data.get('cofinance_amount')

            if not cof_amount or cof_amount <= 0:
                self.add_error('cofinance_amount', _('You must enter a positive amount for co-financing.'))
            if not source_ticket and not source_account:
                raise forms.ValidationError(_('You must select either a source ticket or a source account.'))
            if source_ticket and source_account:
                raise forms.ValidationError(_('Choose only one co-financing source, not both.'))

        return cleaned_data

    def save(self, commit=True):
        expenditure = super().save(commit=False)
        expenditure.payment_type = models.PaymentType.INCOME

        source_ticket = self.cleaned_data.get('cofinance_source_ticket')
        source_account = self.cleaned_data.get('cofinance_source_account')
        cof_amount = self.cleaned_data.get('cofinance_amount')

        expenditure = PaymentService.process_cofinancing_link(
            expenditure, source_ticket, source_account, cof_amount, commit=commit
        )

        return expenditure


class CofinancingAdmin(admin.StackedInline):
    model = models.Expediture
    form = CofinancingAdminForm
    formset = ExpeditureInlineFormSet
    extra = 0
    verbose_name = _('Co-financing')
    verbose_name_plural = _('Co-financings')

    readonly_fields = ('get_linked_ticket',)

    fieldsets = (
        (None, {
            'fields': (
                ('cofinance_filter_grant', 'cofinance_source_ticket', 'cofinance_source_account', 'cofinance_amount', 'get_linked_ticket'),
            )
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(payment_type=models.PaymentType.INCOME)

    def get_linked_ticket(self, obj):
        if obj.pk and obj.linked_expenditure:
            ticket_id = obj.linked_expenditure.ticket_id
            ticket_url = reverse('admin:tracker_ticket_change', args=[ticket_id])
            return format_html('<a href="{}" style="font-weight: bold; color: #0088cc;">Linked ticket #{}</a>',
                               ticket_url, ticket_id)
        return "-"

    get_linked_ticket.short_description = _('Linked ticket')


class PreexpeditureAdmin(admin.TabularInline):
    model = models.Preexpediture


class AddAckForm(forms.Form):
    ack_type = forms.ChoiceField(choices=models.ACK_TYPES, label=_('Type'))
    comment = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={'size': '40'}))
    locale = forms.CharField(required=False, max_length=255, widget=forms.HiddenInput())


class AddAckActionForm(ActionForm):
    ack_type = forms.ChoiceField(required=False, choices=models.ACK_TYPES, label=_('Type'))


def add_ack(modeladmin, request, queryset):
    for ticket in queryset.all():
        ticket.ticketack_set.create(ack_type=request.POST['ack_type'], added_by=request.user)


add_ack.short_description = _('Add ack')


class SignatureAdmin(admin.TabularInline):
    model = models.Signature
    fields = ('created', 'user', 'signed_text')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class TicketAdmin(admin.ModelAdmin):
    def queryset(self, request):
        qs = super(TicketAdmin, self).queryset(request)
        if request.user.has_perm('tracker.supervisor'):
            return qs
        else:
            return qs.extra(where=['topic_id in (select topic_id from tracker_topic_admin where user_id = %s)'], params=[request.user.id])

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        self.ticket = self.get_object(request, object_id)

        if self.ticket is None:
            raise Http404

        extra_context['user_can_edit_documents'] = self.ticket.is_editable(request.user)
        extra_context['user_can_see_all_documents'] = self.ticket.can_see_all_documents(request.user)
        extra_context['add_ack_form'] = AddAckForm()
        return super(TicketAdmin, self).change_view(request, object_id, extra_context=extra_context)

    exclude = ('media_updated', 'updated', 'cluster', 'payment_status', 'imported', 'is_completed')
    readonly_fields = ('state_str', 'requested_user_details')
    list_display = ('event_date', 'id', 'name', 'subtopic', 'admin_topic', 'requested_by', 'state_str')
    list_display_links = ('name',)
    list_filter = ('topic', 'subtopic', 'payment_status')
    date_hierarchy = 'event_date'
    search_fields = ['id', 'requested_user__username', 'requested_text', 'name']
    inlines = [SignatureAdmin, MediaInfoAdmin, PreexpeditureAdmin, ExpeditureAdmin, CofinancingAdmin]
    action_form = AddAckActionForm
    actions = (add_ack, )

    @staticmethod
    def _render(request, template_name, context_data, locale=None):
        curr_lang = get_language()
        if locale is not None and locale in [x[0] for x in models.LANGUAGE_CHOICES]:
            try:
                activate(locale)
                rendered = get_template(template_name).render(context_data)
            finally:
                activate(curr_lang)
        else:
            rendered = get_template(template_name).render(context_data)
        return rendered

    def add_ack(self, request, object_id):
        ticket = models.Ticket.objects.get(id=object_id)
        if (request.method == 'POST'):
            form = AddAckForm(request.POST)
            if form.is_valid():
                if form.cleaned_data['ack_type'] == 'content' and ticket.rating_percentage is None:
                    return HttpResponse(json.dumps({
                        'form': self._render(request, 'admin/tracker/ticket/ack_norating_error.html', {}),
                        'id': -1,
                        'success': False,
                    }))
                if form.cleaned_data['ack_type'] == 'content' and ticket.mandatory_report and ticket.report_url == '':
                    return HttpResponse(json.dumps({
                        'form': self._render(request, 'admin/tracker/ticket/ack_noreport_error.html', {}),
                        'id': -1,
                        'success': False,
                    }))
                ack = ticket.ticketack_set.create(ack_type=form.cleaned_data['ack_type'], added_by=request.user, comment=form.cleaned_data['comment'])
                return HttpResponse(json.dumps({
                    'form': self._render(request, 'admin/tracker/ticket/ack_line.html', {'ack': ack}, locale=form.cleaned_data['locale']),
                    'id': ack.id,
                    'success': True,
                }))
        else:
            form = AddAckForm()
        form_html = self._render(request, 'admin/tracker/ticket/add_ack.html', {'form': form})
        return HttpResponse(json.dumps({'form': form_html}))

    def remove_ack(self, request, object_id):
        ticket = models.Ticket.objects.get(id=object_id)
        if (request.method != 'POST'):
            return HttpResponseNotAllowed(['POST'])
        try:
            ack = ticket.ticketack_set.get(id=request.POST.get('id', None))
        except models.TicketAck.DoesNotExist:
            raise Http404
        ack.delete()
        return HttpResponse(json.dumps({
            'success': True,
        }))

    def get_urls(self):
        return [
            url(r'^(?P<object_id>\d+)/acks/add/$', self.add_ack),
            url(r'^(?P<object_id>\d+)/acks/remove/$', self.remove_ack),
        ] + super(TicketAdmin, self).get_urls()

    def save_model(self, request, obj, form, change):
        obj.save(saved_from_admin=True)

    def render_change_form(self, request, context, *args, **kwargs):
        obj = kwargs.get('obj')

        if obj and hasattr(obj, 'topic') and obj.topic:
            context['adminform'].form.fields['subtopic'].queryset = models.Subtopic.objects.filter(topic=obj.topic)
        else:
            context['adminform'].form.fields['subtopic'].queryset = models.Subtopic.objects.none()

        return super(TicketAdmin, self).render_change_form(request, context, *args, **kwargs)


admin.site.register(models.Ticket, TicketAdmin)


class SubtopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'topic')
    list_filter = ('topic', )


admin.site.register(models.Subtopic, SubtopicAdmin)


def open_topics_for_tickets(modeladmin, request, queryset):
    queryset.update(open_for_tickets=True)


open_topics_for_tickets.short_description = _("Mark selected topics as opened for new tickets")


def close_topics_for_tickets(modeladmin, request, queryset):
    queryset.update(open_for_tickets=False)


close_topics_for_tickets.short_description = _("Mark selected topics as closed for new tickets")


class TopicAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if request.user.has_perm('tracker.supervisor'):
            return ()
        else:
            return ('admin', 'grant')

    def queryset(self, request):
        if request.user.has_perm('tracker.supervisor'):
            return super(TopicAdmin, self).queryset(request)
        else:
            return request.user.topic_set.all()

    list_display = ('name', 'grant', 'open_for_tickets', 'ticket_media', 'ticket_expenses', 'ticket_preexpenses', 'ticket_statutory_declaration', 'ticket_comments_public')
    list_filter = ('grant', 'open_for_tickets', 'ticket_media', 'ticket_expenses', 'ticket_preexpenses', 'ticket_statutory_declaration', 'ticket_comments_public')
    filter_horizontal = ('admin', )
    actions = (open_topics_for_tickets, close_topics_for_tickets)


admin.site.register(models.Topic, TopicAdmin)


class GrantAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available_accounts = FioPaymentManager.get_available_accounts()
        account_choices = [('', '---------')] + [(acc, acc) for acc in available_accounts]

        self.fields['source_bank_account'] = forms.ChoiceField(
            choices=account_choices,
            required=False,
            label=_('Source bank account'),
            help_text=_('Number of the transparent account from which the funds will be disbursed')
        )

    class Meta:
        model = models.Grant
        help_texts = {'open_for_tickets': _('Modify this value by opening or closing topics in this grant to tickets')}
        exclude = []


class GrantAdmin(admin.ModelAdmin):
    form = GrantAdminForm
    prepopulated_fields = {'slug': ('short_name',)}
    readonly_fields = ('open_for_tickets',)
    list_display = ('full_name', 'open_for_tickets')


admin.site.register(models.Grant, GrantAdmin)


class TrackerProfileAdmin(admin.ModelAdmin):
    readonly_fields = ('mediawiki_username', 'chapter_username', 'user')
    list_display = ('user', 'bank_account', 'other_contact', 'other_identification')


admin.site.register(models.TrackerProfile, TrackerProfileAdmin)


class TemplateAdmin(admin.ModelAdmin):
    list_display = ('template_name', 'amount', 'get_target_account', 'variable_symbol', 'specific_symbol', 'constant_symbol')
    fieldsets = (
        (_('Main Template Info'), {
            'description': _('You can use templates to quickly create new expenditures. Payment data will be automatically filled in for you.'),
            'fields': ('template_name', 'amount')
        }),
        (_('Payment Destination'), {
            'description': _('Specify the recipient account. You must choose exactly one way to specify the account: either a saved account OR enter it manually.'),
            'fields': ('saved_account', 'account_number')
        }),
        (_('Symbols'), {
            'description': _('Optional payment symbols.'),
            'fields': ('variable_symbol', 'specific_symbol', 'constant_symbol')
        }),
    )


admin.site.register(models.Template, TemplateAdmin)

# piggypatch admin site to display our own index template with some bonus links
admin.site.index_template = 'tracker/admin_index_override.html'
