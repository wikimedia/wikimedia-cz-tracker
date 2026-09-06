# -*- coding: utf-8 -*-
from django.contrib import auth
from django.views.generic import CreateView
from django import forms
from django.urls import reverse
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.debug import sensitive_post_parameters
from django.forms.models import fields_for_model
from django.views.generic import FormView
from django.shortcuts import render, get_object_or_404

from tracker.models import BankAccount, TrackerProfile

from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget

from .forms import CustomPasswordChangeForm


# Bank account fields of the details form. The user can leave them all
# empty, but a partially filled account is an error.
BANK_ACCOUNT_FIELDS = ("name", "prefix", "number", "bank")
REQUIRED_BANK_ACCOUNT_FIELDS = ("name", "number", "bank")

PROFILE_FIELDS = ("other_contact", "other_identification")


class TrackerProfileDetailsForm(forms.ModelForm):
    """
    The details form that the user gets after the registration.

    The form makes a bank account for the new user. It also fills the
    contact details in the profile of the user. The bank account is
    optional, because the user can add one later.
    """

    class Meta:
        model = BankAccount
        fields = BANK_ACCOUNT_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in REQUIRED_BANK_ACCOUNT_FIELDS:
            self.fields[field_name].required = False
        self.fields.update(fields_for_model(TrackerProfile, fields=PROFILE_FIELDS))
        self.set_bank_account_help_texts()

    def set_bank_account_help_texts(self):
        """
        Explain the bank account fields to the new user.

        An account number has three parts: an optional prefix, the number
        and the code of the bank. The help texts tell the user which part
        goes into which field.
        """
        help_texts = {
            "name": _('Your own name for this account, for example "Personal account". '
                      'It helps you to select the correct account when you ask for a payment.'),
            "prefix": _("The part of the account number before the dash. "
                        "Many accounts have no prefix; then leave this field empty."),
            "number": _("The part of the account number before the slash."),
            "bank": _("The four-digit code of your bank, after the slash. For example 0800."),
        }
        for field_name, help_text in help_texts.items():
            self.fields[field_name].help_text = help_text

    def has_bank_account(self):
        """ Tell if the user filled any part of the bank account. """
        return any(self.cleaned_data.get(field_name) for field_name in BANK_ACCOUNT_FIELDS)

    def clean(self):
        cleaned_data = super().clean()
        if self.has_bank_account():
            for field_name in REQUIRED_BANK_ACCOUNT_FIELDS:
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, self.fields[field_name].error_messages['required'])
        return cleaned_data


class AddTrackerProfileDetails(FormView):
    template_name = 'tracker/fill_details.html'
    form_class = TrackerProfileDetailsForm

    def form_valid(self, form):
        tracker_profile = get_object_or_404(TrackerProfile, user=self.request.user)
        for field_name in PROFILE_FIELDS:
            setattr(tracker_profile, field_name, form.cleaned_data[field_name])
        tracker_profile.save()

        if form.has_bank_account():
            bank_account = form.save(commit=False)
            bank_account.user = tracker_profile
            bank_account.save()

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
