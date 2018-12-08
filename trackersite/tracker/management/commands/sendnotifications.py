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

    def handle_noargs(self, **options):
        subject_c = Context({"date": date.today()})
        subject_text = get_template('notification/notification_subject.txt').render(subject_c)
        html_template = get_template('notification/notification_html.html')
        for user in User.objects.all():
            if user.email:
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
                        "BASE_URL": settings.BASE_URL,
                    }
                    c = Context(c_dict)
                    if user.trackerpreferences.email_language:
                        translation.activate(user.trackerpreferences.email_language)
                    else:
                        translation.deactivate()
                    user.email_user(subject_text, strip_tags(html_template.render(c)), html_message=html_template.render(c))
            for notification in Notification.objects.filter(target_user=user):
                notification.delete()
