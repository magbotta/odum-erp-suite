"""Business logic for SalesInvoice submission: GL posting (§6.1)."""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone


def post_invoice_to_gl(invoice) -> None:
    """
    Create and submit a JournalEntry for a SalesInvoice on submission.
    Dr. Accounts Receivable (party: Customer)
    Cr. Income account per line item
    """
    from apps.accounting.models import (
        ChartOfAccount,
        JournalEntry,
        JournalEntryLine,
    )

    entry = JournalEntry.objects.create(
        company_id=invoice.company_id,
        entry_type=JournalEntry.EntryType.JOURNAL,
        posting_date=invoice.posting_date,
        narration=f"Sales Invoice {invoice.invoice_number or invoice.pk}",
        voucher_type="SalesInvoice",
        voucher_no=str(invoice.pk),
    )

    # Debit: AR account (look up the company's default AR account)
    # For now we use a sentinel lookup — in production this would be from Company settings
    ar_account = ChartOfAccount.objects.filter(
        company_id=invoice.company_id,
        account_type=ChartOfAccount.AccountType.ASSET,
        account_name__icontains="receivable",
    ).first()

    if ar_account:
        JournalEntryLine.objects.create(
            entry=entry,
            account=ar_account,
            debit_amount=invoice.grand_total,
            credit_amount=Decimal("0"),
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
            party_type="Customer",
            party_id=invoice.customer_id,
        )

    # Credit: income per line
    for item in invoice.items.all():
        if item.income_account_id:
            JournalEntryLine.objects.create(
                entry=entry,
                account_id=item.income_account_id,
                debit_amount=Decimal("0"),
                credit_amount=item.amount,
                currency=invoice.currency,
                exchange_rate=invoice.exchange_rate,
            )

    from apps.accounting.hooks.journal_entry import submit_journal_entry
    submit_journal_entry(entry)

    invoice.journal_entry = entry
    invoice.status = "submitted"
    invoice.outstanding_amount = invoice.grand_total
    invoice.save(update_fields=["journal_entry", "status", "outstanding_amount"])
