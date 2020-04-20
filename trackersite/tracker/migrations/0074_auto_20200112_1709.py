# Generated by Django 3.0.1 on 2020-01-12 16:09

import django.core.files.storage
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0073_auto_20191223_1358'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='payload',
            field=models.FileField(storage=django.core.files.storage.FileSystemStorage(location='/home/urbanecm/unsynced/gerrit/wikimedia-cz/tracker/deploy/private'), upload_to='tickets/%Y/'),
        ),
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(choices=[('en', 'English'), ('cs', 'Czech'), ('fr', 'French'), ('ar', 'Arabic'), ('da', 'Danish'), ('fi', 'Finnish'), ('ko', 'Korean'), ('pt', 'Portuguese'), ('sv', 'Swedish'), ('zh-hant', 'Chinese-traditional'), ('es', 'Spanish')], default='cs', max_length=7, verbose_name='Email language'),
        ),
        migrations.CreateModel(
            name='MediaInfoUsage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(help_text='Link to file usage', verbose_name='URL')),
                ('title', models.CharField(max_length=255, verbose_name='title')),
                ('project', models.CharField(max_length=255, verbose_name='project')),
                ('mediainfo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tracker.MediaInfo')),
            ],
        ),
        migrations.CreateModel(
            name='MediaInfoCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='title')),
                ('mediainfo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tracker.MediaInfo')),
            ],
        ),
    ]