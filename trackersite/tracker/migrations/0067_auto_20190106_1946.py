# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0066_auto_20190104_0953'),
    ]

    operations = [
        migrations.AddField(
            model_name='mediainfo',
            name='canonicaltitle',
            field=models.CharField(max_length=255, null=True, verbose_name='cannonical title'),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='thumb_url',
            field=models.URLField(max_length=500, null=True, verbose_name='URL', blank=True),
        ),
    ]
