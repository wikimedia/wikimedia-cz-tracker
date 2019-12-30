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
from django.views.generic import FormView
from django.shortcuts import render, get_object_or_404

from tracker.models import TrackerProfile

from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget

from .forms import CustomPasswordChangeForm


class TrackerProfileDetailsForm(forms.ModelForm):
    class Meta:
        model = TrackerProfile
        fields = ("bank_account", "other_contact", "other_identification")


class AddTrackerProfileDetails(FormView):
    template_name = 'tracker/fill_details.html'
    form_class = TrackerProfileDetailsForm

    def form_valid(self, form):
        tracker_profile = get_object_or_404(TrackerProfile, user=self.request.user)
        tracker_profile.bank_account = form.cleaned_data['bank_account']
        tracker_profile.other_contact = form.cleaned_data['other_contact']
        tracker_profile.other_identification = form.cleaned_data['other_identification']
        tracker_profile.save()
        return HttpResponseRedirect(reverse('ticket_list'))


fill_details = login_required(AddTrackerProfileDetails.as_view())


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
        new_user = auth.authenticate(username=form.cleaned_data['username'],
                                     password=form.cleaned_data['password1'])
        auth.login(self.request, new_user)
        self.request.session['just_registered'] = True
        return HttpResponseRedirect(reverse('fill_details'))


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
