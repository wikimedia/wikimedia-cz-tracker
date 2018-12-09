# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0058_make_ticket_event_data_timezone_aware'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='trackerprofile',
            options={'verbose_name': 'Tracker profile', 'verbose_name_plural': 'Tracker profiles', 'permissions': (('bypass_disabled_comments', 'Can post comments even if they are not enabled.'), ('import_unlimited_rows', 'Can import more than a hundred rows at a time.'))},
        ),
    ]
