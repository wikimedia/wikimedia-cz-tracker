# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0032_auto_20180830_1112'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='enable_comments',
            field=models.BooleanField(default=True, help_text='Can users comment on this ticket?', verbose_name='enable comments'),
        ),
    ]
