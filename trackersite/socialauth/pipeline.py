from django.contrib import messages
from django.utils.translation import ugettext as _
from tracker.services import get_request


def save_extra_data(backend, user, response, *args, **kwargs):
    if backend.name == "mediawiki":
        user.trackerprofile.mediawiki_username = kwargs['details']['username']
        user.trackerprofile.save()


def display_succes_message_link(backend, *args, **kwargs):
    request = get_request()
    if backend.name == "mediawiki" and kwargs['new_association']:
        messages.success(request, _('Successfully linked your wikimedia account!'))
    elif backend.name == "chapterwiki" and kwargs['new_association']:
        messages.success(request, _('Successfully linked your chapter account!'))


def display_succes_message_disconnect(backend, *args, **kwargs):
    request = get_request()
    if backend.name == "mediawiki":
        messages.success(request, _('Your wikimedia account is no longer linked.'))
    elif backend.name == "chapterwiki":
        messages.success(request, _('Your chapterwiki account is no longer linked.'))
