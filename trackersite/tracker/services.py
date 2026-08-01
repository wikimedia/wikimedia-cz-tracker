from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from tracker.models import Expediture, ExpenditureState, PaymentInfo, PaymentType
from .fio import FioPaymentManager


class PaymentService:
    @staticmethod
    def update_payment_details(expenditure, payment_type, payment_data, commit=True):
        is_imported = expenditure.import_info and expenditure.import_info.imported_at and not expenditure.import_info.error
        if expenditure.paid or is_imported:
            raise ValueError(_('You cannot modify payment details of an already imported or paid expenditure.'))

        if expenditure.import_info:
            expenditure.import_info.error = False

        if payment_type == 'bank_transfer':
            if getattr(expenditure, 'payment_info_id', None):
                p_info = expenditure.payment_info
            else:
                p_info = PaymentInfo()

            p_info.saved_account = payment_data.get('saved_account')
            p_info.account_number = payment_data.get('account_number')
            p_info.variable_symbol = payment_data.get('variable_symbol')
            p_info.specific_symbol = payment_data.get('specific_symbol')
            p_info.constant_symbol = payment_data.get('constant_symbol')

            if commit:
                p_info.save()

            expenditure.payment_info = p_info
        else:
            if getattr(expenditure, 'payment_info_id', None):
                expenditure.payment_info.delete()
                expenditure.payment_info = None

        return expenditure

    @staticmethod
    def process_cofinancing_link(expenditure, source_ticket, source_account, cof_amount, commit=True):
        if not cof_amount:
            return expenditure

        # if there is no space between # and ticket id, Django JS automatically change the couting of the expedntirues when adding a new cofinancing
        income_desc = f"Co-financing from ticket # {source_ticket.id}" if source_ticket else f"Co-financing income from account {source_account}"
        expenditure.description = income_desc
        expenditure.amount = -abs(cof_amount)

        if commit:
            with transaction.atomic():
                expenditure.save()

                if source_ticket:
                    if expenditure.linked_expenditure:
                        linked = expenditure.linked_expenditure
                        linked.ticket = source_ticket
                        linked.amount = abs(cof_amount)
                        linked.description = f"Co-financing for ticket #{expenditure.ticket_id}"
                        linked.save()
                    else:
                        transfer = Expediture.objects.create(
                            ticket=source_ticket,
                            description=f"Co-financing for ticket #{expenditure.ticket_id}",
                            amount=abs(cof_amount),
                            payment_type=PaymentType.INTERNAL_TRANSFER,
                            linked_expenditure=expenditure
                        )
                        expenditure.linked_expenditure = transfer
                        expenditure.save(update_fields=['linked_expenditure'])
                else:
                    if expenditure.linked_expenditure:
                        expenditure.linked_expenditure.delete()
                        expenditure.linked_expenditure = None
                        expenditure.save(update_fields=['linked_expenditure'])

        return expenditure

    @staticmethod
    def revert_import(expenditure_id):
        exp = Expediture.objects.get(id=expenditure_id)
        if exp.get_computed_state() == ExpenditureState.PAID:
            raise ValueError(_('Cannot revert import: this expenditure is already paid.'))

        if exp.import_info:
            exp.import_info.delete()
            return True
        return False

    @staticmethod
    def execute_fio_import(expenditure_ids, execution_date):
        to_import = Expediture.objects.filter(id__in=expenditure_ids).select_related(
            'ticket__topic__grant',
            'payment_info',
            'linked_expenditure'
        )

        manager = FioPaymentManager()
        return manager.process_expenditures(to_import, execution_date)
