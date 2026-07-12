"""Accounting action endpoints: submit/cancel invoices, etc. (§6.1)."""
from __future__ import annotations

import uuid
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

router = Router(tags=["Accounting Actions"])


class ActionResponse(Schema):
    ok: bool
    message: str


@router.post("/sales-invoices/{invoice_id}/submit", response=ActionResponse)
def submit_sales_invoice(request, invoice_id: uuid.UUID):
    from apps.accounting.models import SalesInvoice
    from apps.accounting.hooks.sales_invoice import post_invoice_to_gl

    invoice = get_object_or_404(SalesInvoice, id=invoice_id, is_deleted=False)
    if invoice.status != "Draft":
        return {"ok": False, "message": f"Invoice is already {invoice.status}."}

    post_invoice_to_gl(invoice)
    invoice.status = "Submitted"
    invoice.save(update_fields=["status"])
    return {"ok": True, "message": f"Invoice {invoice.invoice_number} submitted."}


@router.post("/sales-invoices/{invoice_id}/cancel", response=ActionResponse)
def cancel_sales_invoice(request, invoice_id: uuid.UUID):
    from apps.accounting.models import SalesInvoice, JournalEntry, JournalEntryLine
    from decimal import Decimal

    invoice = get_object_or_404(SalesInvoice, id=invoice_id, is_deleted=False)
    if invoice.status not in ("Submitted", "Overdue"):
        return {"ok": False, "message": f"Cannot cancel invoice in {invoice.status} status."}

    # Create a reversing journal entry if one exists
    if invoice.journal_entry_id:
        original = JournalEntry.objects.filter(id=invoice.journal_entry_id).first()
        if original:
            reverse_je = JournalEntry.objects.create(
                entry_type="journal",
                posting_date=original.posting_date,
                reference=f"REV/{invoice.invoice_number}",
                narration=f"Reversal of {invoice.invoice_number}",
                status="Submitted",
                currency=invoice.currency,
                company_id=invoice.company_id,
            )
            for line in original.lines.all():
                JournalEntryLine.objects.create(
                    journal_entry=reverse_je,
                    account_id=line.account_id,
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    currency=line.currency,
                    company_id=line.company_id,
                )

    invoice.status = "Cancelled"
    invoice.save(update_fields=["status"])
    return {"ok": True, "message": f"Invoice {invoice.invoice_number} cancelled and GL reversed."}
