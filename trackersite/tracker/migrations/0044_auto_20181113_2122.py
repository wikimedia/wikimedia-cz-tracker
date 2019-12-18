# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0043_trackerpreferences_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='Watcher',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='created', null=True)),
                ('watcher_type', models.CharField(max_length=50, verbose_name=b'watcher_type', blank=True)),
                ('object_id', models.PositiveIntegerField(null=True)),
                ('notification_type', models.CharField(max_length=50, verbose_name=b'notification_type', choices=[(b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_change', 'Expeditures changed'), (b'media_change', 'Media changed')])),
                ('ack_type', models.CharField(max_length=50, null=True, verbose_name=b'ack_type', choices=[(b'user_precontent', 'presubmitted'), (b'precontent', 'preaccepted'), (b'user_content', 'submitted'), (b'content', 'accepted'), (b'user_docs', 'expense documents submitted'), (b'docs', 'expense documents filed'), (b'archive', 'archived'), (b'close', 'closed')])),
                ('content_type', models.ForeignKey(to='contenttypes.ContentType', null=True, on_delete=models.SET_NULL)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
