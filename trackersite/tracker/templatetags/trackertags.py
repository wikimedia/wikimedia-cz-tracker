# -*- coding: utf-8 -*-
from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
from django.utils.formats import number_format
from django.urls import reverse
import re
import bleach
from tracker.models import Ticket, User


register = template.Library()


@register.filter
def money(value):
    if value == 0 or value == '' or value is None:
        return ''
    else:
        out = number_format(value, 2)
    return mark_safe(u'%s&nbsp;%s' % (out, settings.TRACKER_CURRENCY))


@register.filter
def safe_html(value):
    return mark_safe(bleach.clean(value, settings.ALLOWED_TAGS, settings.ALLOWED_ATTRIBUTES))


@register.filter
def tracker_rich_text(value):
    for match in re.findall(r"(#[0-9]+)([ ,.;)\]]|$)", value, re.MULTILINE):
        try:
            ticket_id = int(match[0][1:])
        except ValueError:
            continue
        if not Ticket.objects.filter(id=ticket_id).exists():
            continue

        ticket = Ticket.objects.get(id=ticket_id)
        text = '<a href="%s">%s</a>' % (ticket.get_absolute_url(), "%s: %s" % (match[0], ticket.name))
        value = value.replace(match[0], text)

    usersmentioned = re.findall(r'@([-a-zA-Z0-9_.]+)', value)
    for user_name in usersmentioned:
        users = User.objects.filter(username=user_name)
        if len(users) == 1:
            user_detail_url = reverse('user_detail', kwargs={'username': users[0].username})
            value = value.replace('@%s' % user_name, '<a href="%s">@%s</a>' % (user_detail_url, user_name))

    links = re.findall(r'[^\"](https?://[a-zA-Z.,0-9/%:_?&#=-]+)', value)
    for link in links:
        value = value.replace(link, '<a href="%s">%s</a>' % (link, link))

    return mark_safe(value)


# Get sum of preexpediture amount, functions are used in admin/tabular.html
@register.filter
def get_total_preex(value, identificator):
    value = Ticket.objects.get(id=int(identificator.strip())).preexpeditures_amount()
    return value


# Get sum of expediture amount
@register.filter
def get_total_ex(value, identificator):
    value = Ticket.objects.get(id=int(identificator.strip())).expeditures_amount()
    return value


@register.filter
def get_accepted_expeditures(value, identificator):
    accepted = Ticket.objects.get(id=int(identificator.strip())).accepted_expeditures()
    return accepted
