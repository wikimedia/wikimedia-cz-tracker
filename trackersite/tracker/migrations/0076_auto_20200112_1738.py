# Generated by Django 3.0.1 on 2020-01-12 16:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0075_auto_20200112_1710'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mediainfo',
            name='categories',
        ),
        migrations.RemoveField(
            model_name='mediainfo',
            name='usages',
        ),
    ]