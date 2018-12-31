# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

def squash_classes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    TopicWatcher = apps.get_model('tracker', 'TopicWatcher')
    TicketWatcher = apps.get_model('tracker', 'TicketWatcher')
    Watcher = apps.get_model('tracker', 'Watcher')
    for watch in TopicWatcher.objects.all():
        Watcher.objects.create(watcher_type='Topic', content_type=ContentType.objects.get_for_model(watch.topic), object_id=watch.topic.id, user=watch.user, notification_type=watch.notification_type, ack_type=watch.ack_type)
    for watch in TicketWatcher.objects.all():
        Watcher.objects.create(watcher_type='Ticket', content_type=ContentType.objects.get_for_model(watch.ticket), object_id=watch.ticket.id, user=watch.user, notification_type=watch.notification_type, ack_type=watch.ack_type)

def expand_classes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    TopicWatcher = apps.get_model('tracker', 'TopicWatcher')
    TicketWatcher = apps.get_model('tracker', 'TicketWatcher')
    Watcher = apps.get_model('tracker', 'Watcher')
    for watch in Watcher.objects.filter(watcher_type='Topic'):
        TopicWatcher.objects.create(topic=apps.get_model('tracker', watch.content_type.model).objects.get(id=watch.object_id), user=watch.user, notification_type=watch.notification_type, ack_type=watch.ack_type)
    for watch in Watcher.objects.filter(watcher_type='Ticket'):
        TicketWatcher.objects.create(ticket=apps.get_model('tracker', watch.content_type.model).objects.get(id=watch.object_id), user=watch.user, notification_type=watch.notification_type, ack_type=watch.ack_type)

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0044_auto_20181113_2122'),
    ]

    operations = [
        migrations.RunPython(squash_classes, expand_classes),
    ]
