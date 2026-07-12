"""Purchasing action endpoints: submit GoodsReceipt → StockLedger (§6.7)."""
from __future__ import annotations

import uuid
from django.shortcuts import get_object_or_404
from ninja import Router, Schema


router = Router(tags=["Purchasing Actions"])


class ActionResponse(Schema):
    ok: bool
    message: str


@router.post("/goods-receipts/{grn_id}/submit", response=ActionResponse)
def submit_goods_receipt(request, grn_id: uuid.UUID):
    from apps.purchasing.models import GoodsReceipt
    from apps.warehouse.hooks.stock_entry import post_stock_ledger
    from apps.warehouse.models import StockEntry, StockEntryItem

    grn = get_object_or_404(GoodsReceipt, id=grn_id, is_deleted=False)
    if grn.status != GoodsReceipt.Status.DRAFT:
        return {"ok": False, "message": f"GRN is already {grn.status}."}

    # Create a StockEntry of type "Receipt" to mirror the GRN
    from core.numbering.service import get_next_number
    entry = StockEntry.objects.create(
        entry_type="receipt",
        posting_date=grn.posting_date,
        reference_document="GoodsReceipt",
        reference_id=grn.id,
        status="Draft",
        company_id=grn.company_id,
    )
    for grn_item in grn.items.filter(is_deleted=False):
        StockEntryItem.objects.create(
            stock_entry=entry,
            item=grn_item.item,
            qty=grn_item.qty,
            rate=grn_item.rate,
            to_warehouse=grn_item.warehouse,
            company_id=grn.company_id,
        )

    post_stock_ledger(entry)
    entry.status = "Submitted"
    entry.save(update_fields=["status"])

    grn.status = GoodsReceipt.Status.SUBMITTED
    grn.save(update_fields=["status"])

    return {"ok": True, "message": f"GRN {grn.grn_number} submitted and stock updated."}
