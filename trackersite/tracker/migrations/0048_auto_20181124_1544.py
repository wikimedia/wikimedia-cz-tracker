# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0047_auto_20181119_2153'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='trackerprofile',
            options={'verbose_name': 'Tracker profile', 'verbose_name_plural': 'Tracker profiles', 'permissions': (('bypass_disabled_comments', 'Can post comments even if they are not enabled.'),)},
        ),
    ]
