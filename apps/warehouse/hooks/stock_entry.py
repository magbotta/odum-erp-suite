"""Hook: post StockLedger entries when a StockEntry is submitted (§6.9)."""
from __future__ import annotations

from datetime import datetime


def post_stock_ledger(stock_entry) -> None:
    """
    For each detail line in the submitted StockEntry, append immutable
    StockLedger rows that update the running qty_after_transaction.
    """
    from django.utils import timezone
    from apps.warehouse.models import StockLedger

    now = timezone.now()

    for detail in stock_entry.details.select_related("item").all():
        item = detail.item
        warehouse = stock_entry.to_warehouse or stock_entry.from_warehouse

        # Outbound from from_warehouse
        if stock_entry.from_warehouse and stock_entry.entry_type != "receipt":
            _write_ledger_row(
                item=item,
                warehouse=stock_entry.from_warehouse,
                actual_qty=-detail.qty,
                rate=detail.basic_rate,
                voucher_type="StockEntry",
                voucher_no=str(stock_entry.pk),
                posting_date=stock_entry.posting_date,
                posting_time=now.time(),
            )

        # Inbound to to_warehouse
        if stock_entry.to_warehouse:
            _write_ledger_row(
                item=item,
                warehouse=stock_entry.to_warehouse,
                actual_qty=detail.qty,
                rate=detail.basic_rate,
                voucher_type="StockEntry",
                voucher_no=str(stock_entry.pk),
                posting_date=stock_entry.posting_date,
                posting_time=now.time(),
            )


def _write_ledger_row(item, warehouse, actual_qty, rate, voucher_type, voucher_no,
                      posting_date, posting_time):
    from apps.warehouse.models import StockLedger

    # Running balance — get last ledger entry for this item/warehouse
    last = (
        StockLedger.objects.filter(item=item, warehouse=warehouse)
        .order_by("-posting_date", "-posting_time")
        .first()
    )
    qty_before = last.qty_after_transaction if last else 0
    qty_after = qty_before + actual_qty
    stock_value = qty_after * rate

    StockLedger.objects.create(
        item=item,
        warehouse=warehouse,
        posting_date=posting_date,
        posting_time=posting_time,
        voucher_type=voucher_type,
        voucher_no=voucher_no,
        actual_qty=actual_qty,
        qty_after_transaction=qty_after,
        incoming_rate=rate if actual_qty > 0 else 0,
        valuation_rate=rate,
        stock_value=stock_value,
        stock_value_difference=actual_qty * rate,
    )
