import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_cnb_mod_11(value):
    if not value:
        return

    if not value.isdigit():
        raise ValidationError(_('Account number must be a number.'))

    weights = [1, 2, 4, 8, 5, 10, 9, 7, 3, 6]
    padded = value.zfill(10)

    total = sum(int(digit) * weight for digit, weight in zip(reversed(padded), weights))

    if total % 11 != 0:
        raise ValidationError(_('Incorrect account number.'))


def validate_bank_code(value):
    if not value:
        return
    if not re.match(r'^\d{4}$', str(value).strip()):
        raise ValidationError(_('Incorrect bank code.'))


def validate_full_bank_account(value):
    if not value:
        return

    value = str(value).strip()

    match = re.match(r'^(?:(?P<prefix>\d{1,6})-)?(?P<account>\d{2,10})/(?P<bank_code>\d{4})$', value)

    if not match:
        raise ValidationError(_('Invalid account format.'))

    prefix = match.group('prefix')
    account = match.group('account')
    bank_code = match.group('bank_code')

    if prefix:
        try:
            validate_cnb_mod_11(prefix)
        except ValidationError:
            raise ValidationError(_('Incorrect account prefix.'))

    validate_cnb_mod_11(account)
    validate_bank_code(bank_code)
