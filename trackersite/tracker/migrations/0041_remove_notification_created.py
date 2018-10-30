# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0040_auto_20181030_1747'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notification',
            name='created',
        ),
    ]
