# -*- coding: utf-8 -*-
import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.db import transaction
import requests
import re
import logging
from django.utils.translation import ugettext_lazy as _

from tracker.models import PaymentType, ImportInfo, Expediture

logger = logging.getLogger(__name__)


class FioPaymentManager:
    FIO_IMPORT_URL = 'https://fioapi.fio.cz/v1/rest/import/'

    # How strongly an expenditure fits a bank transaction, strongest first.
    # The bank message is the only field that names one expenditure. The order
    # number is the same for all the expenditures of one import batch, and so
    # it must rank below the message.
    MATCH_MESSAGE_AND_BATCH = 3
    MATCH_MESSAGE = 2
    MATCH_BATCH = 1
    MATCH_NONE = 0

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

                data = {
                    'token': self.tokens[account],
                    'type': 'xml'
                }
                files = {
                    'file': ('import.xml', xml_data, 'text/xml')
                }

                response = requests.post(self.FIO_IMPORT_URL, data=data, files=files)

                if response.status_code == 409:
                    warning_msg = _("Fio API requires a 30-second delay between requests. Please wait a moment and try again.")

                    report['warnings'].append(warning_msg)
                    logger.warning(f"Fio API 409 Rate Limit for account {account}.")
                    continue

                if response.status_code == 500:
                    error_msg = _("Fio API error 500: Invalid or inactive token for account {}.").format(account)
                    report['errors'].append(error_msg)
                    logger.error(f"Fio API 500 Error for account {account}. Check token validity.")
                    with transaction.atomic():
                        for exp in exps:
                            if exp.import_info:
                                exp.import_info.delete()
                            exp.import_info = ImportInfo.objects.create(error=True)
                            exp.save(update_fields=['import_info'])
                    continue

                response.raise_for_status()

                status, messages, id_instruction = self._parse_import_response(response.text)

                with transaction.atomic():
                    if status in ['ok', 'warning']:
                        for exp in exps:
                            new_import_info = ImportInfo.objects.create(imported_at=timezone.now(), due_date=execution_date, order_number=id_instruction or '')
                            if exp.import_info:
                                exp.import_info.delete()
                            exp.import_info = new_import_info
                            exp.save()

                        report['success_count'] += len(exps)

                        if status == 'warning':
                            warning_msg = " | ".join([m for m in messages if m])
                            report['warnings'].append(_("Batch for account {} was accepted with warning: {}").format(account, warning_msg))

                    else:
                        if len(messages) == len(exps):
                            for exp, msg in zip(exps, messages):
                                if msg and msg.strip().upper() != 'OK':
                                    if exp.import_info:
                                        exp.import_info.delete()
                                    exp.import_info = ImportInfo.objects.create(error=True)
                                    exp.save(update_fields=['import_info'])
                                    report['errors'].append(f"{exp.description}: {msg}")
                                else:
                                    if exp.import_info:
                                        old_info = exp.import_info
                                        exp.import_info = None
                                        exp.save(update_fields=['import_info'])
                                        old_info.delete()
                        else:
                            for exp in exps:
                                if exp.import_info:
                                    exp.import_info.delete()
                                exp.import_info = ImportInfo.objects.create(error=True)
                                exp.save(update_fields=['import_info'])
                            error_msg = " | ".join([m for m in messages if m])
                            report['errors'].append(_("API rejected batch for account {}: {}").format(account, error_msg))

            except requests.exceptions.ConnectionError as e:
                with transaction.atomic():
                    for exp in exps:
                        if exp.import_info:
                            exp.import_info.delete()
                        exp.import_info = ImportInfo.objects.create(error=True)
                        exp.save(update_fields=['import_info'])

                ui_error = _(
                    "Connection error to Fio API for account {}. Please check your network or try again later.").format(
                    account)
                report['errors'].append(ui_error)
                logger.exception(f"Fio import connection failed for account {account}: {str(e)}")

            except Exception as e:
                with transaction.atomic():
                    for exp in exps:
                        if exp.import_info:
                            exp.import_info.delete()
                        exp.import_info = ImportInfo.objects.create(error=True)
                        exp.save(update_fields=['import_info'])

                ui_error = _("Communication with Fio failed for account {}: {}").format(account, str(e))
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
        is_account_match = expediture.get_target_account() == full_target_account

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

    def sync_transactions(self, days_back=14, expiry_days=1):
        date_to = datetime.date.today()
        date_from = date_to - datetime.timedelta(days=days_back)

        report = {
            'marked_paid': 0,
            'reverted': 0,
            'errors': []
        }

        for account, token in self.tokens.items():
            url = f"https://fioapi.fio.cz/v1/rest/periods/{token}/{date_from.isoformat()}/{date_to.isoformat()}/transactions.json"

            try:
                response = requests.get(url)
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

                    id_instruction = str(t.get('column17', {}).get('value', '')) if t.get('column17') else None
                    message = str(t.get('column16', {}).get('value', '')) if t.get('column16') else ""
                    target_acc = str(t.get('column2', {}).get('value', '')) if t.get('column2') else None
                    bank_code = str(t.get('column3', {}).get('value', '')) if t.get('column3') else None
                    full_target_account = f"{target_acc}/{bank_code}" if target_acc and bank_code else None

                    query = Q(paid=False) & (Q(import_info__isnull=False) | Q(payment_type=PaymentType.CARD))

                    match_q = Q(amount=abs_amount)
                    if id_instruction:
                        match_q |= Q(import_info__order_number=id_instruction or '')

                    candidates = Expediture.objects.filter(query & match_q).select_related('import_info', 'payment_info', 'linked_expenditure')

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
                        with transaction.atomic():
                            matches[0].mark_paid()
                            report['marked_paid'] += 1

            except Exception as e:
                logger.exception(f"Error when downloading transactions for account {account}: {e}")
                report['errors'].append(f"Account {account}: {str(e)}")

        expiry_limit = date_to - datetime.timedelta(days=expiry_days)

        expired_exps = Expediture.objects.filter(
            import_info__isnull=False,
            import_info__due_date__lt=expiry_limit,
            paid=False
        )

        for exp in expired_exps:
            with transaction.atomic():
                info_to_delete = exp.import_info
                exp.import_info = None
                exp.save(update_fields=['import_info'])

                if info_to_delete:
                    info_to_delete.delete()

                report['reverted'] += 1

        return report
