"""Education SIS hooks — fee invoice creation linked to Accounting."""
import uuid

from apps.education_sis.models import StudentFeeInvoice


def create_accounting_invoice(fee_invoice: StudentFeeInvoice) -> None:
    """
    Placeholder: creates an Accounting SalesInvoice for tuition/fees.
    In production this calls the Accounting service interface.
    """
    if not fee_invoice.accounting_invoice_id:
        # In a real deployment: call accounting service to create invoice.
        # For now store a placeholder UUID so the FK is populated.
        fee_invoice.accounting_invoice_id = uuid.uuid4()
