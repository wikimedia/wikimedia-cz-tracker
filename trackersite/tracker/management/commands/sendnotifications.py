from django.core.management.base import NoArgsCommand
from tracker.models import Notification
from django.contrib.auth.models import User
from django.template.loader import get_template
from django.template import Context
from django.conf import settings
from django.utils import translation
from django.utils.html import strip_tags
from datetime import date


class Command(NoArgsCommand):
    help = 'Process pending notifications'
    subject_c = Context({"date": date.today()})
    subject_template = get_template('notification/notification_subject.txt')
    html_template = get_template('notification/notification_html.html')

    def get_user_object(self, user):
        if user.startswith('#') and user[1:].isdigit():
            return User.objects.get(id=int(user[1:]))
        else:
            return User.objects.get(username=user)

    def process_user(self, user, email_user=None, dry_run=False):
        if email_user is None:
            email_user = user
        if not email_user.email:
            return
        if len(Notification.objects.filter(target_user=user)) > 0:
            c_dict = {
                "ack_notifs": Notification.objects.filter(target_user=user, notification_type__in=["ack_add", "ack_remove"]),
                "ticket_change_notifs": Notification.objects.filter(target_user=user, notification_type__in=["ticket_change", "ticket_change_all"]),
                "preexpeditures_notifs": Notification.objects.filter(target_user=user, notification_type__in=["preexpeditures_change", "preexpeditures_new"]),
                "expeditures_notifs": Notification.objects.filter(target_user=user, notification_type__in=["expeditures_change", "expeditures_new"]),
                "media_notifs": Notification.objects.filter(target_user=user, notification_type__in=["media_change", "media_new"]),
                "ticket_new_notifs": Notification.objects.filter(target_user=user, notification_type="ticket_new"),
                "ticket_delete_notifs": Notification.objects.filter(target_user=user, notification_type="ticket_delete"),
                "comment_notifs": Notification.objects.filter(target_user=user, notification_type="comment"),
                "supervisor_notes_notifs": Notification.objects.filter(target_user=user, notification_type="supervisor_notes"),
                "document_notifs": Notification.objects.filter(target_user=user, notification_type="document"),
                "BASE_URL": settings.BASE_URL,
            }
            c = Context(c_dict)
            if user.trackerpreferences.email_language:
                translation.activate(user.trackerpreferences.email_language)
            else:
                translation.deactivate()
            if dry_run:
                print('Subject: %s' % self.subject_template.render(self.subject_c))
                print('To: %s' % email_user.email)
                print('')
                print(self.html_template.render(c))
            else:
                email_user.email_user(self.subject_template.render(self.subject_c), strip_tags(self.html_template.render(c)), html_message=self.html_template.render(c))

    def add_arguments(self, parser):
        parser.add_argument(
            '--email-user',
            dest='email_user',
            nargs=1,
            type=str,
            help='Send all notifications to this user (prefix with # if you want to use user id)'
        )
        parser.add_argument(
            '--only-process',
            dest='process_users',
            nargs='+',
            type=str,
            help='Process only those users (prefix with # if you want to use user id)'
        )
        parser.add_argument(
            '--keep',
            action='store_false',
            dest='delete',
            help='Do not delete notifications after sending them'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Do not send any emails, input them on screen (produces large output)'
        )

    def handle(self, *args, **options):
        users = User.objects.all()

        # Handle process users argument
        if options['process_users']:
            users = []
            for process_user in options['process_users']:
                users.append(self.get_user_object(process_user))

        # Handle email_user argument
        email_user = None
        if options['email_user']:
            email_user = self.get_user_object(options['email_user'][0])

        # Process notifications
        for user in users:
            self.process_user(user, email_user=email_user, dry_run=options['dry_run'])
            if options['delete']:
                Notification.objects.filter(target_user=user).delete()
