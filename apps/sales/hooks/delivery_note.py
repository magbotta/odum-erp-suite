"""Hook: submit a DeliveryNote — creates an outbound StockEntry and posts to StockLedger."""
from __future__ import annotations

from decimal import Decimal


def submit_delivery(dn) -> None:
    """
    On DeliveryNote submit:
    1. Create a StockEntry (type=issue) with one detail per DN line.
    2. Call post_stock_ledger to subtract from warehouse stock.
    3. Update SO item delivered_qty and flip SO status.
    """
    from django.utils import timezone

    from apps.warehouse.hooks.stock_entry import post_stock_ledger
    from apps.warehouse.models import Item, StockEntry, StockEntryDetail

    now = timezone.now()

    se = StockEntry.objects.create(
        entry_type=StockEntry.EntryType.ISSUE,
        posting_date=dn.posting_date,
        from_warehouse=None,
        status=StockEntry.Status.SUBMITTED,
        voucher_type="DeliveryNote",
        voucher_no=dn.dn_number or str(dn.pk),
        remarks=f"DN: {dn.dn_number or dn.pk}",
        company_id=dn.company_id,
    )

    total_value = Decimal("0")
    for line in dn.items.select_related("item", "warehouse").all():
        StockEntryDetail.objects.create(
            stock_entry=se,
            item=line.item,
            qty=line.qty,
            basic_rate=line.rate,
            amount=line.amount,
            serial_no=line.serial_nos,
            company_id=dn.company_id,
        )
        if se.from_warehouse is None:
            se.from_warehouse = line.warehouse
        total_value += line.amount

    se.total_value = total_value
    se.save(update_fields=["from_warehouse", "total_value"])

    post_stock_ledger(se)

    # Soft-link StockEntry back to DN
    from apps.sales.models import DeliveryNote
    DeliveryNote.objects.filter(pk=dn.pk).update(stock_entry_id=se.pk)

    # Update SO delivered_qty
    if dn.sales_order_id:
        _update_so_delivery_status(dn)


def cancel_delivery(dn) -> None:
    """Reverse the StockLedger rows for this DN."""
    if not dn.stock_entry_id:
        return

    from apps.warehouse.hooks.stock_entry import _write_ledger_row
    from apps.warehouse.models import StockEntry
    from django.utils import timezone

    now = timezone.now()

    try:
        se = StockEntry.objects.get(pk=dn.stock_entry_id)
    except StockEntry.DoesNotExist:
        return

    for detail in se.details.select_related("item", "batch").all():
        if se.from_warehouse:
            # Reversal: put stock back into from_warehouse
            _write_ledger_row(
                item=detail.item,
                warehouse=se.from_warehouse,
                actual_qty=detail.qty,
                rate=detail.basic_rate,
                voucher_type="DeliveryNote-Cancel",
                voucher_no=dn.dn_number or str(dn.pk),
                posting_date=dn.posting_date,
                posting_time=now.time(),
                batch=detail.batch,
            )

    se.status = StockEntry.Status.CANCELLED
    se.save(update_fields=["status"])

    if dn.sales_order_id:
        _reverse_so_delivery(dn)


def _update_so_delivery_status(dn) -> None:
    from apps.sales.models import DeliveryNoteItem, SalesOrder, SalesOrderItem

    dn_items = DeliveryNoteItem.objects.filter(delivery_note=dn)
    for di in dn_items:
        if di.so_item_id:
            try:
                soi = SalesOrderItem.objects.get(pk=di.so_item_id)
                soi.delivered_qty = soi.delivered_qty + di.qty
                soi.save(update_fields=["delivered_qty"])
            except SalesOrderItem.DoesNotExist:
                pass

    try:
        so = SalesOrder.objects.get(pk=dn.sales_order_id)
    except SalesOrder.DoesNotExist:
        return

    items = list(so.items.all())
    if not items:
        return

    total_ordered = sum(i.qty for i in items)
    total_delivered = sum(i.delivered_qty for i in items)

    if total_delivered >= total_ordered:
        so.status = SalesOrder.Status.DELIVERED
    elif total_delivered > 0:
        so.status = SalesOrder.Status.PARTIALLY_DELIVERED

    so.save(update_fields=["status"])


def _reverse_so_delivery(dn) -> None:
    from decimal import Decimal as D
    from apps.sales.models import DeliveryNoteItem, SalesOrder, SalesOrderItem

    dn_items = DeliveryNoteItem.objects.filter(delivery_note=dn)
    for di in dn_items:
        if di.so_item_id:
            try:
                soi = SalesOrderItem.objects.get(pk=di.so_item_id)
                soi.delivered_qty = max(D("0"), soi.delivered_qty - di.qty)
                soi.save(update_fields=["delivered_qty"])
            except SalesOrderItem.DoesNotExist:
                pass

    try:
        so = SalesOrder.objects.get(pk=dn.sales_order_id)
    except SalesOrder.DoesNotExist:
        return

    items = list(so.items.all())
    total_ordered = sum(i.qty for i in items)
    total_delivered = sum(i.delivered_qty for i in items)

    if total_delivered <= 0:
        so.status = SalesOrder.Status.SUBMITTED
    elif total_delivered < total_ordered:
        so.status = SalesOrder.Status.PARTIALLY_DELIVERED

    so.save(update_fields=["status"])
