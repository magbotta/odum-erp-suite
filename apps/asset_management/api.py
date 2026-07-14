"""Asset Management action endpoints (§6.2)."""
from __future__ import annotations

import uuid
import datetime
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

router = Router(tags=["Asset Management"])


class ActionResponse(Schema):
    ok: bool
    message: str


# ── Capitalise (activate) an asset ───────────────────────────────────────────

@router.post("/assets/{asset_id}/capitalise", response=ActionResponse)
def capitalise_asset(request, asset_id: uuid.UUID):
    """Activate a draft asset and generate its depreciation schedule."""
    from apps.asset_management.hooks.asset import generate_depreciation_schedule
    from apps.asset_management.models import Asset

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)
    if asset.status != Asset.Status.DRAFT:
        return {"ok": False, "message": "Asset is already {}.".format(asset.status)}

    if not asset.depreciation_method:
        asset.depreciation_method = asset.category.depreciation_method
    asset.status = Asset.Status.ACTIVE
    asset.save(update_fields=["status", "depreciation_method"])

    generate_depreciation_schedule(asset)
    schedule_count = asset.depreciation_schedule.count()
    return {"ok": True, "message": "Asset {} capitalised. {} depreciation rows generated.".format(
        asset.asset_code, schedule_count
    )}


# ── Post depreciation ─────────────────────────────────────────────────────────

@router.post("/assets/{asset_id}/depreciation/{schedule_id}/post", response=ActionResponse)
def post_single_depreciation(request, asset_id: uuid.UUID, schedule_id: uuid.UUID):
    """Post a single depreciation schedule row to the GL."""
    from apps.asset_management.hooks.asset import post_depreciation
    from apps.asset_management.models import Asset, AssetDepreciationSchedule

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)
    row = get_object_or_404(AssetDepreciationSchedule, id=schedule_id, asset=asset)

    if row.is_posted:
        return {"ok": False, "message": "This depreciation entry is already posted."}

    post_depreciation(row)
    return {"ok": True, "message": "Depreciation for {} on {} posted.".format(
        asset.asset_code, row.schedule_date
    )}


@router.post("/assets/{asset_id}/post-due-depreciation", response=ActionResponse)
def post_due_depreciation(request, asset_id: uuid.UUID, as_of_date: Optional[str] = None):
    """Post all unposted depreciation rows up to today (or a given date)."""
    from apps.asset_management.hooks.asset import post_due_depreciation as _post_due
    from apps.asset_management.models import Asset

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)

    date_obj = None
    if as_of_date:
        try:
            date_obj = datetime.date.fromisoformat(as_of_date)
        except ValueError:
            return {"ok": False, "message": "Invalid date format. Use YYYY-MM-DD."}

    count = _post_due(asset, as_of_date=date_obj)
    return {"ok": True, "message": "{} depreciation entries posted for {}.".format(count, asset.asset_code)}


# ── Depreciation schedule ─────────────────────────────────────────────────────

class ScheduleRow(Schema):
    id: str
    schedule_date: str
    depreciation_amount: float
    accumulated_depreciation: float
    book_value_after: float
    is_posted: bool
    journal_entry_id: Optional[str]


@router.get("/assets/{asset_id}/depreciation-schedule", response=List[ScheduleRow])
def depreciation_schedule(request, asset_id: uuid.UUID):
    """Return the full depreciation schedule for an asset."""
    from apps.asset_management.models import Asset, AssetDepreciationSchedule

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)
    rows = AssetDepreciationSchedule.objects.filter(asset=asset, is_deleted=False).order_by("schedule_date")
    return [
        ScheduleRow(
            id=str(r.pk),
            schedule_date=str(r.schedule_date),
            depreciation_amount=float(r.depreciation_amount),
            accumulated_depreciation=float(r.accumulated_depreciation),
            book_value_after=float(r.book_value_after),
            is_posted=r.is_posted,
            journal_entry_id=str(r.journal_entry_id) if r.journal_entry_id else None,
        )
        for r in rows
    ]


# ── Revaluation / impairment ──────────────────────────────────────────────────

class RevalueIn(Schema):
    new_value: float
    revaluation_date: str
    reason: Optional[str] = None


@router.post("/assets/{asset_id}/revalue", response=ActionResponse)
def revalue_asset(request, asset_id: uuid.UUID, payload: RevalueIn):
    """Record an impairment or upward revaluation and regenerate the depreciation schedule."""
    from apps.asset_management.hooks.asset import revalue_asset as _revalue
    from apps.asset_management.models import Asset

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)
    if asset.status != Asset.Status.ACTIVE:
        return {"ok": False, "message": "Only active assets can be revalued."}

    try:
        _revalue(
            asset,
            new_value=Decimal(str(payload.new_value)),
            revaluation_date=payload.revaluation_date,
            reason=payload.reason or "",
        )
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    return {"ok": True, "message": "Asset {} revalued to {:.2f}.".format(
        asset.asset_code, payload.new_value
    )}


# ── Disposal ──────────────────────────────────────────────────────────────────

class DisposeIn(Schema):
    disposal_date: str
    disposal_amount: float = 0
    reason: Optional[str] = None


@router.post("/assets/{asset_id}/dispose", response=ActionResponse)
def dispose_asset(request, asset_id: uuid.UUID, payload: DisposeIn):
    """Record asset disposal (sale or scrap) and post the GL entry."""
    from apps.asset_management.hooks.asset import dispose_asset as _dispose
    from apps.asset_management.models import Asset

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)
    if asset.status not in (Asset.Status.ACTIVE, Asset.Status.UNDER_MAINTENANCE):
        return {"ok": False, "message": "Cannot dispose of an asset in {} status.".format(asset.status)}

    try:
        _dispose(
            asset,
            disposal_date=payload.disposal_date,
            disposal_amount=Decimal(str(payload.disposal_amount)),
            reason=payload.reason or "",
        )
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    return {"ok": True, "message": "Asset {} disposed on {}.".format(
        asset.asset_code, payload.disposal_date
    )}


# ── Transfer ──────────────────────────────────────────────────────────────────

class TransferIn(Schema):
    to_location: str
    movement_date: str
    to_custodian_id: Optional[str] = None
    to_custodian_name: Optional[str] = None
    purpose: Optional[str] = None


@router.post("/assets/{asset_id}/transfer", response=ActionResponse)
def transfer_asset(request, asset_id: uuid.UUID, payload: TransferIn):
    """Record a location or custodian transfer for an asset."""
    from apps.asset_management.hooks.asset import transfer_asset as _transfer
    from apps.asset_management.models import Asset

    asset = get_object_or_404(Asset, id=asset_id, is_deleted=False)

    cust_id = None
    if payload.to_custodian_id:
        try:
            cust_id = uuid.UUID(payload.to_custodian_id)
        except ValueError:
            pass

    try:
        _transfer(
            asset,
            to_location=payload.to_location,
            movement_date=payload.movement_date,
            to_custodian_id=cust_id,
            to_custodian_name=payload.to_custodian_name or "",
            purpose=payload.purpose or "",
        )
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    return {"ok": True, "message": "Asset {} transferred to {}.".format(
        asset.asset_code, payload.to_location
    )}


# ── Physical audit ────────────────────────────────────────────────────────────

@router.post("/audits/{audit_id}/complete", response=ActionResponse)
def complete_audit(request, audit_id: uuid.UUID):
    """Complete a physical asset audit and tally found/missing counts."""
    from apps.asset_management.hooks.asset import complete_audit as _complete
    from apps.asset_management.models import AssetAudit

    audit = get_object_or_404(AssetAudit, id=audit_id, is_deleted=False)
    if audit.status == AssetAudit.Status.COMPLETED:
        return {"ok": False, "message": "Audit is already completed."}

    _complete(audit)
    return {"ok": True, "message": "Audit {} completed: {} found, {} missing.".format(
        audit.audit_number, audit.total_assets_found, audit.total_assets_missing
    )}


# ── Analytics ─────────────────────────────────────────────────────────────────

class CategorySummary(Schema):
    category_name: str
    asset_count: int
    total_purchase_price: float
    total_current_value: float
    total_accumulated_depreciation: float


class AssetAnalytics(Schema):
    total_assets: int
    active_assets: int
    under_maintenance: int
    fully_depreciated: int
    disposed: int
    total_purchase_value: float
    total_current_value: float
    total_accumulated_depreciation: float
    by_category: List[CategorySummary]
    expiring_warranties_30d: int
    expiring_insurance_30d: int


@router.get("/analytics/summary", response=AssetAnalytics)
def analytics_summary(request, company_id: Optional[str] = None):
    """Portfolio overview: counts, values, expiry alerts by category."""
    from django.db.models import Count, Sum
    from apps.asset_management.models import Asset, AssetCategory, AssetInsurance, AssetWarranty

    qs = Asset.objects.filter(is_deleted=False)
    if company_id:
        qs = qs.filter(company_id=company_id)

    totals = qs.aggregate(
        tp=Sum("purchase_price"),
        tv=Sum("current_value"),
        ta=Sum("accumulated_depreciation"),
    )

    by_cat = []
    for cat in AssetCategory.objects.filter(is_deleted=False):
        cat_qs = qs.filter(category=cat)
        ct = cat_qs.aggregate(tp=Sum("purchase_price"), tv=Sum("current_value"), ta=Sum("accumulated_depreciation"))
        by_cat.append(CategorySummary(
            category_name=cat.name,
            asset_count=cat_qs.count(),
            total_purchase_price=float(ct["tp"] or 0),
            total_current_value=float(ct["tv"] or 0),
            total_accumulated_depreciation=float(ct["ta"] or 0),
        ))

    cutoff = datetime.date.today() + datetime.timedelta(days=30)
    exp_warranty = AssetWarranty.objects.filter(
        is_active=True, warranty_end__lte=cutoff, warranty_end__gte=datetime.date.today(), is_deleted=False
    ).count()
    exp_insurance = AssetInsurance.objects.filter(
        is_active=True, policy_end__lte=cutoff, policy_end__gte=datetime.date.today(), is_deleted=False
    ).count()

    return AssetAnalytics(
        total_assets=qs.count(),
        active_assets=qs.filter(status="active").count(),
        under_maintenance=qs.filter(status="under_maintenance").count(),
        fully_depreciated=qs.filter(fully_depreciated=True).count(),
        disposed=qs.filter(status__in=["sold", "scrapped"]).count(),
        total_purchase_value=float(totals["tp"] or 0),
        total_current_value=float(totals["tv"] or 0),
        total_accumulated_depreciation=float(totals["ta"] or 0),
        by_category=by_cat,
        expiring_warranties_30d=exp_warranty,
        expiring_insurance_30d=exp_insurance,
    )
