# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0068_tracker_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='is_completed',
            field=models.BooleanField(default=False, verbose_name='Is this ticket completed?'),
        )
    ]
