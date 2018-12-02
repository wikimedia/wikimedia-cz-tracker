# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0052_auto_20181130_1158'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackerprofile',
            name='mediawiki_username',
            field=models.CharField(max_length=120, verbose_name='Username on mediawiki', blank=True),
        ),
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(blank=True, max_length=6, verbose_name='Email language', choices=[(b'en', 'English'), (b'cs', 'Czech')]),
        ),
    ]
