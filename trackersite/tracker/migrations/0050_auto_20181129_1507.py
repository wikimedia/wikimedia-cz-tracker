# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0049_auto_20181129_1443'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trackerpreferences',
            name='language',
        ),
        migrations.AddField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(max_length=6, verbose_name='Email language', blank=True),
        ),
    ]
