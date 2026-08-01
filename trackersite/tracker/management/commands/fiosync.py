# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from tracker.fio import FioPaymentManager


class Command(BaseCommand):
    help = 'Synchronizes transactions from Fio API and expires unprocessed imports.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=14,
            help='Number of days in the past to download transactions (default: 14)',
        )
        parser.add_argument(
            '--expiry',
            type=int,
            default=0,
            help='Number of days past due date to expire imports (default: 0)',
        )

    def handle(self, *args, **options):
        days_back = options['days']
        expiry_days = options['expiry']

        self.stdout.write(self.style.NOTICE(
            f'Starting Fio synchronization (history: {days_back} days, expiry after: {expiry_days} days)...'
        ))

        manager = FioPaymentManager()
        report = manager.sync_transactions(days_back=days_back, expiry_days=expiry_days)

        if report['marked_paid'] > 0:
            self.stdout.write(self.style.SUCCESS(f"Successfully matched and marked as PAID: {report['marked_paid']} expenditures."))
        else:
            self.stdout.write("No new payments found for matching.")

        if report['reverted'] > 0:
            self.stdout.write(self.style.WARNING(f"Expired and reverted to WAITING: {report['reverted']} expenditures."))

        if report['errors']:
            self.stdout.write(self.style.ERROR("Errors occurred during synchronization:"))
            for error in report['errors']:
                self.stdout.write(self.style.ERROR(f"- {error}"))

        self.stdout.write(self.style.SUCCESS('Fio synchronization completed.'))
