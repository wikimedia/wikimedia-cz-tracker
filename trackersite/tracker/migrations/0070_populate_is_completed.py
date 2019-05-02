# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

def populate_is_completed(apps, schema_editor):
    Ticket = apps.get_model('tracker', 'Ticket')

    for ticket in Ticket.objects.all():
        acks = set([x.ack_type for x in ticket.ticketack_set.only('ack_type')])
        ticket.is_completed = ('archive' in acks) or ('close' in acks)
        ticket.save()

def unpopulate_is_completed(apps, schema_editor):
    pass # dummy migration to allow unapplying

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0069_ticket_is_completed'),
    ]

    operations = [
        migrations.RunPython(populate_is_completed, unpopulate_is_completed)
    ]
