"""Warehouse action endpoints (§6.9): stock entry submit/cancel, stock balance queries,
cycle count submission, reorder alerts."""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.db.models import Sum, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError


router = Router(tags=["Warehouse Actions"])


class ActionResponse(Schema):
    ok: bool
    message: str
    id: Optional[uuid.UUID] = None


# ── Stock Entry actions ────────────────────────────────────────────────────────

@router.post("/stock-entries/{entry_id}/submit", response=ActionResponse,
             summary="Submit Stock Entry — posts to Stock Ledger")
def submit_stock_entry(request, entry_id: uuid.UUID):
    from apps.warehouse.models import StockEntry
    from apps.warehouse.hooks.stock_entry import post_stock_ledger

    entry = get_object_or_404(StockEntry, id=entry_id, is_deleted=False)
    if entry.status != StockEntry.Status.DRAFT:
        raise HttpError(400, f"Stock entry is already '{entry.status}'.")

    lines = entry.details.count()
    if lines == 0:
        raise HttpError(400, "Cannot submit a stock entry with no line items.")

    entry.status = StockEntry.Status.SUBMITTED
    entry.save(update_fields=["status", "updated_at"])

    post_stock_ledger(entry)
    return {"ok": True, "message": f"Stock entry submitted — {lines} ledger rows posted.", "id": entry.id}


@router.post("/stock-entries/{entry_id}/cancel", response=ActionResponse,
             summary="Cancel Stock Entry — reverses Stock Ledger entries")
def cancel_stock_entry(request, entry_id: uuid.UUID):
    from apps.warehouse.models import StockEntry, StockLedger
    from django.utils import timezone as tz

    entry = get_object_or_404(StockEntry, id=entry_id, is_deleted=False)
    if entry.status != StockEntry.Status.SUBMITTED:
        raise HttpError(400, "Only submitted stock entries can be cancelled.")

    now = tz.now()
    # Mark original ledger rows cancelled then write reversals
    original_rows = StockLedger.objects.filter(
        voucher_type="StockEntry", voucher_no=str(entry.pk), is_cancelled=False
    )
    for row in original_rows:
        row.is_cancelled = True
        row.save(update_fields=["is_cancelled"])

        last = (
            StockLedger.objects.filter(
                item=row.item, warehouse=row.warehouse, is_cancelled=False
            )
            .order_by("-posting_date", "-posting_time", "-created_at")
            .first()
        )
        qty_before = last.qty_after_transaction if last else Decimal("0")
        reversal_qty = -row.actual_qty
        qty_after = qty_before + reversal_qty

        StockLedger.objects.create(
            item=row.item,
            warehouse=row.warehouse,
            posting_date=date.today(),
            posting_time=now.time(),
            voucher_type="StockEntryCancellation",
            voucher_no=str(entry.pk),
            actual_qty=reversal_qty,
            qty_after_transaction=qty_after,
            incoming_rate=row.incoming_rate if reversal_qty > 0 else Decimal("0"),
            valuation_rate=row.valuation_rate,
            stock_value=qty_after * row.valuation_rate,
            stock_value_difference=reversal_qty * row.valuation_rate,
        )

    entry.status = StockEntry.Status.CANCELLED
    entry.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": f"Stock entry cancelled — {original_rows.count()} ledger rows reversed.", "id": entry.id}


# ── Cycle count actions ────────────────────────────────────────────────────────

@router.post("/cycle-count-sheets/{sheet_id}/submit", response=ActionResponse,
             summary="Submit Cycle Count — posts variance adjustments to Stock Ledger")
def submit_cycle_count(request, sheet_id: uuid.UUID):
    from apps.warehouse.models import CycleCountSheet
    from apps.warehouse.hooks.cycle_count import post_cycle_count_adjustments

    sheet = get_object_or_404(CycleCountSheet, id=sheet_id, is_deleted=False)
    if sheet.status not in ("completed", "in_progress"):
        raise HttpError(400, f"Sheet status '{sheet.status}' cannot be submitted.")

    counted = sheet.details.filter(is_counted=True).count()
    if counted == 0:
        raise HttpError(400, "No counted items found. Count items before submitting.")

    post_cycle_count_adjustments(sheet)
    return {
        "ok": True,
        "message": f"Cycle count submitted — {counted} items processed, variance value: {sheet.total_variance_value}.",
        "id": sheet.id,
    }


# ── Stock balance queries ──────────────────────────────────────────────────────

class StockBalanceRow(Schema):
    item_code: str
    item_name: str
    warehouse_code: str
    warehouse_name: str
    qty: float
    valuation_rate: float
    stock_value: float


class StockBalanceResponse(Schema):
    rows: List[StockBalanceRow]
    total_value: float
    as_of_date: str


@router.get("/stock-balance", response=StockBalanceResponse, summary="Current Stock Balance by Item & Warehouse")
def stock_balance(
    request,
    warehouse_code: Optional[str] = None,
    item_code: Optional[str] = None,
    as_of_date: Optional[str] = None,
):
    from apps.warehouse.models import StockLedger, Item, Warehouse

    cutoff = date.fromisoformat(as_of_date) if as_of_date else date.today()

    # Get latest ledger row per (item, warehouse) pair up to cutoff date
    from django.db.models import Max

    qs = StockLedger.objects.filter(
        is_cancelled=False, posting_date__lte=cutoff
    )
    if warehouse_code:
        qs = qs.filter(warehouse__warehouse_code=warehouse_code)
    if item_code:
        qs = qs.filter(item__item_code=item_code)

    # Subquery: latest row per (item, warehouse)
    from django.db.models import OuterRef, Subquery
    latest_ids = (
        StockLedger.objects.filter(
            item=OuterRef("item"),
            warehouse=OuterRef("warehouse"),
            is_cancelled=False,
            posting_date__lte=cutoff,
        )
        .order_by("-posting_date", "-posting_time", "-created_at")
        .values("id")[:1]
    )
    latest_rows = StockLedger.objects.filter(
        id__in=Subquery(latest_ids), is_cancelled=False
    ).select_related("item", "warehouse")

    if warehouse_code:
        latest_rows = latest_rows.filter(warehouse__warehouse_code=warehouse_code)
    if item_code:
        latest_rows = latest_rows.filter(item__item_code=item_code)

    rows = []
    total_value = Decimal("0")
    for row in latest_rows:
        if row.qty_after_transaction <= 0:
            continue
        val = row.qty_after_transaction * row.valuation_rate
        rows.append({
            "item_code": row.item.item_code,
            "item_name": row.item.item_name,
            "warehouse_code": row.warehouse.warehouse_code,
            "warehouse_name": row.warehouse.warehouse_name,
            "qty": float(row.qty_after_transaction),
            "valuation_rate": float(row.valuation_rate),
            "stock_value": float(val),
        })
        total_value += val

    rows.sort(key=lambda r: (r["item_code"], r["warehouse_code"]))
    return {"rows": rows, "total_value": float(total_value), "as_of_date": str(cutoff)}


class ItemStockSummary(Schema):
    item_code: str
    item_name: str
    warehouses: List[StockBalanceRow]
    total_qty: float
    total_value: float


@router.get("/items/{item_id}/stock-summary", response=ItemStockSummary,
            summary="Stock balance for a single item across all warehouses")
def item_stock_summary(request, item_id: uuid.UUID):
    from apps.warehouse.models import Item, StockLedger
    from django.db.models import OuterRef, Subquery

    item = get_object_or_404(Item, id=item_id, is_deleted=False)

    latest_ids = (
        StockLedger.objects.filter(
            item=item, warehouse=OuterRef("warehouse"), is_cancelled=False
        )
        .order_by("-posting_date", "-posting_time", "-created_at")
        .values("id")[:1]
    )
    latest_rows = StockLedger.objects.filter(
        item=item,
        id__in=Subquery(latest_ids),
        is_cancelled=False,
    ).select_related("warehouse")

    wh_rows = []
    total_qty = Decimal("0")
    total_val = Decimal("0")
    for row in latest_rows:
        if row.qty_after_transaction <= 0:
            continue
        val = row.qty_after_transaction * row.valuation_rate
        wh_rows.append({
            "item_code": item.item_code,
            "item_name": item.item_name,
            "warehouse_code": row.warehouse.warehouse_code,
            "warehouse_name": row.warehouse.warehouse_name,
            "qty": float(row.qty_after_transaction),
            "valuation_rate": float(row.valuation_rate),
            "stock_value": float(val),
        })
        total_qty += row.qty_after_transaction
        total_val += val

    return {
        "item_code": item.item_code,
        "item_name": item.item_name,
        "warehouses": wh_rows,
        "total_qty": float(total_qty),
        "total_value": float(total_val),
    }


# ── Reorder alerts ─────────────────────────────────────────────────────────────

class ReorderAlert(Schema):
    item_code: str
    item_name: str
    warehouse_code: str
    current_qty: float
    re_order_level: float
    re_order_qty: float
    safety_stock: float
    shortfall: float


class ReorderAlertsResponse(Schema):
    alerts: List[ReorderAlert]
    count: int


@router.get("/reorder-alerts", response=ReorderAlertsResponse,
            summary="Items at or below their reorder level")
def reorder_alerts(request):
    from apps.warehouse.models import ReorderRule, StockLedger
    from django.db.models import OuterRef, Subquery

    alerts = []
    for rule in ReorderRule.objects.filter(is_deleted=False).select_related("item", "warehouse"):
        latest = (
            StockLedger.objects.filter(
                item=rule.item, warehouse=rule.warehouse, is_cancelled=False
            )
            .order_by("-posting_date", "-posting_time", "-created_at")
            .first()
        )
        current_qty = latest.qty_after_transaction if latest else Decimal("0")
        if current_qty <= rule.re_order_level:
            alerts.append({
                "item_code": rule.item.item_code,
                "item_name": rule.item.item_name,
                "warehouse_code": rule.warehouse.warehouse_code,
                "current_qty": float(current_qty),
                "re_order_level": float(rule.re_order_level),
                "re_order_qty": float(rule.re_order_qty),
                "safety_stock": float(rule.safety_stock),
                "shortfall": float(rule.re_order_level - current_qty),
            })

    alerts.sort(key=lambda a: a["shortfall"], reverse=True)
    return {"alerts": alerts, "count": len(alerts)}


# ── Batch expiry alerts ────────────────────────────────────────────────────────

class BatchExpiryAlert(Schema):
    batch_id: str
    item_code: str
    item_name: str
    expiry_date: str
    remaining_qty: float
    days_until_expiry: int


class BatchExpiryResponse(Schema):
    alerts: List[BatchExpiryAlert]
    count: int


@router.get("/batch-expiry-alerts", response=BatchExpiryResponse,
            summary="Batches expiring within the next N days")
def batch_expiry_alerts(request, days_ahead: int = 90):
    from apps.warehouse.models import Batch
    from datetime import timedelta

    cutoff = date.today() + timedelta(days=days_ahead)
    batches = Batch.objects.filter(
        expiry_date__lte=cutoff,
        expiry_date__gte=date.today(),
        status="active",
        remaining_qty__gt=0,
        is_deleted=False,
    ).select_related("item").order_by("expiry_date")

    alerts = []
    for b in batches:
        days = (b.expiry_date - date.today()).days
        alerts.append({
            "batch_id": b.batch_id,
            "item_code": b.item.item_code,
            "item_name": b.item.item_name,
            "expiry_date": str(b.expiry_date),
            "remaining_qty": float(b.remaining_qty),
            "days_until_expiry": days,
        })

    return {"alerts": alerts, "count": len(alerts)}
