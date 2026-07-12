"""Sales action endpoints: confirm order, quotation → order (§6.8)."""
from __future__ import annotations

import uuid
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from typing import Optional


router = Router(tags=["Sales Actions"])


class ActionResponse(Schema):
    ok: bool
    message: str
    order_id: Optional[uuid.UUID] = None


@router.post("/orders/{order_id}/submit", response=ActionResponse)
def submit_sales_order(request, order_id: uuid.UUID):
    from apps.sales.models import SalesOrder

    order = get_object_or_404(SalesOrder, id=order_id, is_deleted=False)
    if order.status != SalesOrder.Status.DRAFT:
        return {"ok": False, "message": f"Order is already {order.status}."}

    order.status = SalesOrder.Status.CONFIRMED
    order.save(update_fields=["status"])
    return {"ok": True, "message": f"Order {order.order_number} confirmed.", "order_id": order.id}


@router.post("/quotations/{quotation_id}/convert", response=ActionResponse)
def convert_quotation_to_order(request, quotation_id: uuid.UUID):
    from apps.sales.models import Quotation, SalesOrder, SalesOrderItem
    from core.numbering.service import get_next_number

    quotation = get_object_or_404(Quotation, id=quotation_id, is_deleted=False)
    if quotation.status == Quotation.Status.CONVERTED:
        return {"ok": False, "message": "Quotation already converted.", "order_id": None}
    if quotation.status not in (Quotation.Status.DRAFT, Quotation.Status.SENT, Quotation.Status.ACCEPTED):
        return {"ok": False, "message": f"Cannot convert quotation in {quotation.status} status.", "order_id": None}

    order = SalesOrder.objects.create(
        customer=quotation.customer,
        order_number=get_next_number("SO", company_id=quotation.company_id),
        posting_date=quotation.posting_date,
        currency=quotation.currency,
        exchange_rate=quotation.exchange_rate,
        net_total=quotation.net_total,
        tax_total=quotation.tax_total,
        grand_total=quotation.grand_total,
        status=SalesOrder.Status.DRAFT,
        quotation_id=quotation.id,
        company_id=quotation.company_id,
    )

    for q_item in quotation.items.filter(is_deleted=False):
        SalesOrderItem.objects.create(
            order=order,
            item=q_item.item,
            qty=q_item.qty,
            rate=q_item.rate,
            amount=q_item.amount,
            company_id=quotation.company_id,
        )

    quotation.status = Quotation.Status.CONVERTED
    quotation.save(update_fields=["status"])

    return {"ok": True, "message": f"Quotation converted to order {order.order_number}.", "order_id": order.id}
