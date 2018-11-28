# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0051_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(blank=True, max_length=6, verbose_name='Email language', choices=[(b'en', 'English (en)'), (b'cs_CZ', 'Czech (cs)')]),
        ),
    ]
