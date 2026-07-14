"""Hooks for PurchaseOrder lifecycle."""
from __future__ import annotations

from decimal import Decimal


def before_save_po(po) -> None:
    """Auto-generate PO number and compute totals."""
    if not po.po_number:
        from core.numbering.service import get_next_number
        po.po_number = get_next_number("PO", po.company_id)

    # Recompute totals from items (if items already saved — on create they're empty)
    _recompute_totals(po)


def _recompute_totals(po) -> None:
    if po.pk:
        items = list(po.items.all())
        net = sum(i.amount for i in items)
        po.net_total = net
        po.grand_total = net + po.tax_total


def _update_po_receipt_status(grn) -> None:
    """Update PO received_qty on each line and flip PO status."""
    from apps.purchasing.models import GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem

    grn_items = GoodsReceiptItem.objects.filter(receipt=grn)
    for gi in grn_items:
        if gi.po_item_id:
            try:
                poi = PurchaseOrderItem.objects.get(pk=gi.po_item_id)
            except PurchaseOrderItem.DoesNotExist:
                continue
            qty = gi.accepted_qty if gi.accepted_qty else gi.qty
            poi.received_qty = poi.received_qty + qty
            poi.save(update_fields=["received_qty"])

    try:
        po = PurchaseOrder.objects.get(pk=grn.purchase_order_id)
    except PurchaseOrder.DoesNotExist:
        return

    items = list(po.items.all())
    if not items:
        return

    total_ordered = sum(i.qty for i in items)
    total_received = sum(i.received_qty for i in items)

    if total_received >= total_ordered:
        po.status = PurchaseOrder.Status.RECEIVED
    elif total_received > 0:
        po.status = PurchaseOrder.Status.PARTIALLY_RECEIVED

    po.save(update_fields=["status"])
