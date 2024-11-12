# Generated by Django 3.0.14 on 2024-11-12 13:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0087_auto_20231208_1924'),
    ]

    operations = [
        migrations.AddField(
            model_name='expediture',
            name='archived',
            field=models.BooleanField(default=False, help_text='This is only editable through the admin', verbose_name='archived'),
        ),
    ]
