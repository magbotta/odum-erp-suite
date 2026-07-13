"""
Accounting action endpoints: submit/cancel/reverse, payments, reconciliation,
period management, and financial reports (§6.1).

NOTE: do NOT add `from __future__ import annotations` — Pydantic v2 compat requires
      runtime annotation evaluation.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["Accounting Actions"])


# ---------------------------------------------------------------------------
# Shared response schemas
# ---------------------------------------------------------------------------

class ActionResponse(Schema):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Report output schemas
# ---------------------------------------------------------------------------

class TrialBalanceLine(Schema):
    account_number: str
    account_name: str
    account_type: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


class AgedBucket(Schema):
    party_id: str
    party_name: str
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total_outstanding: Decimal


class IncomeStatementLine(Schema):
    section: str
    account_name: str
    amount: Decimal


class IncomeStatementResponse(Schema):
    from_date: str
    to_date: str
    total_income: Decimal
    total_expense: Decimal
    net_income: Decimal
    lines: List[IncomeStatementLine]


# ---------------------------------------------------------------------------
# Allocation request body
# ---------------------------------------------------------------------------

class AllocateBody(Schema):
    invoice_type: str   # "SalesInvoice" | "PurchaseBill"
    invoice_id: uuid.UUID
    amount: Decimal


class ReconcileBody(Schema):
    journal_entry_id: uuid.UUID


# ---------------------------------------------------------------------------
# 1. Journal Entry actions
# ---------------------------------------------------------------------------

@router.post("/journal-entries/{entry_id}/submit", response=ActionResponse)
def submit_journal_entry_endpoint(request, entry_id: uuid.UUID):
    from apps.accounting.models import JournalEntry
    from apps.accounting.hooks.journal_entry import submit_journal_entry

    entry = get_object_or_404(JournalEntry, id=entry_id, is_deleted=False)
    if entry.status != "draft":
        return {"ok": False, "message": f"Journal entry is already {entry.status}."}
    try:
        submit_journal_entry(entry)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Journal entry {entry_id} submitted."}


@router.post("/journal-entries/{entry_id}/reverse", response=ActionResponse)
def reverse_journal_entry(request, entry_id: uuid.UUID):
    from apps.accounting.models import JournalEntry, JournalEntryLine
    from apps.accounting.hooks.journal_entry import submit_journal_entry

    entry = get_object_or_404(JournalEntry, id=entry_id, is_deleted=False)
    if entry.status != "submitted":
        return {"ok": False, "message": "Only submitted entries can be reversed."}
    if entry.is_reversed:
        return {"ok": False, "message": "Entry has already been reversed."}

    reverse_je = JournalEntry.objects.create(
        company_id=entry.company_id,
        entry_type=JournalEntry.EntryType.REVERSAL,
        posting_date=entry.posting_date,
        reference=f"REV/{entry.reference or entry.pk}",
        narration=f"Reversal of {entry.narration or entry.pk}",
        voucher_type=entry.voucher_type,
        voucher_no=entry.voucher_no,
        reversal_of=entry,
    )

    for line in entry.lines.all():
        JournalEntryLine.objects.create(
            entry=reverse_je,
            account_id=line.account_id,
            cost_center_id=line.cost_center_id,
            debit_amount=line.credit_amount,
            credit_amount=line.debit_amount,
            currency=line.currency,
            exchange_rate=line.exchange_rate,
            party_type=line.party_type,
            party_id=line.party_id,
            description=line.description,
            company_id=line.company_id,
        )

    try:
        submit_journal_entry(reverse_je)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    entry.is_reversed = True
    entry.status = "cancelled"
    entry.save(update_fields=["is_reversed", "status"])
    return {"ok": True, "message": f"Reversal entry created: {reverse_je.pk}"}


# ---------------------------------------------------------------------------
# 2. Sales Invoice actions (fixed: lowercase status)
# ---------------------------------------------------------------------------

@router.post("/sales-invoices/{invoice_id}/submit", response=ActionResponse)
def submit_sales_invoice(request, invoice_id: uuid.UUID):
    from apps.accounting.models import SalesInvoice
    from apps.accounting.hooks.sales_invoice import post_invoice_to_gl

    invoice = get_object_or_404(SalesInvoice, id=invoice_id, is_deleted=False)
    if invoice.status != "draft":
        return {"ok": False, "message": f"Invoice is already {invoice.status}."}

    post_invoice_to_gl(invoice)
    return {"ok": True, "message": f"Invoice {invoice.invoice_number} submitted."}


@router.post("/sales-invoices/{invoice_id}/cancel", response=ActionResponse)
def cancel_sales_invoice(request, invoice_id: uuid.UUID):
    from apps.accounting.models import SalesInvoice, JournalEntry, JournalEntryLine

    invoice = get_object_or_404(SalesInvoice, id=invoice_id, is_deleted=False)
    if invoice.status not in ("submitted", "overdue"):
        return {"ok": False, "message": f"Cannot cancel invoice in {invoice.status} status."}

    # Create a reversing journal entry if one exists
    if invoice.journal_entry_id:
        original = JournalEntry.objects.filter(id=invoice.journal_entry_id).first()
        if original and not original.is_reversed:
            reverse_je = JournalEntry.objects.create(
                company_id=invoice.company_id,
                entry_type=JournalEntry.EntryType.REVERSAL,
                posting_date=original.posting_date,
                reference=f"REV/{invoice.invoice_number}",
                narration=f"Reversal of {invoice.invoice_number}",
                status="submitted",
                voucher_type="SalesInvoice",
                voucher_no=str(invoice.pk),
                reversal_of=original,
            )
            for line in original.lines.all():
                JournalEntryLine.objects.create(
                    entry=reverse_je,
                    account_id=line.account_id,
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    currency=line.currency,
                    company_id=line.company_id,
                )
            original.is_reversed = True
            original.save(update_fields=["is_reversed"])

    invoice.status = "cancelled"
    invoice.save(update_fields=["status"])
    return {"ok": True, "message": f"Invoice {invoice.invoice_number} cancelled and GL reversed."}


# ---------------------------------------------------------------------------
# 3. Purchase Bill actions
# ---------------------------------------------------------------------------

@router.post("/purchase-bills/{bill_id}/submit", response=ActionResponse)
def submit_purchase_bill(request, bill_id: uuid.UUID):
    from apps.accounting.models import PurchaseBill
    from apps.accounting.hooks.purchase_bill import post_bill_to_gl

    bill = get_object_or_404(PurchaseBill, id=bill_id, is_deleted=False)
    if bill.status != "draft":
        return {"ok": False, "message": f"Bill is already {bill.status}."}
    try:
        post_bill_to_gl(bill)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Purchase bill {bill.bill_number or bill_id} submitted."}


@router.post("/purchase-bills/{bill_id}/cancel", response=ActionResponse)
def cancel_purchase_bill(request, bill_id: uuid.UUID):
    from apps.accounting.models import PurchaseBill, JournalEntry, JournalEntryLine

    bill = get_object_or_404(PurchaseBill, id=bill_id, is_deleted=False)
    if bill.status not in ("submitted", "overdue"):
        return {"ok": False, "message": f"Cannot cancel bill in {bill.status} status."}

    if bill.journal_entry_id:
        original = JournalEntry.objects.filter(id=bill.journal_entry_id).first()
        if original and not original.is_reversed:
            reverse_je = JournalEntry.objects.create(
                company_id=bill.company_id,
                entry_type=JournalEntry.EntryType.REVERSAL,
                posting_date=original.posting_date,
                reference=f"REV/{bill.bill_number or bill.pk}",
                narration=f"Reversal of purchase bill {bill.bill_number or bill.pk}",
                status="submitted",
                voucher_type="PurchaseBill",
                voucher_no=str(bill.pk),
                reversal_of=original,
            )
            for line in original.lines.all():
                JournalEntryLine.objects.create(
                    entry=reverse_je,
                    account_id=line.account_id,
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    currency=line.currency,
                    company_id=line.company_id,
                )
            original.is_reversed = True
            original.save(update_fields=["is_reversed"])

    bill.status = "cancelled"
    bill.save(update_fields=["status"])
    return {"ok": True, "message": f"Bill {bill.bill_number or bill_id} cancelled."}


# ---------------------------------------------------------------------------
# 4. Payment actions
# ---------------------------------------------------------------------------

@router.post("/payments/{payment_id}/process", response=ActionResponse)
def process_payment(request, payment_id: uuid.UUID):
    from apps.accounting.models import Payment
    from apps.accounting.hooks.payment import post_payment_to_gl

    payment = get_object_or_404(Payment, id=payment_id, is_deleted=False)
    if payment.status != "pending":
        return {"ok": False, "message": f"Payment is already {payment.status}."}
    try:
        post_payment_to_gl(payment)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Payment {payment_id} processed and GL posted."}


@router.post("/payments/{payment_id}/allocate", response=ActionResponse)
def allocate_payment(request, payment_id: uuid.UUID, body: AllocateBody):
    from apps.accounting.models import Payment
    from apps.accounting.hooks.payment import allocate_payment_to_invoice

    payment = get_object_or_404(Payment, id=payment_id, is_deleted=False)
    if payment.status != "processed":
        return {"ok": False, "message": "Payment must be processed before allocation."}
    if body.invoice_type not in ("SalesInvoice", "PurchaseBill"):
        return {"ok": False, "message": "invoice_type must be 'SalesInvoice' or 'PurchaseBill'."}
    try:
        allocate_payment_to_invoice(payment, body.invoice_type, body.invoice_id, body.amount)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Allocated {body.amount} to {body.invoice_type}/{body.invoice_id}."}


# ---------------------------------------------------------------------------
# 5. Bank reconciliation
# ---------------------------------------------------------------------------

@router.post("/bank-transactions/{txn_id}/reconcile", response=ActionResponse)
def reconcile_bank_transaction(request, txn_id: uuid.UUID, body: ReconcileBody):
    from apps.accounting.models import BankTransaction, JournalEntry

    txn = get_object_or_404(BankTransaction, id=txn_id, is_deleted=False)
    if txn.is_reconciled:
        return {"ok": False, "message": "Transaction is already reconciled."}

    je = get_object_or_404(JournalEntry, id=body.journal_entry_id, is_deleted=False)
    txn.is_reconciled = True
    txn.reconciled_je = je
    txn.reconciled_at = timezone.now()
    txn.save(update_fields=["is_reconciled", "reconciled_je", "reconciled_at"])
    return {"ok": True, "message": f"Bank transaction {txn_id} reconciled to JE {je.pk}."}


# ---------------------------------------------------------------------------
# 6. Accounting period management
# ---------------------------------------------------------------------------

@router.post("/accounting-periods/{period_id}/close", response=ActionResponse)
def close_accounting_period(request, period_id: uuid.UUID):
    from apps.accounting.models import AccountingPeriod

    period = get_object_or_404(AccountingPeriod, id=period_id, is_deleted=False)
    if period.is_closed:
        return {"ok": False, "message": "Period is already closed."}
    period.is_closed = True
    period.save(update_fields=["is_closed"])
    return {"ok": True, "message": f"Period '{period.period_name}' closed."}


@router.post("/accounting-periods/{period_id}/reopen", response=ActionResponse)
def reopen_accounting_period(request, period_id: uuid.UUID):
    from apps.accounting.models import AccountingPeriod

    period = get_object_or_404(AccountingPeriod, id=period_id, is_deleted=False)
    if not period.is_closed:
        return {"ok": False, "message": "Period is not closed."}
    period.is_closed = False
    period.save(update_fields=["is_closed"])
    return {"ok": True, "message": f"Period '{period.period_name}' reopened."}


# ---------------------------------------------------------------------------
# 7. Financial reports
# ---------------------------------------------------------------------------

@router.get("/reports/trial-balance", response=List[TrialBalanceLine])
def trial_balance(request, as_of_date: Optional[str] = None):
    """
    For each leaf ChartOfAccount, sum debit/credit from submitted JournalEntryLines
    up to as_of_date. Returns balance = total_debit - total_credit (normal debit-balance
    convention; credit accounts show negative).
    """
    from apps.accounting.models import ChartOfAccount, JournalEntryLine, JournalEntry
    from django.db.models import Sum, Q

    je_qs = JournalEntry.objects.filter(status="submitted", is_deleted=False)
    if as_of_date:
        je_qs = je_qs.filter(posting_date__lte=as_of_date)

    submitted_je_ids = je_qs.values_list("id", flat=True)

    accounts = ChartOfAccount.objects.filter(is_deleted=False, is_group=False)
    result = []
    for acct in accounts:
        lines = JournalEntryLine.objects.filter(
            entry_id__in=submitted_je_ids,
            account=acct,
            is_deleted=False,
        )
        agg = lines.aggregate(total_debit=Sum("debit_amount"), total_credit=Sum("credit_amount"))
        total_debit = agg["total_debit"] or Decimal("0")
        total_credit = agg["total_credit"] or Decimal("0")
        balance = total_debit - total_credit
        result.append(TrialBalanceLine(
            account_number=acct.account_number or "",
            account_name=acct.account_name,
            account_type=acct.account_type,
            total_debit=total_debit,
            total_credit=total_credit,
            balance=balance,
        ))
    return result


@router.get("/reports/aged-receivables", response=List[AgedBucket])
def aged_receivables(request, as_of_date: Optional[str] = None):
    """
    For each Customer with open SalesInvoices, group outstanding_amount by age buckets.
    """
    from apps.accounting.models import SalesInvoice, Customer
    from django.db.models import Q

    ref_date = date.fromisoformat(as_of_date) if as_of_date else date.today()

    open_invoices = SalesInvoice.objects.filter(
        is_deleted=False,
        status__in=("submitted", "partially_paid", "overdue"),
        outstanding_amount__gt=0,
    ).select_related("customer")

    # Group by customer
    buckets: dict = {}
    for inv in open_invoices:
        cid = str(inv.customer_id)
        if cid not in buckets:
            buckets[cid] = {
                "party_id": cid,
                "party_name": inv.customer.customer_name,
                "current": Decimal("0"),
                "days_1_30": Decimal("0"),
                "days_31_60": Decimal("0"),
                "days_61_90": Decimal("0"),
                "days_over_90": Decimal("0"),
            }
        due = inv.due_date or inv.posting_date
        days_overdue = (ref_date - due).days if due else 0
        outstanding = inv.outstanding_amount
        b = buckets[cid]
        if days_overdue <= 0:
            b["current"] += outstanding
        elif days_overdue <= 30:
            b["days_1_30"] += outstanding
        elif days_overdue <= 60:
            b["days_31_60"] += outstanding
        elif days_overdue <= 90:
            b["days_61_90"] += outstanding
        else:
            b["days_over_90"] += outstanding

    result = []
    for b in buckets.values():
        total = b["current"] + b["days_1_30"] + b["days_31_60"] + b["days_61_90"] + b["days_over_90"]
        result.append(AgedBucket(
            party_id=b["party_id"],
            party_name=b["party_name"],
            current=b["current"],
            days_1_30=b["days_1_30"],
            days_31_60=b["days_31_60"],
            days_61_90=b["days_61_90"],
            days_over_90=b["days_over_90"],
            total_outstanding=total,
        ))
    return result


@router.get("/reports/aged-payables", response=List[AgedBucket])
def aged_payables(request, as_of_date: Optional[str] = None):
    """
    For each Vendor with open PurchaseBills, group outstanding_amount by age buckets.
    """
    from apps.accounting.models import PurchaseBill, Vendor

    ref_date = date.fromisoformat(as_of_date) if as_of_date else date.today()

    open_bills = PurchaseBill.objects.filter(
        is_deleted=False,
        status__in=("submitted", "partially_paid", "overdue"),
        outstanding_amount__gt=0,
    ).select_related("vendor")

    buckets: dict = {}
    for bill in open_bills:
        vid = str(bill.vendor_id)
        if vid not in buckets:
            buckets[vid] = {
                "party_id": vid,
                "party_name": bill.vendor.vendor_name,
                "current": Decimal("0"),
                "days_1_30": Decimal("0"),
                "days_31_60": Decimal("0"),
                "days_61_90": Decimal("0"),
                "days_over_90": Decimal("0"),
            }
        due = bill.due_date or bill.posting_date
        days_overdue = (ref_date - due).days if due else 0
        outstanding = bill.outstanding_amount
        b = buckets[vid]
        if days_overdue <= 0:
            b["current"] += outstanding
        elif days_overdue <= 30:
            b["days_1_30"] += outstanding
        elif days_overdue <= 60:
            b["days_31_60"] += outstanding
        elif days_overdue <= 90:
            b["days_61_90"] += outstanding
        else:
            b["days_over_90"] += outstanding

    result = []
    for b in buckets.values():
        total = b["current"] + b["days_1_30"] + b["days_31_60"] + b["days_61_90"] + b["days_over_90"]
        result.append(AgedBucket(
            party_id=b["party_id"],
            party_name=b["party_name"],
            current=b["current"],
            days_1_30=b["days_1_30"],
            days_31_60=b["days_31_60"],
            days_61_90=b["days_61_90"],
            days_over_90=b["days_over_90"],
            total_outstanding=total,
        ))
    return result


@router.get("/reports/income-statement", response=IncomeStatementResponse)
def income_statement(request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    """
    Sum income and expense JE lines in date range.
    Returns per-account lines grouped into income / expense sections.
    """
    from apps.accounting.models import ChartOfAccount, JournalEntryLine, JournalEntry
    from django.db.models import Sum

    je_qs = JournalEntry.objects.filter(status="submitted", is_deleted=False)
    if from_date:
        je_qs = je_qs.filter(posting_date__gte=from_date)
    if to_date:
        je_qs = je_qs.filter(posting_date__lte=to_date)

    submitted_je_ids = je_qs.values_list("id", flat=True)

    income_accounts = ChartOfAccount.objects.filter(
        account_type="income", is_deleted=False, is_group=False
    )
    expense_accounts = ChartOfAccount.objects.filter(
        account_type="expense", is_deleted=False, is_group=False
    )

    lines: List[IncomeStatementLine] = []
    total_income = Decimal("0")
    total_expense = Decimal("0")

    for acct in income_accounts:
        agg = JournalEntryLine.objects.filter(
            entry_id__in=submitted_je_ids, account=acct, is_deleted=False,
        ).aggregate(total_debit=Sum("debit_amount"), total_credit=Sum("credit_amount"))
        # Income: credit - debit (credit normal)
        amount = (agg["total_credit"] or Decimal("0")) - (agg["total_debit"] or Decimal("0"))
        total_income += amount
        lines.append(IncomeStatementLine(section="income", account_name=acct.account_name, amount=amount))

    for acct in expense_accounts:
        agg = JournalEntryLine.objects.filter(
            entry_id__in=submitted_je_ids, account=acct, is_deleted=False,
        ).aggregate(total_debit=Sum("debit_amount"), total_credit=Sum("credit_amount"))
        # Expense: debit - credit (debit normal)
        amount = (agg["total_debit"] or Decimal("0")) - (agg["total_credit"] or Decimal("0"))
        total_expense += amount
        lines.append(IncomeStatementLine(section="expense", account_name=acct.account_name, amount=amount))

    return IncomeStatementResponse(
        from_date=from_date or "",
        to_date=to_date or "",
        total_income=total_income,
        total_expense=total_expense,
        net_income=total_income - total_expense,
        lines=lines,
    )
