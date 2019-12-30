# -*- coding: utf-8 -*-
from django.contrib.auth import views as auth
from django.urls import path

import users
from .views import password_change, invalid_oauth_tokens

urlpatterns = [
    path('login/', auth.LoginView.as_view(template_name='users/login.html'), name='tracker_login'),
    path('logout/', auth.LogoutView.as_view(template_name='users/logout.html'), name='tracker_logout'),
    path('register/', users.views.register, name='register'),
    path('register/details/', users.views.fill_details, name='fill_details'),
    path('password/change/', password_change, name='password_change',
         kwargs={'template_name': 'users/password_change.html'}),
    path('password/change/done/', auth.PasswordChangeDoneView.as_view(template_name='users/password_change_done.html'),
         name='password_change_done'),
    path('password/reset/', auth.PasswordResetView.as_view(template_name='users/password_reset.html',
                                                           email_template_name='users/password_reset_email.html'),
         name='password_reset'),
    path('password/reset/sent/', auth.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'),
         name='password_reset_done'),
    path('password/reset/<str:uidb64>/<str:token>/',
         auth.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password/reset/done/',
         auth.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'),
         name='password_reset_complete'),
    path('oauth/<provider>/invalid/', invalid_oauth_tokens, name='invalid_oauth_tokens'),
]
