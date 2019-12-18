# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0062_auto_20181212_2240'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='uploader',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL),
        ),
    ]
