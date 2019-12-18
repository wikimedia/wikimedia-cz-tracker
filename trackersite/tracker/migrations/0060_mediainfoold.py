# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0059_auto_20181209_1915'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaInfoOld',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='created', null=True)),
                ('description', models.CharField(help_text='Item description to show', max_length=255, verbose_name='description')),
                ('url', models.URLField(help_text='Link to media files', verbose_name='URL', blank=True)),
                ('count', models.PositiveIntegerField(help_text='Number of files', null=True, verbose_name='count', blank=True)),
                ('ticket', models.ForeignKey(verbose_name='ticket', to='tracker.Ticket', help_text='Ticket this media info belongs to', on_delete=models.CASCADE)),
            ],
            options={
                'verbose_name': 'Ticket media',
                'verbose_name_plural': 'Ticket media',
            },
        ),
    ]
