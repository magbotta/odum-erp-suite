"""Business logic hooks for Payment: GL posting and invoice allocation (§6.1, §11)."""
from decimal import Decimal
import uuid


def post_payment_to_gl(payment) -> None:
    """
    Create and submit a JournalEntry for a Payment.
    receive: Dr. Bank/Cash (asset)  Cr. AR (asset/receivable)
    pay:     Dr. AP (liability)     Cr. Bank/Cash (asset)
    """
    from apps.accounting.models import (
        ChartOfAccount,
        JournalEntry,
        JournalEntryLine,
    )
    from apps.accounting.hooks.journal_entry import submit_journal_entry

    entry = JournalEntry.objects.create(
        company_id=payment.company_id,
        entry_type=JournalEntry.EntryType.JOURNAL,
        posting_date=payment.payment_date,
        narration=f"Payment {payment.payment_type} {payment.amount} {payment.currency}",
        voucher_type="Payment",
        voucher_no=str(payment.pk),
    )

    # Look up accounts
    cash_bank_account = ChartOfAccount.objects.filter(
        company_id=payment.company_id,
        account_type=ChartOfAccount.AccountType.ASSET,
        is_active=True,
    ).filter(
        account_name__icontains="cash"
    ).first() or ChartOfAccount.objects.filter(
        company_id=payment.company_id,
        account_type=ChartOfAccount.AccountType.ASSET,
        account_name__icontains="bank",
        is_active=True,
    ).first()

    ar_account = ChartOfAccount.objects.filter(
        company_id=payment.company_id,
        account_type=ChartOfAccount.AccountType.ASSET,
        account_name__icontains="receivable",
        is_active=True,
    ).first()

    ap_account = ChartOfAccount.objects.filter(
        company_id=payment.company_id,
        account_type=ChartOfAccount.AccountType.LIABILITY,
        account_name__icontains="payable",
        is_active=True,
    ).first()

    amount = payment.amount
    currency = payment.currency
    exchange_rate = payment.exchange_rate

    if payment.payment_type == "receive":
        # Dr. Bank/Cash, Cr. AR
        if cash_bank_account:
            JournalEntryLine.objects.create(
                entry=entry,
                account=cash_bank_account,
                debit_amount=amount,
                credit_amount=Decimal("0"),
                currency=currency,
                exchange_rate=exchange_rate,
            )
        if ar_account:
            JournalEntryLine.objects.create(
                entry=entry,
                account=ar_account,
                debit_amount=Decimal("0"),
                credit_amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
                party_type="Customer",
                party_id=payment.party_id,
            )
    elif payment.payment_type == "pay":
        # Dr. AP, Cr. Bank/Cash
        if ap_account:
            JournalEntryLine.objects.create(
                entry=entry,
                account=ap_account,
                debit_amount=amount,
                credit_amount=Decimal("0"),
                currency=currency,
                exchange_rate=exchange_rate,
                party_type="Vendor",
                party_id=payment.party_id,
            )
        if cash_bank_account:
            JournalEntryLine.objects.create(
                entry=entry,
                account=cash_bank_account,
                debit_amount=Decimal("0"),
                credit_amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
            )

    submit_journal_entry(entry)

    payment.journal_entry = entry
    payment.status = "processed"
    payment.save(update_fields=["journal_entry", "status"])


def allocate_payment_to_invoice(payment, invoice_type: str, invoice_id: uuid.UUID, amount: Decimal) -> None:
    """
    Allocate a portion of a payment against a SalesInvoice or PurchaseBill.
    Reduces outstanding_amount on the invoice and updates its status accordingly.
    """
    from apps.accounting.models import (
        PaymentAllocation,
        SalesInvoice,
        PurchaseBill,
    )
    from django.utils import timezone

    # Create allocation record
    PaymentAllocation.objects.create(
        company_id=payment.company_id,
        payment=payment,
        invoice_type=invoice_type,
        invoice_id=invoice_id,
        allocated_amount=amount,
        currency=payment.currency,
        allocation_date=payment.payment_date,
    )

    # Retrieve and update the invoice
    if invoice_type == "SalesInvoice":
        invoice = SalesInvoice.objects.filter(id=invoice_id).first()
        if invoice:
            invoice.outstanding_amount = max(Decimal("0"), invoice.outstanding_amount - amount)
            if invoice.outstanding_amount <= Decimal("0"):
                invoice.status = "paid"
            elif invoice.outstanding_amount < invoice.grand_total:
                invoice.status = "partially_paid"
            invoice.save(update_fields=["outstanding_amount", "status"])
    elif invoice_type == "PurchaseBill":
        bill = PurchaseBill.objects.filter(id=invoice_id).first()
        if bill:
            bill.outstanding_amount = max(Decimal("0"), bill.outstanding_amount - amount)
            if bill.outstanding_amount <= Decimal("0"):
                bill.status = "paid"
            elif bill.outstanding_amount < bill.grand_total:
                bill.status = "partially_paid"
            bill.save(update_fields=["outstanding_amount", "status"])
