# -*- coding: utf-8 -*-
from django.contrib.auth import views as auth
from django.urls import path

import users
from .views import password_change, invalid_oauth_tokens

urlpatterns = [
    path('login/', auth.login, kwargs={'template_name': 'users/login.html'}, name='tracker_login'),
    path('logout/', auth.logout, kwargs={'template_name': 'users/logout.html'}, name='tracker_logout'),
    path('register/', users.views.register, name='register'),
    path('password/change/', password_change, name='password_change',
         kwargs={'template_name': 'users/password_change.html'}),
    path('password/change/done/', auth.password_change_done, name='password_change_done', kwargs={
        'template_name': 'users/password_change_done.html',
    }),
    path('password/reset/', auth.password_reset, kwargs={
        'template_name': 'users/password_reset.html', 'email_template_name': 'users/password_reset_email.html'
    }, name='password_reset'),
    path('password/reset/sent/', auth.password_reset_done, name='password_reset_done', kwargs={
        'template_name': 'users/password_reset_done.html',
    }),
    path('password/reset/<str:uidb64>/<str:token>/', auth.password_reset_confirm,
         name='password_reset_confirm', kwargs={'template_name': 'users/password_reset_confirm.html'}),
    path('password/reset/done/', auth.password_reset_complete, name='password_reset_complete', kwargs={
        'template_name': 'users/password_reset_complete.html'
    }),
    path('oauth/<provider>/invalid/', invalid_oauth_tokens, name='invalid_oauth_tokens'),
]
