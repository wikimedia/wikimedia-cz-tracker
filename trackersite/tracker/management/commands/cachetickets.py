from django.core.management.base import NoArgsCommand
from django.conf import settings
import os.path
import json
from django.utils import translation
from tracker.models import Ticket


class Command(NoArgsCommand):
    help = 'Cache tickets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-path',
            action='store',
            dest='base_path',
            help='We will save the cached tickets to this path, default is TRACKER_PUBLIC_DEPLOY_ROOT'
        )

    def handle(self, *args, **options):
        base_path = options['base_path'] or os.path.join(settings.TRACKER_PUBLIC_DEPLOY_ROOT, 'tickets')

        for langcode, langname in settings.LANGUAGES:
            with translation.override(langcode):
                open(os.path.join(base_path, '%s.json' % langcode), 'w').write(json.dumps({
                    "data": [ticket.get_cached_ticket() for ticket in Ticket.objects.order_by('-id')]
                }))
