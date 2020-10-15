from django.core.management.base import BaseCommand
from tracker.models import Ticket


class Command(BaseCommand):
    help = 'Schedule updating of all tickets'

    def handle(self, *args, **options):
        for ticket in Ticket.objects.all():
            if 'archive' not in ticket.ack_set():
                Ticket.update_media(ticket.id)
