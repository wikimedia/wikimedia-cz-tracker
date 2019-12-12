# -*- coding: utf-8 -*-
from __future__ import absolute_import
import django
import django.views.i18n
from django.conf.urls import include, url
from django.http import HttpResponse
from django.views.generic import RedirectView, TemplateView
from django.contrib import admin

import tracker.urls
from api.router import router
import users.urls
import rest_framework.authtoken.views

admin.autodiscover()

js_info_dict = {
    'packages': ('django.contrib.admin'),
    # local site stuff should be covered by LOCALE_PATHS common setting
}

handler403 = 'errors.permission_denied'

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='tickets/', permanent=False), name='index'),
    url(r'', include(tracker.urls)),  # tracker urls are included directly in web root
    url(r'^admin/', include(admin.site.urls)),
    url(r'^account/', include(users.urls)),
    url(r'oauth/', include('social_django.urls', namespace='social')),
    url(r'^lang/$', TemplateView.as_view(template_name='choose_language.html'), name='choose_language'),
    url(r'^lang/set/$', django.views.i18n.set_language, name='set_language'),
    url(r'^js/i18n\.js$', django.views.i18n.javascript_catalog, js_info_dict),
    url(r'^api/', include(router.urls)),
    url(r'^api-docs/', include('rest_framework_swagger.urls')),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api-token-auth/', rest_framework.authtoken.views.obtain_auth_token),
    url(r'^robots\.txt$', lambda x: HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")),
]
