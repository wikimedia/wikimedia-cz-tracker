from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.utils.translation import ugettext as _


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    A customized form from PasswordChangeForm to allow user that
    don't have any usable password (usually happened when they logged in
    with an OAuth account).
    """

    old_password = forms.CharField(label=_("Old password"),
                                   widget=forms.PasswordInput,
                                   required=False)

    def clean_old_password(self):
        """
        Validates that the old_password field is correct if the user
        has any usable password.
        """
        old_password = self.cleaned_data["old_password"]
        if self.user.has_usable_password() and (not self.user.check_password(old_password)):
            raise forms.ValidationError(
                self.error_messages['password_incorrect'],
                code='password_incorrect',
            )
        return old_password
