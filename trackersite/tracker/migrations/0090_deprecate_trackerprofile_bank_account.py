# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0089_auto_20260515_1132'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trackerprofile',
            name='bank_account',
            field=models.CharField(blank=True, editable=False, help_text='Bank account information for money transfers', max_length=120, verbose_name='Bank account'),
        ),
    ]
