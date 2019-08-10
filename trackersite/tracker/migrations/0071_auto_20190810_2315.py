# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0070_populate_is_completed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(max_length=50, null=True, verbose_name=b'notification_type', choices=[(b'muted', 'All notifications'), (b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_new', 'New preexpediture was created'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_new', 'New expediture was created'), (b'expeditures_change', 'Expeditures changed'), (b'media_new', 'New media was created'), (b'media_change', 'Media changed'), (b'document', 'Document changed')]),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='description',
            field=models.TextField(help_text="Space for further notes. If you're entering a trip tell us where did you go and what you did there. You can link to another tickets by adding #ticketid in your description. You may use a limited subset of HTML.", verbose_name='description', blank=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='media_updated',
            field=models.DateTimeField(default=None, help_text='Date when cached information about media were last updated. Used in "show media" view.', null=True, verbose_name='media updated'),
        ),
        migrations.AlterField(
            model_name='trackerpreferences',
            name='email_language',
            field=models.CharField(default=b'cs', max_length=6, verbose_name='Email language', choices=[(b'en', 'English'), (b'cs', 'Czech'), (b'fr', 'French'), (b'ar', 'Arabic'), (b'da', 'Danish'), (b'fi', 'Finnish'), (b'ko', 'Korean'), (b'pt', 'Portuguese'), (b'sv', 'Swedish')]),
        ),
        migrations.AlterField(
            model_name='watcher',
            name='notification_type',
            field=models.CharField(max_length=50, verbose_name=b'notification_type', choices=[(b'muted', 'All notifications'), (b'comment', 'Comment added'), (b'supervisor_notes', 'Supervisor notes changed'), (b'ticket_new', 'New ticket was created'), (b'ticket_delete', 'Ticket was deleted'), (b'ack_add', 'Ack added'), (b'ack_remove', 'Ack removed'), (b'ticket_change', 'Ticket changed'), (b'preexpeditures_new', 'New preexpediture was created'), (b'preexpeditures_change', 'Preexpeditures changed'), (b'expeditures_new', 'New expediture was created'), (b'expeditures_change', 'Expeditures changed'), (b'media_new', 'New media was created'), (b'media_change', 'Media changed'), (b'document', 'Document changed')]),
        ),
    ]
