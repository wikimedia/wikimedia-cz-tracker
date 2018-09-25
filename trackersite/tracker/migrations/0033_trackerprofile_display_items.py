# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0032_auto_20180830_1112'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackerprofile',
            name='display_items',
            field=models.IntegerField(default=25, help_text='How many items should we display in tables at once', verbose_name='Display items'),
        ),
    ]
