# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.conf import settings
import os.path
import json
from django.utils import translation
from tracker.models import Ticket


class Command(BaseCommand):
    help = 'Cache tickets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-path',
            action='store',
            dest='base_path',
            help='We will save the cached tickets to this path, default is TRACKER_PUBLIC_DEPLOY_ROOT'
        )
        parser.add_argument(
            '--do-archived',
            action='store_true',
            dest='do_archived',
            help='We will update cache for both unarchived and archived tickets.'
        )

    def handle(self, *args, **options):
        base_path = options['base_path'] or os.path.join(settings.TRACKER_PUBLIC_DEPLOY_ROOT, 'tickets')
        base_path_dirs = ('archived', )
        if not os.path.exists(base_path):
            os.mkdir(base_path)
        for dir in base_path_dirs:
            if not os.path.exists(os.path.join(base_path, dir)):
                os.mkdir(os.path.join(base_path, dir))
        archived_tickets = {}
        if not options['do_archived']:
            for langcode, langname in settings.LANGUAGES:
                archived_path = os.path.join(base_path, 'archived', '%s.json' % langcode)
                if os.path.exists(archived_path):
                    archived_tickets[langcode] = json.loads(open(archived_path).read())
                else:
                    options['do_archived'] = True   # we don't have archived tickets cached yet, we must do that now
                    break

        if options['do_archived']:
            for langcode, langname in settings.LANGUAGES:
                with translation.override(langcode):
                    archived_tickets[langcode] = [ticket.get_cached_ticket() for ticket in Ticket.objects.filter(is_completed=True).order_by('-id')]
                    open(os.path.join(base_path, 'archived', '%s.json' % langcode), 'w').write(json.dumps(
                        archived_tickets[langcode]
                    ))

        for langcode, langname in settings.LANGUAGES:
            with translation.override(langcode):
                open(os.path.join(base_path, '%s.json' % langcode), 'w').write(json.dumps({
                    "data": archived_tickets[langcode] + [ticket.get_cached_ticket() for ticket in Ticket.objects.filter(is_completed=False).order_by('-id')]
                }))
