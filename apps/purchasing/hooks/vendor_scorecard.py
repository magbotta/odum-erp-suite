"""Vendor scorecard auto-computation hook (§6.7)."""
from __future__ import annotations

from decimal import Decimal


def recalculate_scorecard(vendor_id: str, company_id, period_start, period_end) -> None:
    """
    Rebuild a vendor's scorecard for the given period from submitted GRNs.
    Creates or updates a VendorScorecard record.
    """
    from apps.purchasing.models import (
        GoodsReceipt,
        GoodsReceiptItem,
        PurchaseOrder,
        VendorScorecard,
    )

    # POs submitted in period
    pos = PurchaseOrder.objects.filter(
        vendor_id=vendor_id,
        company_id=company_id,
        posting_date__gte=period_start,
        posting_date__lte=period_end,
        status__in=[
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.BILLED,
        ],
    )
    total_pos = pos.count()

    on_time = 0
    for po in pos:
        if po.expected_delivery_date:
            # Count as on-time if any GRN was submitted on or before the expected date
            first_grn = (
                GoodsReceipt.objects.filter(
                    purchase_order=po, status=GoodsReceipt.Status.SUBMITTED
                )
                .order_by("posting_date")
                .first()
            )
            if first_grn and first_grn.posting_date <= po.expected_delivery_date:
                on_time += 1
        else:
            on_time += 1   # No date set → no late penalty

    on_time_pct = Decimal(on_time * 100) / max(total_pos, 1)

    # Quality: sum accepted vs. rejected qty from GRN items
    grn_items = GoodsReceiptItem.objects.filter(
        receipt__vendor_id=vendor_id,
        receipt__company_id=company_id,
        receipt__posting_date__gte=period_start,
        receipt__posting_date__lte=period_end,
        receipt__status=GoodsReceipt.Status.SUBMITTED,
    )
    total_received = sum(i.accepted_qty + i.rejected_qty for i in grn_items) or Decimal("1")
    total_rejected = sum(i.rejected_qty for i in grn_items)
    rejection_pct = (total_rejected / total_received * 100).quantize(Decimal("0.01"))

    # Composite score: 50% on-time, 50% quality (100 - rejection_pct)
    quality_score = max(Decimal("0"), 100 - rejection_pct)
    composite = ((on_time_pct * 50) + (quality_score * 50)) / 100

    VendorScorecard.objects.update_or_create(
        vendor_id=vendor_id,
        period_start=period_start,
        period_end=period_end,
        company_id=company_id,
        defaults={
            "vendor_name": _get_vendor_name(vendor_id),
            "total_pos": total_pos,
            "on_time_pos": on_time,
            "on_time_delivery_pct": on_time_pct.quantize(Decimal("0.01")),
            "total_received_qty": total_received,
            "rejected_qty": total_rejected,
            "quality_rejection_pct": rejection_pct,
            "composite_score": composite.quantize(Decimal("0.01")),
        },
    )


def _get_vendor_name(vendor_id: str) -> str:
    try:
        from apps.accounting.models import Vendor
        v = Vendor.objects.get(pk=vendor_id)
        return v.vendor_name
    except Exception:
        return str(vendor_id)
