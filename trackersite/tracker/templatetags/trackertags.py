# -*- coding: utf-8 -*-
from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
from django.utils.formats import number_format
from tracker.models import Ticket
import re

register = template.Library()


@register.filter
def money(value):
    if value == 0:
        out = '0'
    else:
        out = number_format(value, 2)
    return mark_safe(u'%s&nbsp;%s' % (out, settings.TRACKER_CURRENCY))


@register.filter
def tracker_rich_text(value):
    value_new = value
    for match in re.findall(r"#[0-9]+", value):
        try:
            ticket_id = int(match[1:])
        except ValueError:
            continue
        if not Ticket.objects.filter(id=ticket_id).exists():
            continue

        ticket = Ticket.objects.get(id=ticket_id)
        text = '<a href="%s">%s</a>' % (ticket.get_absolute_url(), "%s: %s" % (match, ticket.name))
        value_new = value_new.replace(match, text)
    return mark_safe(value_new)
