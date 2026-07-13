"""Business logic hooks for PurchaseBill submission: GL posting (§6.1)."""
from decimal import Decimal


def post_bill_to_gl(bill) -> None:
    """
    Create and submit a JournalEntry for a PurchaseBill on submission.
    Cr. Accounts Payable (liability) for grand_total
    Dr. Expense account per line item (or fallback to first expense account)
    """
    from apps.accounting.models import (
        ChartOfAccount,
        JournalEntry,
        JournalEntryLine,
    )
    from apps.accounting.hooks.journal_entry import submit_journal_entry

    entry = JournalEntry.objects.create(
        company_id=bill.company_id,
        entry_type=JournalEntry.EntryType.JOURNAL,
        posting_date=bill.posting_date,
        narration=f"Purchase Bill {bill.bill_number or bill.pk}",
        voucher_type="PurchaseBill",
        voucher_no=str(bill.pk),
    )

    # Credit: Accounts Payable
    ap_account = ChartOfAccount.objects.filter(
        company_id=bill.company_id,
        account_type=ChartOfAccount.AccountType.LIABILITY,
        account_name__icontains="payable",
        is_active=True,
    ).first()

    if ap_account:
        JournalEntryLine.objects.create(
            entry=entry,
            account=ap_account,
            debit_amount=Decimal("0"),
            credit_amount=bill.grand_total,
            currency=bill.currency,
            exchange_rate=bill.exchange_rate,
            party_type="Vendor",
            party_id=bill.vendor_id,
        )

    # Debit: per line item expense account, or fallback to first expense account
    items = list(bill.items.all())
    if items:
        for item in items:
            expense_account = item.expense_account
            if expense_account is None:
                expense_account = ChartOfAccount.objects.filter(
                    company_id=bill.company_id,
                    account_type=ChartOfAccount.AccountType.EXPENSE,
                    is_active=True,
                ).first()
            if expense_account:
                JournalEntryLine.objects.create(
                    entry=entry,
                    account=expense_account,
                    debit_amount=item.amount,
                    credit_amount=Decimal("0"),
                    currency=bill.currency,
                    exchange_rate=bill.exchange_rate,
                )
    else:
        # No line items — debit first available expense account for grand_total
        fallback_expense = ChartOfAccount.objects.filter(
            company_id=bill.company_id,
            account_type=ChartOfAccount.AccountType.EXPENSE,
            is_active=True,
        ).first()
        if fallback_expense:
            JournalEntryLine.objects.create(
                entry=entry,
                account=fallback_expense,
                debit_amount=bill.grand_total,
                credit_amount=Decimal("0"),
                currency=bill.currency,
                exchange_rate=bill.exchange_rate,
            )

    submit_journal_entry(entry)

    bill.journal_entry = entry
    bill.status = "submitted"
    bill.outstanding_amount = bill.grand_total
    bill.save(update_fields=["journal_entry", "status", "outstanding_amount"])
