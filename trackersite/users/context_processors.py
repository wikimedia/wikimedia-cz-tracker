from __future__ import absolute_import
from .models import UserWrapper


def wrapped_user(request):
    return {'wrapped_user': UserWrapper(request.user)}
