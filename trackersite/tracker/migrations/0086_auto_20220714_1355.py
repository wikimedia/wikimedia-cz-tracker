# Generated by Django 3.0.14 on 2022-07-14 11:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0085_auto_20220714_1349'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mediainfousage',
            name='url',
            field=models.URLField(help_text='Link to file usage', max_length=512, verbose_name='URL'),
        ),
    ]