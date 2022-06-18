from django.core.management.base import BaseCommand
from tracker.models import Ticket


class Command(BaseCommand):
    help = 'Schedule updating of MediaInfo of all unarchived tickets'

    def handle(self, *args, **options):
        for ticket in Ticket.objects.all():
            acks = ticket.ack_set()
            if 'archive' not in acks and 'close' not in acks and ticket.mediainfo_set.all().count() > 0:
                Ticket.update_media(ticket.id)
