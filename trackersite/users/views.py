# -*- coding: utf-8 -*-
from django.contrib import auth
from django.views.generic import CreateView
from django.contrib import messages
from django import forms
from django.urls import reverse
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.debug import sensitive_post_parameters
from django.shortcuts import render

from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget

from .forms import CustomPasswordChangeForm


class UserWithEmailForm(auth.forms.UserCreationForm):
    email = forms.EmailField(required=True, help_text=_("Will be used for password recovery and notifications, if you enable them."))
    captcha = ReCaptchaField(widget=ReCaptchaWidget())

    class Meta:
        model = auth.models.User
        fields = ("username", "email")
        # ^ UserCreationForm has custom handling of password


class RegisterView(CreateView):
    form_class = UserWithEmailForm
    template_name = 'users/register.html'

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('User %s created.') % form.cleaned_data['username'])
        new_user = auth.authenticate(username=form.cleaned_data['username'],
                                     password=form.cleaned_data['password1'])
        auth.login(self.request, new_user)

        return HttpResponseRedirect(reverse('ticket_list'))


register = RegisterView.as_view()


@sensitive_post_parameters()
@login_required
def password_change(request, template_name):
    post_change_redirect = reverse('password_change_done')
    if request.method == "POST":
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            # Updating the password logs out all other sessions for the user
            # except the current one if
            # django.contrib.auth.middleware.SessionAuthenticationMiddleware
            # is enabled.
            update_session_auth_hash(request, form.user)
            return HttpResponseRedirect(post_change_redirect)
    else:
        form = CustomPasswordChangeForm(user=request.user)
    context = {
        'user_has_usable_password': request.user.has_usable_password(),
        'form': form,
        'title': _('Password change'),
    }

    return TemplateResponse(request, template_name, context)


@login_required
def invalid_oauth_tokens(request, provider):
    return render(request, 'users/oauth_invalid.html', {
        'provider': provider,
        'next': request.GET.get('next', '/')
    })
