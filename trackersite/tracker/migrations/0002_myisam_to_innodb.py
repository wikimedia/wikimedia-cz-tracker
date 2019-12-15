# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

original_myisam_tables = (
    'auth_group',
    'auth_group_permissions',
    'auth_permission',
    'auth_user',
    'auth_user_groups',
    'auth_user_user_permissions',
    'django_admin_log',
    'django_comment_flags',
    'django_comments',
    'django_content_type',
    'django_session',
    'django_site',
    'tracker_cluster',
    'tracker_document',
    'tracker_expediture',
    'tracker_grant',
    'tracker_mediainfo',
    'tracker_ticket',
    'tracker_ticketack',
    'tracker_topic',
    'tracker_topic_admin',
    'tracker_trackerprofile',
    'tracker_transaction',
    'tracker_transaction_tickets',
)

def forwards(apps, schema_editor):
    if not schema_editor.connection.vendor.startswith('mysql'):
        return

    for query in ['ALTER TABLE {} ENGINE=InnoDB'.format(table) for table in original_myisam_tables]:
        schema_editor.execute(query)

def backwards(apps, schema_editor):
    if not schema_editor.connection.vendor.startswith('mysql'):
        return

    for query in ['ALTER TABLE {} ENGINE=MyISAM'.format(table) for table in original_myisam_tables]:
        schema_editor.execute(query)

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, atomic=False)
    ]
