# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0061_auto_20181209_1943'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mediainfo',
            name='count',
        ),
        migrations.RemoveField(
            model_name='mediainfo',
            name='description',
        ),
        migrations.RemoveField(
            model_name='mediainfo',
            name='url',
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='categories',
            field=jsonfield.fields.JSONField(default=[], verbose_name='categories'),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='height',
            field=models.IntegerField(null=True, verbose_name='height'),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='name',
            field=models.CharField(max_length=255, verbose_name='name', blank=True),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='updated',
            field=models.DateTimeField(null=True, verbose_name='updated'),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='usages',
            field=jsonfield.fields.JSONField(default=[], verbose_name='usages'),
        ),
        migrations.AddField(
            model_name='mediainfo',
            name='width',
            field=models.IntegerField(null=True, verbose_name='width'),
        ),
    ]
