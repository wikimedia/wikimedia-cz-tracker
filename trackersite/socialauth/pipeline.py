from django.contrib import messages
from django.utils.translation import ugettext as _
from request_provider.signals import get_request


def save_extra_data(backend, user, response, *args, **kwargs):
    if backend.name == "mediawiki":
        user.trackerprofile.mediawiki_username = kwargs['details']['username']
        user.trackerprofile.save()


def display_succes_message_link(backend, *args, **kwargs):
    if backend.name == "mediawiki" and not kwargs['is_new']:
        request = get_request()
        messages.success(request, _('Successfully linked your wikimedia account!'))


def display_succes_message_disconnect(backend, *args, **kwargs):
    if backend.name == "mediawiki":
        request = get_request()
        messages.success(request, _('Your wikimedia account is no longer linked.'))
