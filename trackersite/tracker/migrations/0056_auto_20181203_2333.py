# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0055_auto_20181202_2244'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(max_length=50, null=True, verbose_name=b'notification_type', choices=[(b'muted', 'All notifications'), (b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_new', 'New preexpediture was created'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_new', 'New expediture was created'), (b'expeditures_change', 'Expeditures changed'), (b'media_new', 'New media was created'), (b'media_change', 'Media changed')]),
        ),
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(default=b'cs', max_length=6, verbose_name='Email language', choices=[(b'en', 'English'), (b'cs', 'Czech')]),
        ),
        migrations.AlterField(
            model_name='watcher',
            name='notification_type',
            field=models.CharField(max_length=50, verbose_name=b'notification_type', choices=[(b'muted', 'All notifications'), (b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_new', 'New preexpediture was created'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_new', 'New expediture was created'), (b'expeditures_change', 'Expeditures changed'), (b'media_new', 'New media was created'), (b'media_change', 'Media changed')]),
        ),
    ]
