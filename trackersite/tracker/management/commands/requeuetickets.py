from django.core.management.base import BaseCommand, CommandError
from tracker.models import Ticket, MediaInfo
from os import getcwd, path
from django.conf import settings


class Command(BaseCommand):
    help = 'Re-triggers add_to_mediawiki for specified ticket(s)'

    def add_arguments(self, parser):
        parser.add_argument('ticket_ids', nargs='*', type=int)
        parser.add_argument('--ticket-id-file', type=str)

    def handle(self, *args, **options):
        ticket_ids = []

        if options['ticket_ids']:
            ticket_ids = options['ticket_ids']

        if options['ticket_id_file']:
            full_file_path = path.join(getcwd(), options['ticket_id_file'])
            self.stdout.write('Reading ticket ids from file %s...' % full_file_path)
            with open(full_file_path, 'r') as file:
                for line in file:
                    if line.strip().isnumeric():
                        ticket_ids.append(int(line.strip()))

        self.stdout.write('Got %s ticket ids. Processing...' % str(len(ticket_ids)))
        for ticket_id in ticket_ids:
            try:
                for mediainfo in MediaInfo.objects.filter(ticket_id=ticket_id):
                    MediaInfo.add_to_mediawiki(mediainfo.id, settings.TRACKER_MAINTENANCE_USER_ID)

            except Ticket.DoesNotExist:
                raise CommandError('Ticket %s does not exist' % ticket_id)
        self.stdout.write('Done.')
