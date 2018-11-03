# -*- coding: utf-8 -*-
from django.conf import settings


def public_settings(request):
    return {
        'CURRENCY': settings.TRACKER_CURRENCY,
        'BASE_URL': settings.BASE_URL,
        'PRODUCTION': settings.PRODUCTION,
        'GOOGLE_ANALYTICS': settings.GOOGLE_ANALYTICS,
    }
