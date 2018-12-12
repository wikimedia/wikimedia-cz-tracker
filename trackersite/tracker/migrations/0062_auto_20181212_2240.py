# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0061_migrate_statutory_declarations'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ticket',
            name='statutory_declaration',
        ),
        migrations.RemoveField(
            model_name='ticket',
            name='statutory_declaration_date',
        ),
    ]
