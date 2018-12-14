# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

def set_uploader(apps, schema_editor):
    Document = apps.get_model('tracker', 'Document')

    for doc in Document.objects.all():
        doc.uploader = doc.ticket.requested_user
        doc.save()

def unset_uploader(apps, schema_editor):
    pass # dummy migration to allow unapplying

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0063_document_uploader'),
    ]

    operations = [
        migrations.RunPython(set_uploader, unset_uploader)
    ]
