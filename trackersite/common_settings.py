# -*- coding: utf-8 -*-
from os.path import dirname, abspath, join
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _

SITE_DIR = abspath(dirname(__file__))
PROJECT_DIR = abspath(join(dirname(__file__), '..'))
_IGNORE = ('_IGNORE', '__builtins__', '__doc__', '__file__', '__name__', '__package__', 'os')

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
)

TEMPLATE_DIRS = (
    join(SITE_DIR, 'templates'),
)

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.core.context_processors.request",
    "django.contrib.messages.context_processors.messages",
    'social_django.context_processors.backends',
    'social_django.context_processors.login_redirect',
    "tracker.context_processors.public_settings",
    "users.context_processors.wrapped_user",
)

STATICFILES_DIRS = (
    join(PROJECT_DIR, 'static'),
)

LOCALE_PATHS = (
    join(SITE_DIR, 'locale'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'django_comments',
    'django.contrib.messages',
    'tracker',
    'users',
    'api',
    'customcomments',
    'sendfile',
    'snowpenguin.django.recaptcha2',
    'widget_tweaks',
    'social_django',
    'rest_framework',
    'django_filters',
)

COMMENTS_APP = 'customcomments'

ROOT_URLCONF = 'urls'
LOGIN_URL = '/account/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_URL = '/account/logout/'

MESSAGE_STORAGE = 'django.contrib.messages.storage.fallback.FallbackStorage'

TRACKER_CURRENCY = _('CZK')

LANGUAGES = (
    ('en', _('English')),
    ('cs', _('Czech')),
)

AUTHENTICATION_BACKENDS = (
    'social_core.backends.mediawiki.MediaWiki',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_MEDIAWIKI_CALLBACK = 'oob'

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ),
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ]
}

STATUTORY_DECLARATION_TEXT = 'I hereby declare that my travel expenses are true and accurate and that you spent money economically and effectivelly.'

MESSAGE_TAGS = {
    messages.ERROR: 'danger'
}

MANUAL_LINK = 'https://www.wikimedia.cz/web/Manuál_na_tracker'
