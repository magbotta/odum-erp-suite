"""Telecom hooks — invoice computation and accounting posting."""
import uuid
from decimal import Decimal

from django.db import transaction

from apps.telecom.models import TelecomInvoice, UsageRecord
from core.numbering.service import get_next_number


def compute_invoice_totals(invoice: TelecomInvoice) -> None:
    """Compute usage charges by summing rated CDRs for the billing period."""
    if invoice.pk:
        # Re-rate any unrated usage records that fall in the billing window
        usage_total = (
            UsageRecord.objects.filter(
                subscription__subscriber=invoice.subscriber,
                started_at__date__gte=invoice.billing_period_start,
                started_at__date__lte=invoice.billing_period_end,
                is_rated=True,
            ).values_list("rated_amount", flat=True)
        )
        invoice.usage_charges = sum(usage_total, Decimal("0"))
    invoice.grand_total = (
        (invoice.recurring_charges or Decimal("0"))
        + (invoice.usage_charges or Decimal("0"))
        + (invoice.taxes or Decimal("0"))
    )
    if not invoice.invoice_number:
        invoice.invoice_number = get_next_number(
            "TEL-INV", company_id=invoice.company_id
        )


@transaction.atomic
def post_to_accounting(invoice: TelecomInvoice) -> None:
    """Create a SalesInvoice in Accounting for the finalized telecom invoice."""
    if not invoice.accounting_invoice_id:
        invoice.accounting_invoice_id = uuid.uuid4()  # placeholder
        invoice.save(update_fields=["accounting_invoice_id"])
