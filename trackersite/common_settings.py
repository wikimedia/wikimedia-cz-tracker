# -*- coding: utf-8 -*-
from os.path import dirname, abspath, join
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _

SITE_DIR = abspath(dirname(__file__))
PROJECT_DIR = abspath(join(dirname(__file__), '..'))
_IGNORE = ('_IGNORE', '__builtins__', '__doc__', '__file__', '__name__', '__package__', 'os')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
    'crequest.middleware.CrequestMiddleware',
    'tracker.middleware.WarnIEUsers',
    'tracker.middleware.InvalidOauth',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [join(SITE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
                'tracker.context_processors.public_settings',
                'users.context_processors.wrapped_user',
            ],
        },
    },
]

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/tmp/tracker.log',
            'formatter': 'verbose'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins', 'file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'tracker': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}

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
    'rest_framework.authtoken',
    'rest_framework_swagger',
    'django_filters',
    'background_task',
    'crequest',
)

USE_TZ = True

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
    ('fr', _('French')),
    ('ar', _('Arabic')),
    ('da', _('Danish')),
    ('fi', _('Finnish')),
    ('ko', _('Korean')),
    ('pt', _('Portuguese')),
    ('sv', _('Swedish')),
    ('zh-hant', _('Chinese-traditional')),
    ('es', _('Spanish'))
)

AUTHENTICATION_BACKENDS = (
    'social_core.backends.mediawiki.MediaWiki',
    'socialauth.chapterwiki.ChapterWiki',
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_MEDIAWIKI_CALLBACK = 'oob'
SOCIAL_AUTH_CHAPTERWIKI_CALLBACK = 'oob'
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ['groups', ]
SOCIAL_AUTH_NEW_USER_REDIRECT_URL = '/account/register/details'
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'socialauth.pipeline.save_extra_data',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'socialauth.pipeline.display_succes_message_link'
)

SOCIAL_AUTH_DISCONNECT_PIPELINE = (
    'social_core.pipeline.disconnect.allowed_to_disconnect',
    'social_core.pipeline.disconnect.get_entries',
    'social_core.pipeline.disconnect.revoke_tokens',
    'social_core.pipeline.disconnect.disconnect',
    'socialauth.pipeline.display_succes_message_disconnect'
)

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ),
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    )

}

# Setting this to False will remove the limitation
MAX_NUMBER_OF_ROWS_ON_IMPORT = 100

STATUTORY_DECLARATION_TEXT = 'I hereby declare that my travel expenses are true and accurate and that I spent money economically and effectivelly.'

MESSAGE_TAGS = {
    messages.ERROR: 'danger'
}

ALLOWED_TAGS = ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul', 'big', 'small']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title'], 'acronym': ['title'], 'abbr': ['title']}
