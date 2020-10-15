from __future__ import print_function
from django.core.management.base import BaseCommand
from tracker.models import Grant


class Command(BaseCommand):
    help = 'List available grants'

    def handle(self, *args, **options):
        for g in Grant.objects.all():
            print(g.id, g.short_name, g.full_name)
