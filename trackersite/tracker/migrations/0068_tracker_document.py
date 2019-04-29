# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0067_auto_20190106_1946'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='content_type',
            field=models.CharField(max_length=100),
        ),
    ]
