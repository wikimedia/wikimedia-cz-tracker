from django.core.management.base import NoArgsCommand
from tracker.models import Ticket


class Command(NoArgsCommand):
    help = 'Schedule updating of all tickets'

    def handle_noargs(self, **options):
        for ticket in Ticket.objects.all():
            if 'archive' not in ticket.ack_set():
                Ticket.update_medias(ticket.id)
