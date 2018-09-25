# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0034_merge'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notification',
            name='ticket',
        ),
    ]
