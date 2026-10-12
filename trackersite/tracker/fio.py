# -*- coding: utf-8 -*-
import datetime
import xml.etree.ElementTree as ET
import zoneinfo
from decimal import Decimal
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.db import transaction
import requests
import re
import logging
from django.utils.translation import gettext_lazy as _

from tracker.models import PaymentType, ImportInfo, Expediture, ReconciledTransaction

logger = logging.getLogger(__name__)

# The time zone that Fio writes the dates in. The JSON API gives the date as a
# number of milliseconds at midnight local time, thus a conversion in another
# zone moves the date by one day. The project does not set TIME_ZONE, and so
# the Django default is not the zone of the bank.
BANK_TIMEZONE_NAME = 'Europe/Prague'

try:
    BANK_TIMEZONE = zoneinfo.ZoneInfo(BANK_TIMEZONE_NAME)
except zoneinfo.ZoneInfoNotFoundError:  # pragma: no cover
    # zoneinfo reads the time zone database of the system, which a small
    # container can leave out. pytz carries its own copy, and Django needs
    # pytz anyway.
    import pytz

    BANK_TIMEZONE = pytz.timezone(BANK_TIMEZONE_NAME)


class FioPaymentManager:
    FIO_IMPORT_URL = 'https://fioapi.fio.cz/v1/rest/import/'

    # Connect timeout and read timeout for the Fio API, in seconds. The import
    # runs in a web request. A call must not hold a worker for an unlimited time.
    HTTP_TIMEOUT = (10, 60)

    # How strongly an expenditure fits a bank transaction, strongest first.
    # The bank message is the only field that names one expenditure. The order
    # number is the same for all the expenditures of one import batch, and so
    # it must rank below the message.
    MATCH_MESSAGE_AND_BATCH = 3
    MATCH_MESSAGE = 2
    MATCH_BATCH = 1
    MATCH_NONE = 0

    # The Fio fields that can carry our payment reference: the message for the
    # recipient, and the comment.
    REFERENCE_COLUMNS = ('column16', 'column25')

    # The Fio field that holds the identity of one transaction. Fio gives a
    # different field, column17, for the identity of the import order. Many
    # transactions share one order, thus only column22 names one movement of
    # money.
    TRANSACTION_ID_COLUMN = 'column22'

    # The Fio field that holds the date of the transaction.
    DATE_COLUMN = 'column0'

    @staticmethod
    def normalize_account(account_str):
        account_str = str(account_str).strip()

        if '/' not in account_str:
            return f"{account_str}/2010"

        return account_str

    @staticmethod
    def get_available_accounts():
        raw_tokens = getattr(settings, 'FIO_API_TOKENS', {})
        return [FioPaymentManager.normalize_account(k) for k in raw_tokens.keys()]

    @classmethod
    def _reference_text(cls, transaction):
        """
        Join the transaction fields that can name an expenditure.

        A transfer carries the reference in the message for the recipient, and
        _generate_xml() copies the same text into the comment. A card
        transaction has no message for the recipient: the bank fills that field
        with the merchant and the date. The operator thus writes the reference
        in the comment. Read both fields, because either one can hold it.
        """
        parts = []

        for column in cls.REFERENCE_COLUMNS:
            column_data = transaction.get(column)
            if not column_data:
                continue

            value = str(column_data.get('value', '') or '')
            if value:
                parts.append(value)

        return ' | '.join(parts)

    @classmethod
    def _transaction_id(cls, transaction):
        """
        Read the identity of one transaction.

        Return None when Fio sends no identity. The sync then cannot tell this
        transaction from another one, and so it must not record it.
        """
        column_data = transaction.get(cls.TRANSACTION_ID_COLUMN)
        if not column_data:
            return None

        value = str(column_data.get('value', '') or '').strip()
        return value or None

    @classmethod
    def _transaction_date(cls, transaction):
        """
        Read the date of one transaction.

        Fio uses two forms. The XML API writes a date with a time zone, for
        example 2026-09-04+0200. The JSON API writes a number of milliseconds
        since the epoch at midnight in the zone of the bank. Read both.

        Return None when the field is absent or malformed. The date is only a
        note for the operator, thus it must not stop the match.
        """
        column_data = transaction.get(cls.DATE_COLUMN)
        if not column_data:
            return None

        value = column_data.get('value')
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        text = str(value).strip()
        if not text:
            return None

        if isinstance(value, (int, float)) or text.lstrip('-').isdigit():
            try:
                moment = datetime.datetime.fromtimestamp(int(value) / 1000, tz=BANK_TIMEZONE)
            except (OverflowError, OSError, ValueError):
                return None

            return moment.date()

        try:
            return datetime.date.fromisoformat(text[:10])
        except ValueError:
            return None

    @staticmethod
    def _message_matches(expected_msg, message):
        """
        Fio's message field may carry extra text around our reference, so this
        is a substring match -- but anchored, so "WMCZ ticket #1" does not
        match "WMCZ ticket #12".
        """
        if not expected_msg or not message:
            return False
        return re.search(re.escape(expected_msg) + r'(?!\w)', message) is not None

    def __init__(self):
        raw_tokens = getattr(settings, 'FIO_API_TOKENS', {})
        self.tokens = {self.normalize_account(k): v for k, v in raw_tokens.items()}
        self.currencies = getattr(settings, 'FIO_API_CURRENCIES', {})

    def _select_tokens(self, accounts):
        """
        Give the account-to-token map that a sync run must read.

        Pass None for accounts to read every registered account. Pass a list of
        account numbers to read only those. The bank code is optional, because
        normalize_account() adds the Fio one.

        Raise ValueError if an account has no token, because a silent empty run
        looks the same as a run that found no payment.
        """
        if accounts is None:
            return dict(self.tokens)

        selected = {}
        for account in accounts:
            full_account = self.normalize_account(account)

            if full_account not in self.tokens:
                raise ValueError(
                    f"No Fio API token for account {full_account}. "
                    f"Registered accounts: {', '.join(sorted(self.tokens)) or '(none)'}."
                )

            selected[full_account] = self.tokens[full_account]

        return selected

    def _split_target_account(self, full_account):
        if '/' not in full_account:
            raise ValueError(f"Wrong account format: {full_account}")

        account_part, bank_code = full_account.split('/', 1)
        return account_part, bank_code

    def _get_payment_message(self, expediture):
        if expediture.payment_type == PaymentType.INTERNAL_TRANSFER:
            if not expediture.linked_expenditure:
                raise ValueError(f"Missing linked expenditure for ticket: {expediture.ticket.id}")

            number = expediture.linked_expenditure.accounting_info or expediture.linked_expenditure.id
            msg = f"Kofinancování ticketu #{number}_ko"

        elif expediture.payment_type == PaymentType.INCOME:
            number = expediture.accounting_info or expediture.ticket.id
            msg = f"Kofinancování ticketu #{number}_ko"

        elif expediture.payment_type in [PaymentType.BANK_TRANSFER, PaymentType.CARD]:
            number = expediture.accounting_info or expediture.ticket.id
            msg = f"WMCZ ticket #{number}"
        else:
            raise ValueError(f"Unsupported payment type: {expediture.payment_type}")

        return msg[:140]

    def _generate_xml(self, source_account, expenditures, execution_date):
        root = ET.Element("Import", {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://www.fio.cz/schema/importIB.xsd"
        })
        orders = ET.SubElement(root, "Orders")

        account_from = str(source_account).split('/')[0] if '/' in str(source_account) else str(source_account)
        account_currency = self.currencies.get(source_account, "CZK")

        for exp in expenditures:
            if not getattr(exp, 'payment_info', None) and exp.payment_type not in [PaymentType.INTERNAL_TRANSFER, PaymentType.INCOME]:
                continue

            transaction = ET.SubElement(orders, "DomesticTransaction")

            ET.SubElement(transaction, "accountFrom").text = account_from
            ET.SubElement(transaction, "currency").text = account_currency
            ET.SubElement(transaction, "amount").text = str(exp.amount)

            target_account = exp.get_target_account()

            if not target_account:
                raise ValueError(f"Cannot resolve target account for expenditure {exp.id}")

            acc_num, bank_code = self._split_target_account(target_account)

            ET.SubElement(transaction, "accountTo").text = acc_num
            ET.SubElement(transaction, "bankCode").text = bank_code

            if getattr(exp, 'payment_info', None):
                if exp.payment_info.constant_symbol:
                    ET.SubElement(transaction, "ks").text = exp.payment_info.constant_symbol
                if exp.payment_info.variable_symbol:
                    ET.SubElement(transaction, "vs").text = exp.payment_info.variable_symbol
                if exp.payment_info.specific_symbol:
                    ET.SubElement(transaction, "ss").text = exp.payment_info.specific_symbol

            ET.SubElement(transaction, "date").text = execution_date

            message = self._get_payment_message(exp)
            ET.SubElement(transaction, "messageForRecipient").text = message
            ET.SubElement(transaction, "comment").text = message
            ET.SubElement(transaction, "paymentType").text = "431001"

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _parse_import_response(self, xml_string):
        try:
            root = ET.fromstring(xml_string)
            result = root.find('result')

            if result is not None:
                status = result.findtext('status')
                error_code = result.findtext('errorCode')
                id_instruction = result.findtext('idInstruction')

                messages = root.findall('.//message')
                message_texts = [msg.text for msg in messages if msg is not None]

                if not message_texts:
                    message_texts = [f"Fio error code: {error_code}"]

                if status == 'ok':
                    logger.info(f"Fio API ok (Code: {error_code})")
                    return 'ok', message_texts, id_instruction
                elif status == 'warning':
                    logger.warning(f"Fio API warning (Code: {error_code})")
                    return 'warning', message_texts, id_instruction
                else:
                    logger.error(f"Fio API Error (Status: {status}, Code: {error_code})")
                    return 'error', message_texts, None
            else:
                logger.error("Missing <result> element")
                return 'error', ["Missing <result> element"], None

        except ET.ParseError:
            logger.error(f"XML parsing failed Raw: {xml_string}")
            return 'error', ["XML parsing failed"], None

    def _claim_for_import(self, expenditures, execution_date):
        """
        Reserve the expenditures before the order goes to Fio.

        The claim is one transaction with locked rows. A second import that runs
        at the same time finds the rows claimed and stops. The claim also stays
        in place when the Fio call ends with an unknown result. A lost response
        thus cannot put the order back in the queue on its own.

        Return False if one expenditure is no longer ready for import. Nothing
        is claimed then, and the caller must not send the batch.
        """
        ids = [exp.id for exp in expenditures]

        with transaction.atomic():
            # Lock in a stable order. Two imports that overlap then wait for each
            # other instead of deadlocking.
            locked = {
                current.id: current
                for current in Expediture.objects.select_for_update().filter(
                    id__in=ids
                ).select_related('import_info').order_by('id')
            }

            for exp in expenditures:
                current = locked.get(exp.id)
                if current is None or current.paid:
                    return False
                if current.import_info and not current.import_info.error:
                    return False

            for exp in expenditures:
                stale_info = locked[exp.id].import_info
                exp.import_info = ImportInfo.objects.create(imported_at=timezone.now(), due_date=execution_date)
                exp.save(update_fields=['import_info'])

                if stale_info:
                    stale_info.delete()

        return True

    def _confirm_claim(self, expenditures, order_number):
        """Write the Fio order number into the claim. Fio has the order now."""
        with transaction.atomic():
            for exp in expenditures:
                exp.import_info.order_number = order_number or ''
                exp.import_info.save(update_fields=['order_number'])

    def _release_claim(self, expenditures, mark_error):
        """
        Give the expenditures back to the import queue.

        Use this only when Fio refuses the batch. If the result of the call is
        unknown, keep the claim. An operator must then look at the order in Fio
        and revert the import by hand.

        Set mark_error to show the operator that the attempt failed. Clear
        mark_error when Fio only rate limits the batch, because the data of the
        expenditure is correct.
        """
        with transaction.atomic():
            for exp in expenditures:
                info = exp.import_info
                if info is None:
                    continue

                if mark_error:
                    # No order exists, thus the due date has no meaning. Clear it,
                    # or the expiry sweep removes the error mark at that date.
                    info.error = True
                    info.due_date = None
                    info.save(update_fields=['error', 'due_date'])
                else:
                    exp.import_info = None
                    exp.save(update_fields=['import_info'])
                    info.delete()

    def process_expenditures(self, expenditures, execution_date):
        batches = {}
        report = {
            'success_count': 0,
            'errors': [],
            'warnings': []
        }

        for exp in expenditures:
            source_account = exp.get_source_account()

            if not source_account:
                error_msg = _("Missing source grant account for expenditure ID {}.").format(exp.id)
                report['errors'].append(error_msg)
                logger.error(f"Missing source grant account for expenditure ID {exp.id}.")
                continue

            if source_account not in self.tokens:
                ui_error = _("Missing API token for account {}.").format(source_account)
                if ui_error not in report['errors']:
                    report['errors'].append(ui_error)
                    logger.error(f"Missing API token for account {source_account}.")
                continue

            if source_account not in batches:
                batches[source_account] = []
            batches[source_account].append(exp)

        for account, exps in batches.items():
            try:
                xml_data = self._generate_xml(account, exps, execution_date)
            except Exception as e:
                # The order is not sent yet. The expenditures stay in the queue.
                report['errors'].append(_("Cannot prepare the batch for account {}: {}").format(account, str(e)))
                logger.exception(f"Fio import cannot build the batch for account {account}: {str(e)}")
                continue

            if not self._claim_for_import(exps, execution_date):
                report['warnings'].append(_(
                    "Expenditures for account {} changed while the import ran. Nothing was sent. Please try again."
                ).format(account))
                logger.warning(f"Fio import cannot claim the batch for account {account}.")
                continue

            try:
                data = {
                    'token': self.tokens[account],
                    'type': 'xml'
                }
                files = {
                    'file': ('import.xml', xml_data, 'text/xml')
                }

                response = requests.post(self.FIO_IMPORT_URL, data=data, files=files, timeout=self.HTTP_TIMEOUT)

                if response.status_code == 409:
                    # Fio refuses the batch, thus no order exists.
                    self._release_claim(exps, mark_error=False)

                    warning_msg = _("Fio API requires a 30-second delay between requests. Please wait a moment and try again.")

                    report['warnings'].append(warning_msg)
                    logger.warning(f"Fio API 409 Rate Limit for account {account}.")
                    continue

                if response.status_code == 500:
                    # Fio refuses the token, thus no order exists.
                    self._release_claim(exps, mark_error=True)

                    error_msg = _("Fio API error 500: Invalid or inactive token for account {}.").format(account)
                    report['errors'].append(error_msg)
                    logger.error(f"Fio API 500 Error for account {account}. Check token validity.")
                    continue

                response.raise_for_status()

                status, messages, id_instruction = self._parse_import_response(response.text)

                with transaction.atomic():
                    if status in ['ok', 'warning']:
                        self._confirm_claim(exps, id_instruction)

                        report['success_count'] += len(exps)

                        if status == 'warning':
                            warning_msg = " | ".join([m for m in messages if m])
                            report['warnings'].append(_("Batch for account {} was accepted with warning: {}").format(account, warning_msg))

                    else:
                        # Fio refuses the batch, thus no order exists.
                        if len(messages) == len(exps):
                            for exp, msg in zip(exps, messages):
                                if msg and msg.strip().upper() != 'OK':
                                    self._release_claim([exp], mark_error=True)
                                    report['errors'].append(f"{exp.description}: {msg}")
                                else:
                                    self._release_claim([exp], mark_error=False)
                        else:
                            self._release_claim(exps, mark_error=True)
                            error_msg = " | ".join([m for m in messages if m])
                            report['errors'].append(_("API rejected batch for account {}: {}").format(account, error_msg))

            except Exception as e:
                # The batch can be on its way to Fio, but the result is unknown.
                # Keep the claim. If you release it here, a second import can
                # send the same order again and pay it twice.
                ui_error = _(
                    "Communication with Fio failed for account {}: {}. The expenditures stay marked as imported. "
                    "Check the order in Fio internet banking before you revert the import."
                ).format(account, str(e))
                report['errors'].append(ui_error)
                logger.exception(f"Fio import failed for batch on account {account}: {str(e)}")

        return report

    def _match_strength(self, expediture, abs_amount, id_instruction, message, full_target_account):
        """
        Tell how strongly an expenditure fits one bank transaction.

        A larger value is stronger evidence. MATCH_NONE means the expenditure
        does not fit the transaction.
        """
        try:
            expected_msg = self._get_payment_message(expediture)
        except ValueError:
            # We never sent a payment reference for this expenditure, thus no
            # transaction can carry one. An expenditure that failed the import
            # keeps its ImportInfo and stays a candidate, so this can happen.
            logger.debug(f"No payment message for expenditure {expediture.id}.")
            return self.MATCH_NONE

        is_msg_match = self._message_matches(expected_msg, message)
        is_amount_match = expediture.amount == abs_amount

        if expediture.payment_type == PaymentType.CARD:
            return self.MATCH_MESSAGE if is_msg_match and is_amount_match else self.MATCH_NONE

        is_batch_match = bool(id_instruction and getattr(expediture.import_info, 'order_number', None) == id_instruction)

        # An operator can pay an expenditure by hand in internet banking. The
        # expenditure then keeps no payment data, and so we have no account to
        # compare. An unknown account is no evidence, thus it must not refuse
        # the match. An account that we know and that disagrees with the bank
        # is evidence against the match, thus it still refuses it.
        target_account = expediture.get_target_account()
        is_account_match = not target_account or target_account == full_target_account

        if is_batch_match and is_msg_match:
            return self.MATCH_MESSAGE_AND_BATCH
        if is_msg_match and is_amount_match and is_account_match:
            return self.MATCH_MESSAGE
        if is_batch_match and is_amount_match and is_account_match:
            return self.MATCH_BATCH

        return self.MATCH_NONE

    def _best_matches(self, candidates, abs_amount, id_instruction, message, full_target_account):
        """
        Find the expenditures that fit one bank transaction best.

        All the expenditures of one import batch have the same order number and
        frequently also the same amount and the same target account. Only the
        bank message tells them apart. Thus the strongest match is not always
        the first candidate found, and it is not always unique. Return every
        expenditure with the strongest match. The caller must not pay any of
        them when there is more than one.
        """
        matches = []
        best = self.MATCH_NONE

        for expediture in candidates:
            strength = self._match_strength(expediture, abs_amount, id_instruction, message, full_target_account)

            if strength == self.MATCH_NONE:
                continue

            if strength > best:
                best = strength
                matches = [expediture]
            elif strength == best:
                matches.append(expediture)

        return matches

    def sync_transactions(self, days_back=14, expiry_days=1, dry_run=False, accounts=None):
        """
        Read the bank statements and mark the expenditures that the bank paid.

        Set dry_run to report the result without a write. Use it before a long
        history run, because a wide days_back reads transactions that an
        operator can have reconciled by hand already.

        Set accounts to a list of account numbers to reconcile only the
        payments from those accounts. The default reads every registered
        account.
        """
        tokens = self._select_tokens(accounts)

        date_to = datetime.date.today()
        date_from = date_to - datetime.timedelta(days=days_back)

        report = {
            'marked_paid': 0,
            'reverted': 0,
            'errors': [],
            'matches': [],
            'dry_run': dry_run,
        }

        # A transaction that this run already used. The paid flag keeps the
        # expenditure out of the next query, but a dry run writes nothing, and
        # so the run must remember the decision itself.
        consumed = set()

        for account, token in tokens.items():
            url = f"https://fioapi.fio.cz/v1/rest/periods/{token}/{date_from.isoformat()}/{date_to.isoformat()}/transactions.json"

            try:
                response = requests.get(url, timeout=self.HTTP_TIMEOUT)
                response.raise_for_status()
                data = response.json()

                transactions = data.get('accountStatement', {}).get('transactionList', {}).get('transaction', [])
                if not transactions:
                    continue

                for t in transactions:
                    if not t:
                        continue

                    amount = t.get('column1', {}).get('value', 0) if t.get('column1') else 0
                    if amount >= 0:
                        continue

                    # Fio sends the amount as a JSON float, but the expenditure
                    # keeps a decimal. Decimal('10.10') != 10.1, thus we must
                    # compare a decimal against a decimal. Go through str() to
                    # get the decimal that the float shows, not the binary value
                    # behind it.
                    abs_amount = Decimal(str(abs(amount)))

                    transaction_id = self._transaction_id(t)
                    transaction_date = self._transaction_date(t)

                    # One transaction pays one expenditure. Read the record
                    # before the match, or a history run marks a second
                    # expenditure with a transaction that is already used.
                    if transaction_id and ReconciledTransaction.objects.filter(transaction_id=transaction_id).exists():
                        continue

                    id_instruction = str(t.get('column17', {}).get('value', '')) if t.get('column17') else None
                    message = self._reference_text(t)
                    target_acc = str(t.get('column2', {}).get('value', '')) if t.get('column2') else None
                    bank_code = str(t.get('column3', {}).get('value', '')) if t.get('column3') else None
                    full_target_account = f"{target_acc}/{bank_code}" if target_acc and bank_code else None

                    # Every unpaid expenditure is a candidate. An ImportInfo row
                    # says that a Fio order is live, not that the bank never
                    # paid, and it goes away when the order expires. Thus it
                    # cannot decide who is eligible. _match_strength() refuses
                    # the payment types that carry no reference of ours, and
                    # ReconciledTransaction stops a transaction from paying
                    # twice.
                    query = Q(paid=False)

                    match_q = Q(amount=abs_amount)
                    if id_instruction:
                        match_q |= Q(import_info__order_number=id_instruction or '')

                    candidates = Expediture.objects.filter(query & match_q).exclude(
                        id__in=consumed
                    ).select_related('import_info', 'payment_info', 'linked_expenditure')

                    matches = self._best_matches(candidates, abs_amount, id_instruction, message, full_target_account)

                    if len(matches) > 1:
                        matched_ids = ', '.join(str(exp.id) for exp in matches)
                        logger.warning(
                            f"Ambiguous Fio transaction on account {account} "
                            f"(amount {abs_amount}, order number {id_instruction}, message {message!r}): "
                            f"expenditures {matched_ids} match equally well."
                        )
                        report['errors'].append(
                            f"Account {account}: a payment of {abs_amount} matches expenditures {matched_ids} "
                            "equally well. Mark the correct one as paid manually."
                        )
                        continue

                    if matches:
                        matched = matches[0]
                        consumed.add(matched.id)

                        report['marked_paid'] += 1
                        report['matches'].append(
                            f"{transaction_date or '?'} {abs_amount} on {account} "
                            f"-> expenditure {matched.id} (ticket {matched.ticket_id}, {matched.description})"
                        )

                        if dry_run:
                            continue

                        with transaction.atomic():
                            matched.mark_paid()

                            if transaction_id:
                                ReconciledTransaction.objects.create(
                                    transaction_id=transaction_id,
                                    account=account,
                                    date=transaction_date,
                                    amount=abs_amount,
                                    reference=message[:255],
                                    expediture=matched,
                                )
                            else:
                                logger.warning(
                                    f"Fio transaction on account {account} (amount {abs_amount}, "
                                    f"message {message!r}) carries no transaction id. "
                                    "It can match a second expenditure in a later run."
                                )

            except Exception as e:
                logger.exception(f"Error when downloading transactions for account {account}: {e}")
                report['errors'].append(f"Account {account}: {str(e)}")

        expiry_limit = date_to - datetime.timedelta(days=expiry_days)

        expired_exps = Expediture.objects.filter(
            import_info__isnull=False,
            import_info__due_date__lt=expiry_limit,
            paid=False
        ).exclude(id__in=consumed).select_related(
            'import_info',
            'ticket__topic__grant',
            'linked_expenditure__ticket__topic__grant',
        )

        for exp in expired_exps:
            # Expire only the orders of the accounts that this run read. The
            # bank can have paid an order on another account, and a run that
            # did not read that statement must not revert it.
            if accounts is not None:
                source_account = exp.get_source_account()

                if not source_account or self.normalize_account(source_account) not in tokens:
                    continue

            report['reverted'] += 1

            if dry_run:
                continue

            with transaction.atomic():
                info_to_delete = exp.import_info
                exp.import_info = None
                exp.save(update_fields=['import_info'])

                if info_to_delete:
                    info_to_delete.delete()

        return report
