"""Hook: post stock adjustment entries from a submitted CycleCountSheet (§6.9)."""
from __future__ import annotations

from decimal import Decimal
from django.utils import timezone


def post_cycle_count_adjustments(sheet) -> None:
    """
    For each CycleCountDetail with a variance, create a StockLedger adjustment row.
    Variance = counted_qty - system_qty. Positive = found more stock, negative = shrinkage.
    """
    from apps.warehouse.models import StockLedger, CycleCountDetail

    now = timezone.now()
    total_variance_value = Decimal("0")

    for detail in sheet.details.select_related("item").filter(is_counted=True):
        if detail.counted_qty is None:
            continue
        variance = detail.counted_qty - detail.system_qty
        if variance == 0:
            continue

        rate = detail.valuation_rate or Decimal("0")
        last = (
            StockLedger.objects.filter(
                item=detail.item, warehouse=sheet.warehouse, is_cancelled=False
            )
            .order_by("-posting_date", "-posting_time", "-created_at")
            .first()
        )
        qty_before = last.qty_after_transaction if last else Decimal("0")
        qty_after = qty_before + variance
        variance_value = variance * rate

        StockLedger.objects.create(
            item=detail.item,
            warehouse=sheet.warehouse,
            posting_date=sheet.count_date,
            posting_time=now.time(),
            voucher_type="CycleCountSheet",
            voucher_no=str(sheet.pk),
            actual_qty=variance,
            qty_after_transaction=qty_after,
            incoming_rate=rate if variance > 0 else Decimal("0"),
            valuation_rate=rate,
            stock_value=qty_after * rate,
            stock_value_difference=variance_value,
        )

        detail.variance_qty = variance
        detail.variance_value = variance_value
        detail.save(update_fields=["variance_qty", "variance_value"])
        total_variance_value += abs(variance_value)

    sheet.total_variance_value = total_variance_value
    sheet.status = "submitted"
    sheet.save(update_fields=["total_variance_value", "status"])
