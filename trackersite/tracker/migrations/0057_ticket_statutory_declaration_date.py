# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0056_auto_20181203_2333'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='statutory_declaration_date',
            field=models.DateTimeField(default=None, null=True, verbose_name='Date when statutory declaration was made'),
        ),
    ]
