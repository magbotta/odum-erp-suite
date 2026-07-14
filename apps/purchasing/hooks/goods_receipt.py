"""Hook: submit a GoodsReceipt — creates a StockEntry and posts to the StockLedger."""
from __future__ import annotations

from decimal import Decimal


def submit_grn(grn) -> None:
    """
    On GRN submit:
    1. Create a StockEntry (type=receipt) with one StockEntryDetail per GRN line.
    2. Call post_stock_ledger to append immutable ledger rows.
    3. Update each PO line's received_qty and set PO status to partially_received
       or received as appropriate.
    """
    from django.utils import timezone

    from apps.warehouse.hooks.stock_entry import post_stock_ledger
    from apps.warehouse.models import Item, StockEntry, StockEntryDetail, Warehouse
    from .purchase_order import _update_po_receipt_status

    now = timezone.now()

    # ── Create the warehouse StockEntry ──────────────────────────────────────
    se = StockEntry.objects.create(
        entry_type=StockEntry.EntryType.RECEIPT,
        posting_date=grn.posting_date,
        to_warehouse=None,     # set per-item below if all same; else handled on details
        status=StockEntry.Status.SUBMITTED,
        voucher_type="GoodsReceipt",
        voucher_no=grn.grn_number or str(grn.pk),
        remarks=f"GRN: {grn.grn_number or grn.pk}",
        company_id=grn.company_id,
    )

    total_value = Decimal("0")
    for line in grn.items.all():
        try:
            item_obj = Item.objects.get(pk=line.item_id)
        except Item.DoesNotExist:
            raise ValueError(f"Item {line.item_id} not found in Warehouse")

        try:
            wh_obj = Warehouse.objects.get(pk=line.warehouse_id)
        except Warehouse.DoesNotExist:
            raise ValueError(f"Warehouse {line.warehouse_id} not found")

        qty = line.accepted_qty if line.accepted_qty else line.qty
        rate = line.rate
        amount = qty * rate

        StockEntryDetail.objects.create(
            stock_entry=se,
            item=item_obj,
            qty=qty,
            basic_rate=rate,
            amount=amount,
            serial_no=line.serial_nos,
            company_id=grn.company_id,
        )
        # Attach destination warehouse directly on StockEntry for single-warehouse receipts;
        # post_stock_ledger reads se.to_warehouse for inbound movement.
        if se.to_warehouse is None:
            se.to_warehouse = wh_obj
        elif se.to_warehouse_id != wh_obj.pk:
            # Multi-warehouse GRN: write a separate StockEntry per warehouse below.
            # For now we store the first warehouse — a future enhancement can split.
            pass

        total_value += amount

    se.total_value = total_value
    se.save(update_fields=["to_warehouse", "total_value"])

    # ── Post stock ledger (immutable append-only rows) ────────────────────────
    post_stock_ledger(se)

    # ── Link StockEntry back to GRN ───────────────────────────────────────────
    from apps.purchasing.models import GoodsReceipt
    GoodsReceipt.objects.filter(pk=grn.pk).update(stock_entry_id=se.pk)

    # ── Update PO received quantities ─────────────────────────────────────────
    if grn.purchase_order_id:
        _update_po_receipt_status(grn)


def cancel_grn(grn) -> None:
    """
    Reverse the StockLedger rows posted for this GRN.
    Writes reversal rows (negative actual_qty) then marks the StockEntry cancelled.
    """
    if not grn.stock_entry_id:
        return

    from apps.warehouse.hooks.stock_entry import _write_ledger_row
    from apps.warehouse.models import StockEntry, StockEntryDetail
    from django.utils import timezone

    now = timezone.now()

    try:
        se = StockEntry.objects.get(pk=grn.stock_entry_id)
    except StockEntry.DoesNotExist:
        return

    for detail in se.details.select_related("item", "batch").all():
        # Reversal: deduct from to_warehouse (inbound reversal)
        if se.to_warehouse:
            _write_ledger_row(
                item=detail.item,
                warehouse=se.to_warehouse,
                actual_qty=-detail.qty,
                rate=detail.basic_rate,
                voucher_type="GoodsReceipt-Cancel",
                voucher_no=grn.grn_number or str(grn.pk),
                posting_date=grn.posting_date,
                posting_time=now.time(),
                batch=detail.batch,
            )

    se.status = StockEntry.Status.CANCELLED
    se.save(update_fields=["status"])

    # Reverse PO received_qty
    if grn.purchase_order_id:
        _reverse_po_receipt(grn)


def _reverse_po_receipt(grn) -> None:
    from apps.purchasing.models import PurchaseOrder, PurchaseOrderItem, GoodsReceiptItem

    grn_items = GoodsReceiptItem.objects.filter(receipt=grn)
    for gi in grn_items:
        if gi.po_item_id:
            try:
                poi = PurchaseOrderItem.objects.get(pk=gi.po_item_id)
            except PurchaseOrderItem.DoesNotExist:
                continue
            qty = gi.accepted_qty if gi.accepted_qty else gi.qty
            poi.received_qty = max(Decimal("0"), poi.received_qty - qty)
            poi.save(update_fields=["received_qty"])

    try:
        po = PurchaseOrder.objects.get(pk=grn.purchase_order_id)
        items = list(po.items.all())
        total_ordered = sum(i.qty for i in items)
        total_received = sum(i.received_qty for i in items)
        if total_received <= 0:
            po.status = PurchaseOrder.Status.SUBMITTED
        elif total_received < total_ordered:
            po.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
        po.save(update_fields=["status"])
    except PurchaseOrder.DoesNotExist:
        pass
