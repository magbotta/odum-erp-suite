"""Work Order hooks: material explosion, stock issue/receipt, GL posting (§7)."""
from __future__ import annotations

from decimal import Decimal
from django.utils import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.manufacturing.models import WorkOrder


def set_work_order_number(wo: "WorkOrder") -> None:
    if not wo.work_order_number:
        from core.numbering.service import get_next_number
        wo.work_order_number = get_next_number("WO", company_id=wo.company_id)


def release_work_order(wo: "WorkOrder") -> None:
    """
    Explode the BOM into WorkOrderMaterial rows and create WorkOrderOperation rows.
    This is the manufacturing-equivalent of MRP explosion at the WO level.
    """
    from apps.manufacturing.models import BOMItem, BOMOperation, WorkOrderMaterial, WorkOrderOperation

    if not wo.bom:
        return

    # Clear any existing rows (idempotent re-release)
    wo.materials.filter(is_deleted=False).delete()
    wo.operations.filter(is_deleted=False).delete()

    multiplier = wo.qty / (wo.bom.quantity or Decimal("1"))

    for bom_item in BOMItem.objects.filter(bom=wo.bom, is_deleted=False):
        required = bom_item.quantity * multiplier * (1 + bom_item.scrap_pct / 100)
        WorkOrderMaterial.objects.create(
            work_order=wo,
            item=bom_item.item,
            required_qty=required,
            rate=bom_item.rate,
            source_warehouse=wo.source_warehouse,
            company_id=wo.company_id,
        )

    for bom_op in BOMOperation.objects.filter(bom=wo.bom, is_deleted=False):
        WorkOrderOperation.objects.create(
            work_order=wo,
            sequence=bom_op.sequence,
            operation_name=bom_op.operation_name,
            work_center=bom_op.work_center,
            planned_time=bom_op.time_in_minutes * multiplier,
            operating_cost=bom_op.operating_cost * multiplier,
            company_id=wo.company_id,
        )


def start_production(wo: "WorkOrder") -> None:
    """Record actual start time when a WO moves to In Progress."""
    wo.actual_start_date = timezone.now()
    wo.save(update_fields=["actual_start_date"])


def complete_work_order(wo: "WorkOrder") -> None:
    """
    On completion:
    1. Record actual end time.
    2. Create a StockEntry to receive finished goods into target_warehouse.
    3. Post WIP → Finished Goods GL entry (cross-app).
    """
    from apps.warehouse.models import StockEntry, StockEntryItem
    from apps.warehouse.hooks.stock_entry import post_stock_ledger

    wo.actual_end_date = timezone.now()
    wo.save(update_fields=["actual_end_date"])

    if wo.produced_qty <= 0:
        wo.produced_qty = wo.qty
        wo.save(update_fields=["produced_qty"])

    # Receipt of finished goods
    entry = StockEntry.objects.create(
        entry_type="manufacture",
        posting_date=wo.actual_end_date.date(),
        reference_document="WorkOrder",
        reference_id=wo.id,
        status="Draft",
        company_id=wo.company_id,
    )
    StockEntryItem.objects.create(
        stock_entry=entry,
        item=wo.item,
        qty=wo.produced_qty,
        rate=wo.total_cost / wo.produced_qty if wo.produced_qty else Decimal("0"),
        to_warehouse=wo.target_warehouse,
        company_id=wo.company_id,
    )
    post_stock_ledger(entry)
    entry.status = "Submitted"
    entry.save(update_fields=["status"])
