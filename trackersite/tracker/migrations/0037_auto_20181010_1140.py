# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0036_auto_20181008_1706'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='statutory_declaration',
            field=models.BooleanField(default=False, help_text=b'I hereby declare that my travel expenses are true and accurate and that your phototrip is according to the principles of the project Fot\xc3\xadme \xc4\x8cesko / MediaGrant (economity, quality, effectiveness and ecologity.', verbose_name='Statutory declaration'),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='car_travel',
            field=models.BooleanField(default=False, help_text='Do you request reimbursement of car-type travel expense?', verbose_name='Did you travel by car?'),
        ),
        migrations.AlterField(
            model_name='topic',
            name='ticket_statutory_declaration',
            field=models.BooleanField(default=False, help_text='Does this topic require statutory declaration for car travelling?', verbose_name='require statutory declaration'),
        ),
    ]
