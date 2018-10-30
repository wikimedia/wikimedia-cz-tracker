# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0039_auto_20181028_1835'),
    ]

    operations = [
        migrations.AddField(
            model_name='cluster',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='expediture',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='grant',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='preexpediture',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='subtopic',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='ticketack',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='ticketwatcher',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='topic',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='topicwatcher',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AddField(
            model_name='transaction',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created', null=True),
        ),
    ]
