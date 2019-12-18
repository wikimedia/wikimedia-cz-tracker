# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0065_merge'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mediainfo',
            name='updated',
        ),
        migrations.AddField(
            model_name='ticket',
            name='media_updated',
            field=models.DateTimeField(default=None, null=True, verbose_name='media_updated'),
        ),
        migrations.AlterField(
            model_name='preexpediture',
            name='ticket',
            field=models.ForeignKey(verbose_name='ticket', to='tracker.Ticket', help_text='Ticket this preexpediture belongs to', on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(default=b'cs', max_length=6, verbose_name='Email language', choices=[(b'en', 'English'), (b'cs', 'Czech'), (b'fr', 'French'), (b'ar', 'Arabic'), (b'da', 'Danish')]),
        ),
    ]
