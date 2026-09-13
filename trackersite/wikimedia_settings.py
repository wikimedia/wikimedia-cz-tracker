# -*- coding: utf-8 -*-
# Django project settings for Wikimedia Continous Integration
# THIS IS NOT AN EXAMPLE CONFIGURATION
# If you want to generate settings.py, use support/makesettings.py
from __future__ import absolute_import
import os

import common_settings as _common
for item in dir(_common):
    if item not in _common._IGNORE:
        locals()[item] = getattr(_common, item)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'tracker',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
        'OPTIONS': {
            'unix_socket': '/tmp/mysqld/mysqld.sock'
        },
        'TEST': {
            'COLLATION': 'utf8_general_ci'
        }
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'tracker-test-cache',
    }
}

SECRET_KEY = '42'
PRODUCTION = False
TRACKER_DOCS_ROOT = os.path.join(os.environ['DEPLOY_DIR'], 'docs')
SENDFILE_ROOT = TRACKER_DOCS_ROOT
SITE_ID = 1
ADMIN_MEDIA_PREFIX = '/static/admin/'
STATIC_URL = '/static/'
# Google's public reCAPTCHA test keys. They always validate.
RECAPTCHA_PUBLIC_KEY = '6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'
RECAPTCHA_PRIVATE_KEY = '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'
SILENCED_SYSTEM_CHECKS = ['django_recaptcha.recaptcha_test_key_error']
SENDFILE_BACKEND = 'django_sendfile.backends.development'
BASE_URL = 'https://example.com'
GOOGLE_ANALYTICS = None
MEDIAINFO_MEDIAWIKI_API = 'https://commons.wikimedia.org/w/api.php'
PRODUCTION_URL = "https://tracker.wikimedia.cz"
TRACKER_MANUAL_LINK = None
MEDIAINFO_MEDIAWIKI_ARTICLE = 'https://commons.wikimedia.org/wiki/'
MEDIAINFO_MEDIAWIKI_TEMPLATE = 'Fotíme Česko'
MEDIAINFO_MEDIAWIKI_INFO_TEMPLATE = 'Information'
