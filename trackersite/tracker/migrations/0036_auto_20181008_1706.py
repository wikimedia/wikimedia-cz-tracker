# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0035_remove_notification_ticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='car_travel',
            field=models.BooleanField(default=False, help_text='Did you travel by car?', verbose_name='car travel'),
        ),
        migrations.AddField(
            model_name='topic',
            name='ticket_statutory_declaration',
            field=models.BooleanField(default=False, help_text='Does this topic require statutory declaration for car travelling?', verbose_name='ticket statutory declaration'),
        ),
    ]
