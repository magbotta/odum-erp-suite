"""Education SIS hooks — fee invoice creation linked to Accounting (§7)."""
import datetime

from apps.education_sis.models import StudentFeeInvoice
from core.numbering.service import get_next_number


def set_invoice_number(fee_invoice: StudentFeeInvoice) -> None:
    if not fee_invoice.invoice_number:
        fee_invoice.invoice_number = get_next_number("SINV", company_id=fee_invoice.company_id)


def issue_fee_invoice(fee_invoice: StudentFeeInvoice) -> None:
    """Issue the fee invoice — number it and link to Accounting SalesInvoice."""
    set_invoice_number(fee_invoice)
    fee_invoice.status = StudentFeeInvoice.Status.ISSUED
    if not fee_invoice.issue_date:
        fee_invoice.issue_date = datetime.date.today()
    _create_accounting_invoice(fee_invoice)


def _create_accounting_invoice(fee_invoice: StudentFeeInvoice) -> None:
    """
    Creates an Accounting SalesInvoice for tuition/fees and links back.
    Skips gracefully if Accounting models are unavailable.
    """
    if fee_invoice.accounting_invoice_id:
        return
    try:
        from apps.accounting.models import SalesInvoice, SalesInvoiceLine
    except ImportError:
        return

    student = fee_invoice.student
    description = "Tuition/Fees — {} — {}".format(student, fee_invoice.academic_year or "")

    inv = SalesInvoice.objects.create(
        customer_name="{} {}".format(student.first_name, student.last_name),
        customer_email=student.email or student.guardian_email,
        invoice_number=fee_invoice.invoice_number,
        status="submitted",
        invoice_date=fee_invoice.issue_date or datetime.date.today(),
        due_date=fee_invoice.due_date,
        currency="USD",
        subtotal=fee_invoice.amount,
        tax_amount=0,
        grand_total=fee_invoice.amount,
        company_id=fee_invoice.company_id,
    )
    SalesInvoiceLine.objects.create(
        invoice=inv,
        description=description,
        quantity=1,
        unit_price=fee_invoice.amount,
        amount=fee_invoice.amount,
        company_id=fee_invoice.company_id,
    )
    fee_invoice.accounting_invoice_id = inv.id


def record_payment(fee_invoice: StudentFeeInvoice, amount) -> None:
    """Record a payment against a fee invoice."""
    from decimal import Decimal
    fee_invoice.paid_amount = (fee_invoice.paid_amount or Decimal("0")) + Decimal(str(amount))
    if fee_invoice.paid_amount >= fee_invoice.amount:
        fee_invoice.status = StudentFeeInvoice.Status.PAID
    else:
        fee_invoice.status = StudentFeeInvoice.Status.PARTIALLY_PAID
    fee_invoice.save(update_fields=["paid_amount", "status"])


def cancel_fee_invoice(fee_invoice: StudentFeeInvoice) -> None:
    fee_invoice.status = StudentFeeInvoice.Status.CANCELLED
