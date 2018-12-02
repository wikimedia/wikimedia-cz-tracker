# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0054_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(max_length=50, null=True, verbose_name=b'notification_type', choices=[(b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_change', 'Expeditures changed'), (b'media_change', 'Media changed'), (b'muted', 'No notifications')]),
        ),
        migrations.AlterField(
            model_name='watcher',
            name='notification_type',
            field=models.CharField(max_length=50, verbose_name=b'notification_type', choices=[(b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_change', 'Expeditures changed'), (b'media_change', 'Media changed'), (b'muted', 'No notifications')]),
        ),
    ]
