# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0038_auto_20181017_1919'),
    ]

    operations = [
        migrations.AddField(
            model_name='subtopic',
            name='form_description',
            field=models.TextField(help_text='Description shown to users who enter tickets for this subtopic', verbose_name='form description', blank=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='name',
            field=models.CharField(help_text='Name for the ticket', max_length=100, verbose_name='name'),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='statutory_declaration',
            field=models.BooleanField(default=False, help_text=b'I hereby declare that my travel expenses are true and accurate and that you spent money economically and effectivelly.', verbose_name='Statutory declaration'),
        ),
    ]
