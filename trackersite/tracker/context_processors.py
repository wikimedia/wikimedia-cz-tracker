# -*- coding: utf-8 -*-
from django.conf import settings


def public_settings(request):
    return {
        'CURRENCY': settings.TRACKER_CURRENCY,
        'BASE_URL': settings.BASE_URL,
        'PRODUCTION': settings.PRODUCTION,
        'PRODUCTION_URL': settings.PRODUCTION_URL,
        'GOOGLE_ANALYTICS': settings.GOOGLE_ANALYTICS,
        'MANUAL_LINK': settings.MANUAL_LINK,
        'STATUTORY_DECLARATION_TEXT': settings.STATUTORY_DECLARATION_TEXT,
    }
