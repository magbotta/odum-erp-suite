"""Hook: post StockLedger entries when a StockEntry is submitted (§6.9)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def post_stock_ledger(stock_entry) -> None:
    """
    For each detail line in the submitted StockEntry, append immutable
    StockLedger rows that update the running qty_after_transaction.
    Also updates Batch.remaining_qty for batch-tracked items.
    """
    from django.utils import timezone

    now = timezone.now()

    for detail in stock_entry.details.select_related("item", "batch").all():
        item = detail.item

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
                batch=detail.batch,
            )
            if detail.batch:
                detail.batch.remaining_qty = max(
                    Decimal("0"), detail.batch.remaining_qty - detail.qty
                )
                detail.batch.save(update_fields=["remaining_qty"])

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
                batch=detail.batch,
            )


def _write_ledger_row(item, warehouse, actual_qty, rate, voucher_type, voucher_no,
                      posting_date, posting_time, batch=None):
    from apps.warehouse.models import StockLedger

    last = (
        StockLedger.objects.filter(item=item, warehouse=warehouse, is_cancelled=False)
        .order_by("-posting_date", "-posting_time", "-created_at")
        .first()
    )
    qty_before = last.qty_after_transaction if last else Decimal("0")
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
        incoming_rate=rate if actual_qty > 0 else Decimal("0"),
        valuation_rate=rate,
        stock_value=stock_value,
        stock_value_difference=actual_qty * rate,
        batch=batch,
    )
