# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0045_auto_20181114_0935'),
    ]

    operations = [
        migrations.DeleteModel(
            name='TicketWatcher',
        ),
        migrations.DeleteModel(
            name='TopicWatcher',
        ),
    ]
