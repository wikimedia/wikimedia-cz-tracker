# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0037_auto_20181010_1140'),
    ]

    operations = [
        migrations.RenameField('Ticket', 'summary', 'name')
    ]
