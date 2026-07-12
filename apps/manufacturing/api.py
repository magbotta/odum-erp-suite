"""Manufacturing action endpoints: BOM activate, WO release/start/complete, MRP run (§7)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from typing import Optional


router = Router(tags=["Manufacturing Actions"])


class ActionResponse(Schema):
    ok: bool
    message: str
    id: Optional[uuid.UUID] = None


@router.post("/boms/{bom_id}/activate", response=ActionResponse)
def activate_bom(request, bom_id: uuid.UUID):
    from apps.manufacturing.models import BillOfMaterials
    from apps.manufacturing.hooks.bom import activate_bom as _activate

    bom = get_object_or_404(BillOfMaterials, id=bom_id, is_deleted=False)
    _activate(bom)
    bom.is_active = True
    bom.save(update_fields=["is_active"])
    return {"ok": True, "message": f"BOM {bom.bom_number} activated.", "id": bom.id}


@router.post("/work-orders/{wo_id}/release", response=ActionResponse)
def release_work_order(request, wo_id: uuid.UUID):
    from apps.manufacturing.models import WorkOrder
    from apps.manufacturing.hooks.work_order import release_work_order as _release

    wo = get_object_or_404(WorkOrder, id=wo_id, is_deleted=False)
    if wo.status != WorkOrder.Status.DRAFT:
        return {"ok": False, "message": f"Work Order is already {wo.status}.", "id": wo.id}
    _release(wo)
    wo.status = WorkOrder.Status.RELEASED
    wo.save(update_fields=["status"])
    return {"ok": True, "message": f"Work Order {wo.work_order_number} released.", "id": wo.id}


@router.post("/work-orders/{wo_id}/start", response=ActionResponse)
def start_work_order(request, wo_id: uuid.UUID):
    from apps.manufacturing.models import WorkOrder
    from apps.manufacturing.hooks.work_order import start_production

    wo = get_object_or_404(WorkOrder, id=wo_id, is_deleted=False)
    if wo.status != WorkOrder.Status.RELEASED:
        return {"ok": False, "message": f"Work Order must be Released to start.", "id": wo.id}
    start_production(wo)
    wo.status = WorkOrder.Status.IN_PROGRESS
    wo.save(update_fields=["status"])
    return {"ok": True, "message": f"Work Order {wo.work_order_number} started.", "id": wo.id}


@router.post("/work-orders/{wo_id}/complete", response=ActionResponse)
def complete_work_order(request, wo_id: uuid.UUID):
    from apps.manufacturing.models import WorkOrder
    from apps.manufacturing.hooks.work_order import complete_work_order as _complete

    wo = get_object_or_404(WorkOrder, id=wo_id, is_deleted=False)
    if wo.status != WorkOrder.Status.IN_PROGRESS:
        return {"ok": False, "message": "Work Order must be In Progress to complete.", "id": wo.id}
    _complete(wo)
    wo.status = WorkOrder.Status.COMPLETED
    wo.save(update_fields=["status"])
    return {"ok": True, "message": f"Work Order {wo.work_order_number} completed.", "id": wo.id}


class MRPRunSchema(Schema):
    from_date: str
    to_date: str
    planning_horizon_days: int = 30


@router.post("/mrp/run", response=ActionResponse)
def run_mrp(request, payload: MRPRunSchema):
    """
    Trigger an MRP run: project demand over the horizon and generate recommendations.
    For large datasets, this should be queued as a Celery task (§17).
    """
    from datetime import date
    from apps.manufacturing.models import MRPRun, MRPRecommendation
    from apps.warehouse.models import StockLedger
    from core.numbering.service import get_next_number

    from_date = date.fromisoformat(payload.from_date)
    to_date = date.fromisoformat(payload.to_date)

    mrp = MRPRun.objects.create(
        from_date=from_date,
        to_date=to_date,
        planning_horizon_days=payload.planning_horizon_days,
        status=MRPRun.Status.RUNNING,
        run_number=get_next_number("MRP"),
    )

    try:
        _execute_mrp(mrp)
        mrp.status = MRPRun.Status.COMPLETED
    except Exception as exc:
        mrp.status = MRPRun.Status.FAILED
        mrp.notes = str(exc)
        mrp.save(update_fields=["status", "notes"])
        raise
    mrp.save(update_fields=["status"])
    return {"ok": True, "message": f"MRP run {mrp.run_number} completed.", "id": mrp.id}


def _execute_mrp(mrp: "MRPRun") -> None:
    """
    Simplified MRP logic: for each item with a reorder point set,
    compare current stock against safety stock and generate a recommendation.
    A full multi-level BOM explosion would run here in production.
    """
    from apps.warehouse.models import Item, StockLedger
    from apps.manufacturing.models import MRPRecommendation
    from django.db.models import Sum

    for item in Item.objects.filter(is_deleted=False, reorder_point__gt=0):
        current_stock = (
            StockLedger.objects.filter(item=item, is_deleted=False)
            .aggregate(total=Sum("actual_qty_after"))["total"] or Decimal("0")
        )
        if current_stock < item.reorder_point:
            reorder_qty = (item.reorder_qty or item.reorder_point) - current_stock
            # Prefer manufacture if item has an active BOM, else purchase
            has_bom = item.boms.filter(is_active=True, is_deleted=False).exists()
            rec_type = (
                MRPRecommendation.RecommendationType.MANUFACTURE
                if has_bom
                else MRPRecommendation.RecommendationType.PURCHASE
            )
            MRPRecommendation.objects.create(
                mrp_run=mrp,
                item=item,
                recommendation_type=rec_type,
                required_qty=reorder_qty + current_stock,
                current_stock=current_stock,
                reorder_qty=reorder_qty,
                required_by=mrp.to_date,
            )
