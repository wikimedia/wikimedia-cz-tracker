# -*- coding: utf-8 -*-
from __future__ import absolute_import

import django.views.i18n
import rest_framework.authtoken.views
from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse
from django.views.generic import RedirectView, TemplateView
from django.views.i18n import javascript_catalog
from rest_framework_swagger.views import get_swagger_view

import tracker.urls
import users.urls
from api.router import router

admin.autodiscover()

js_info_dict = {
    'packages': ('django.contrib.admin',),
    # local site stuff should be covered by LOCALE_PATHS common setting
}

handler403 = 'errors.permission_denied'

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='tickets/', permanent=False), name='index'),
    url(r'old/(?P<url>(?:tickets?/|topics?/|)(?:\d+/|new/)?)$', RedirectView.as_view(url='/%(url)s', permanent=True)),
    url(r'', include(tracker.urls)),  # tracker urls are included directly in web root
    url(r'^admin/', admin.site.urls),
    url(r'^account/', include(users.urls)),
    url(r'^oauth/', include('social_django.urls', namespace='social')),
    url(r'^lang/$', TemplateView.as_view(template_name='choose_language.html'), name='choose_language'),
    url(r'^lang/set/$', django.views.i18n.set_language, name='set_language'),
    url(r'^api/', include(router.urls)),
    url(r'^api-docs/', get_swagger_view()),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api-token-auth/', rest_framework.authtoken.views.obtain_auth_token),
    url(r'^robots\.txt$', lambda x: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")),
    url(r'^jsi18n/$', javascript_catalog, js_info_dict, name='javascript-catalog'),
]
