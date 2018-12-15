# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


def statutory_declarations_to_extra_object(apps, schema_editor):
    Ticket = apps.get_model('tracker', 'Ticket')
    Signature = apps.get_model('tracker', 'Signature')

    for t in Ticket.objects.all():
        if t.requested_user is not None and t.statutory_declaration:
            Signature.objects.create(signed_ticket=t, signed_text=settings.STATUTORY_DECLARATION_TEXT, user=t.requested_user, created=t.statutory_declaration_date)

def statutory_declarations_to_ticket(apps, schema_editor):
    Signature = apps.get_model('tracker', 'Signature')

    for s in Signature.objects.all():
        t = s.signed_ticket
        if t.requested_user == s.user:
            t.car_travel = True
            t.statutory_declaration = True
            t.statutory_declaration_date = s.created
            t.save()

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0060_signature'),
    ]

    operations = [
        migrations.RunPython(statutory_declarations_to_extra_object, statutory_declarations_to_ticket)
    ]
