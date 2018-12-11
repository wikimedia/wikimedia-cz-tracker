# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

def archive_mediainfo(apps, schema_editor):
    MediaInfo = apps.get_model('tracker', 'MediaInfo')
    MediaInfoOld = apps.get_model('tracker', 'MediaInfoOld')

    for media in MediaInfo.objects.all():
        MediaInfoOld.objects.create(
            ticket=media.ticket,
            description=media.description,
            url=media.url,
            count=media.count
        )
        media.delete()

def restore_mediainfo(apps, schema_editor):
    MediaInfo = apps.get_model('tracker', 'MediaInfo')
    MediaInfoOld = apps.get_model('tracker', 'MediaInfoOld')

    for media_old in MediaInfoOld.objects.all():
        MediaInfo.objects.create(
            ticket=media_old.ticket,
            description=media_old.description,
            url=media_old.url,
            count=media_old.count
        )
        media_old.delete()

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0060_mediainfoold'),
    ]

    operations = [
        migrations.RunPython(archive_mediainfo, restore_mediainfo)
    ]
