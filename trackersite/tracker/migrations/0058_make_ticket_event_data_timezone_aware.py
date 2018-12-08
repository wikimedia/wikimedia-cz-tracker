# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from pytz import timezone
from django.db import migrations, models


def make_ticket_timezone_aware(apps, schema_editor):
    Ticket = apps.get_model('tracker', 'Ticket')
    localtz = timezone('Europe/Prague')
    for ticket in Ticket.objects.all():
        try:
            ticket.updated = localtz.localize(ticket.updated)
        except ValueError:
            # Ticket already has a timezone
            pass
        else:
            ticket.save()


def make_ticket_timezone_unaware(apps, schema_editor):
    Ticket = apps.get_model('tracker', 'Ticket')
    for ticket in Ticket.objects.all():
        ticket.updated = ticket.updated.replace(tzinfo=None)
        ticket.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0057_ticket_statutory_declaration_date'),
    ]

    operations = [
        migrations.RunPython(make_ticket_timezone_aware, make_ticket_timezone_unaware)
    ]
