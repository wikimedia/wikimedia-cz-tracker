# -*- coding: utf-8 -*-
import json

from django.conf.urls import url
from django.contrib import admin
from django import forms
from tracker import models
from django.utils.translation import ugettext_lazy as _, get_language, activate
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.template.loader import get_template
from django.contrib.admin.helpers import ActionForm


class MediaInfoAdmin(admin.TabularInline):
    model = models.MediaInfo
    fields = ('name', 'width', 'height')
    readonly_fields = ('width', 'height')


class ExpeditureAdmin(admin.TabularInline):
    model = models.Expediture


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
    inlines = [SignatureAdmin, MediaInfoAdmin, PreexpeditureAdmin, ExpeditureAdmin]
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
        context['adminform'].form.fields['subtopic'].queryset = models.Subtopic.objects.filter(topic=self.ticket.topic)
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

    list_display = ('name', 'grant', 'open_for_tickets', 'ticket_media', 'ticket_expenses', 'ticket_preexpenses', 'ticket_statutory_declaration')
    list_filter = ('grant', 'open_for_tickets', 'ticket_media', 'ticket_expenses', 'ticket_preexpenses', 'ticket_statutory_declaration')
    filter_horizontal = ('admin', )
    actions = (open_topics_for_tickets, close_topics_for_tickets)


admin.site.register(models.Topic, TopicAdmin)


class GrantAdminForm(forms.ModelForm):
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
    readonly_fields = ('mediawiki_username', 'user')
    list_display = ('user', 'bank_account', 'other_contact', 'other_identification')


admin.site.register(models.TrackerProfile, TrackerProfileAdmin)

# piggypatch admin site to display our own index template with some bonus links
admin.site.index_template = 'tracker/admin_index_override.html'
