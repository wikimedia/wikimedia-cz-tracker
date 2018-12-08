from django.core.management.base import NoArgsCommand
from django.conf import settings
import os.path
import json
from django.utils import translation
from tracker.templatetags.trackertags import money
from django.utils.html import escape
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
                tickets = []
                for ticket in Ticket.objects.order_by('-id'):
                    subtopic = ticket.subtopic
                    if subtopic:
                        subtopic = '<a href="%s">%s</a>' % (ticket.subtopic.get_absolute_url(), ticket.subtopic)
                    else:
                        subtopic = ''
                    tickets.append([
                        '<a href="%s">%s</a>' % (ticket.get_absolute_url(), ticket.pk),
                        unicode(ticket.event_date),
                        '<a class="ticket-summary" href="%s">%s</a>' % (ticket.get_absolute_url(), escape(ticket.name)),
                        '<a href="%s">%s</a>' % (ticket.topic.grant.get_absolute_url(), ticket.topic.grant),
                        '<a href="%s">%s</a>' % (ticket.topic.get_absolute_url(), ticket.topic),
                        subtopic,
                        ticket.requested_by_html(),
                        money(ticket.preexpeditures()['amount'] or 0),
                        money(ticket.accepted_expeditures()),
                        money(ticket.paid_expeditures()),
                        unicode(ticket.state_str()),
                        unicode(ticket.updated),
                    ])
                open(os.path.join(base_path, '%s.json' % langcode), 'w').write(json.dumps({"data": tickets}))
