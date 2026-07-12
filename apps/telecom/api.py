"""Telecom action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.telecom.models import ServiceSubscription, Subscriber, TelecomInvoice
from core.platform_api.security import AuthBearer

router = Router(tags=["Telecom Actions"], auth=AuthBearer())


@router.post("/subscribers/{subscriber_id}/suspend")
def suspend_subscriber(request, subscriber_id: UUID):
    subscriber = get_object_or_404(Subscriber, pk=subscriber_id)
    if subscriber.status != "active":
        return {"error": "Only Active subscribers can be suspended."}
    subscriber.status = "suspended"
    subscriber.save()
    return {"status": subscriber.status}


@router.post("/subscribers/{subscriber_id}/reactivate")
def reactivate_subscriber(request, subscriber_id: UUID):
    subscriber = get_object_or_404(Subscriber, pk=subscriber_id)
    if subscriber.status != "suspended":
        return {"error": "Only Suspended subscribers can be reactivated."}
    subscriber.status = "active"
    subscriber.save()
    return {"status": subscriber.status}


@router.post("/invoices/{invoice_id}/issue")
def issue_invoice(request, invoice_id: UUID):
    invoice = get_object_or_404(TelecomInvoice, pk=invoice_id)
    if invoice.status != "draft":
        return {"error": "Only Draft invoices can be issued."}
    from apps.telecom.hooks.invoice import compute_invoice_totals, post_to_accounting
    compute_invoice_totals(invoice)
    invoice.status = "issued"
    invoice.save()
    post_to_accounting(invoice)
    return {"status": invoice.status, "grand_total": str(invoice.grand_total)}


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid(request, invoice_id: UUID):
    invoice = get_object_or_404(TelecomInvoice, pk=invoice_id)
    if invoice.status not in ("issued", "overdue"):
        return {"error": "Invoice must be Issued or Overdue to mark as paid."}
    invoice.status = "paid"
    invoice.save()
    return {"status": invoice.status}
