# -*- coding: utf-8 -*-
import users
from django.conf.urls import url
from django.contrib.auth import views as auth
from .views import password_change, invalid_oauth_tokens

urlpatterns = [
    url(r'^login/$', auth.login, kwargs={'template_name': 'users/login.html'}, name='tracker_login'),
    url(r'^logout/$', auth.logout, kwargs={'template_name': 'users/logout.html'}, name='tracker_logout'),
    url(r'^register/$', users.views.register, name='register'),
    url(r'^password/change/$', password_change, name='password_change', kwargs={'template_name': 'users/password_change.html'}),
    url(r'^password/change/done/$', auth.password_change_done, name='password_change_done', kwargs={
        'template_name': 'users/password_change_done.html',
    }),
    url(r'^password/reset/$', auth.password_reset, kwargs={
        'template_name': 'users/password_reset.html', 'email_template_name': 'users/password_reset_email.html'
    }, name='password_reset'),
    url(r'^password/reset/sent/$', auth.password_reset_done, name='password_reset_done', kwargs={
        'template_name': 'users/password_reset_done.html',
    }),
    url(r'^password/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/$', auth.password_reset_confirm, name='password_reset_confirm', kwargs={
        'template_name': 'users/password_reset_confirm.html',
    }),
    url(r'^password/reset/done/$', auth.password_reset_complete, name='password_reset_complete', kwargs={
        'template_name': 'users/password_reset_complete.html'
    }),
    url(r'^oauth/(?P<provider>[a-z]+)/invalid/', invalid_oauth_tokens, name='invalid_oauth_tokens'),
]
