# -*- coding: utf-8 -*-
from __future__ import absolute_import

import django.views.i18n
import rest_framework.authtoken.views
from django.urls import include, re_path
from django.contrib import admin
from django.http import HttpResponse
from django.views.generic import RedirectView, TemplateView
from django.views.i18n import JavaScriptCatalog

import tracker.urls
import users.urls
from api.router import router

admin.autodiscover()
# Django 3.1 added a navigation sidebar to every admin page. Do not show it.
admin.site.enable_nav_sidebar = False

js_info_dict = [
    'django.contrib.admin'
    # local site stuff should be covered by LOCALE_PATHS common setting
]

handler403 = 'errors.permission_denied'

urlpatterns = [
    re_path(r'^$', RedirectView.as_view(url='tickets/', permanent=False), name='index'),
    re_path(r'old/(?P<url>(?:tickets?/|topics?/|)(?:\d+/|new/)?)$', RedirectView.as_view(url='/%(url)s', permanent=True)),
    re_path('', include(tracker.urls)),  # tracker urls are included directly in web root
    re_path('admin/', admin.site.urls),
    re_path('account/', include(users.urls)),
    re_path('oauth/', include('social_django.urls', namespace='social')),
    re_path('^lang/$', TemplateView.as_view(template_name='choose_language.html'), name='choose_language'),
    re_path('lang/set/', django.views.i18n.set_language, name='set_language'),
    re_path('api/', include(router.urls)),
    re_path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    re_path('api-token-auth/', rest_framework.authtoken.views.obtain_auth_token),
    re_path('robots.txt', lambda x: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")),
    re_path('jsi18n/', JavaScriptCatalog.as_view(packages=js_info_dict), name='javascript-catalog'),
]
