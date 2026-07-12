"""
Manufacturing models (§7, Phase 3): BOM, Routing, Work Centers, Work Orders, MRP.
Built on Warehouse (materials), Purchasing (subcontracting), Accounting (WIP/COGS).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.warehouse.models import Item, Warehouse
from core.metadata_engine.base_entity import BaseEntity


# ---------------------------------------------------------------------------
# Bill of Materials
# ---------------------------------------------------------------------------

class BillOfMaterials(BaseEntity):
    """
    A multi-level bill of materials for a finished / semi-finished product (§7).
    Multiple active BOMs per item are supported (e.g. alternate formulations).
    """

    class BOMMType(models.TextChoices):
        MANUFACTURE = "manufacture", "Manufacture"
        SUBCONTRACT = "subcontract", "Subcontract"
        PHANTOM = "phantom", "Phantom"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="boms")
    bom_number = models.CharField(max_length=50, blank=True, db_index=True)
    version = models.PositiveSmallIntegerField(default=1)
    quantity = models.DecimalField(max_digits=19, decimal_places=4, default=1,
                                   help_text="Quantity of finished item this BOM produces")
    uom = models.CharField(max_length=30, default="Nos")
    bom_type = models.CharField(max_length=20, choices=BOMMType.choices, default=BOMMType.MANUFACTURE)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    remarks = models.TextField(blank=True)
    # Costing (computed when BOM is saved/submitted)
    raw_material_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    operating_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_boms"
        verbose_name = "Bill of Materials"
        verbose_name_plural = "Bills of Materials"

    def __str__(self) -> str:
        return f"BOM/{self.bom_number or self.pk} ({self.item})"


class BOMItem(BaseEntity):
    """A component line within a BOM."""

    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="bom_items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="used_in_boms")
    quantity = models.DecimalField(max_digits=19, decimal_places=4)
    uom = models.CharField(max_length=30, default="Nos")
    rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    scrap_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                    help_text="Expected scrap/waste %")
    sourced_by_supplier = models.BooleanField(default=False,
                                               help_text="For subcontracting: supplier provides this component")
    # If this component has its own BOM, it can be exploded in MRP
    child_bom = models.ForeignKey(
        BillOfMaterials, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="parent_bom_items",
    )
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_bom_items"
        ordering = ["bom", "sequence"]

    def __str__(self) -> str:
        return f"{self.bom} → {self.item} × {self.quantity}"


class BOMOperation(BaseEntity):
    """An operation / routing step defined on a BOM."""

    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="operations")
    sequence = models.PositiveSmallIntegerField(default=0)
    operation_name = models.CharField(max_length=150)
    work_center = models.ForeignKey(
        "WorkCenter", on_delete=models.PROTECT, related_name="bom_operations"
    )
    time_in_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    operating_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_bom_operations"
        ordering = ["bom", "sequence"]

    def __str__(self) -> str:
        return f"{self.bom} / {self.sequence}. {self.operation_name}"


# ---------------------------------------------------------------------------
# Work Centers
# ---------------------------------------------------------------------------

class WorkCenter(BaseEntity):
    """
    A machine, cell, or worker group where manufacturing operations are performed.
    Capacity is in hours per day; used for production scheduling and costing.
    """

    class WorkCenterType(models.TextChoices):
        MACHINE = "machine", "Machine"
        PERSON = "person", "Person / Workstation"
        CELL = "cell", "Manufacturing Cell"

    name = models.CharField(max_length=150)
    work_center_type = models.CharField(
        max_length=20, choices=WorkCenterType.choices, default=WorkCenterType.MACHINE
    )
    capacity = models.DecimalField(max_digits=7, decimal_places=2, default=8,
                                   help_text="Available hours per day")
    hourly_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0,
                                      help_text="Operating cost per hour")
    description = models.TextField(blank=True)
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_centers",
    )
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_work_centers"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Work Orders
# ---------------------------------------------------------------------------

class WorkOrder(BaseEntity):
    """
    A production order to manufacture a specific quantity of a finished item (§7).
    Transitions: Draft → Released → In Progress → Completed / Cancelled.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RELEASED = "released", "Released"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    work_order_number = models.CharField(max_length=50, blank=True, db_index=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="work_orders")
    bom = models.ForeignKey(
        BillOfMaterials, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    qty = models.DecimalField(max_digits=19, decimal_places=4, help_text="Quantity to produce")
    produced_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    scrap_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    uom = models.CharField(max_length=30, default="Nos")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    planned_start_date = models.DateTimeField(null=True, blank=True)
    planned_end_date = models.DateTimeField(null=True, blank=True)
    actual_start_date = models.DateTimeField(null=True, blank=True)
    actual_end_date = models.DateTimeField(null=True, blank=True)
    target_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_order_targets",
    )
    source_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_order_sources",
    )
    # Costing
    material_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    operating_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Back-reference if created by MRP
    mrp_run_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_work_orders"

    def __str__(self) -> str:
        return self.work_order_number or f"WO/{self.pk}"


class WorkOrderOperation(BaseEntity):
    """One routing step / operation within a Work Order, with actual time tracking."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="operations")
    sequence = models.PositiveSmallIntegerField(default=0)
    operation_name = models.CharField(max_length=150)
    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.PROTECT, related_name="work_order_operations"
    )
    planned_time = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                       help_text="Planned time in minutes")
    actual_time = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_order_operations",
    )

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_work_order_operations"
        ordering = ["work_order", "sequence"]

    def __str__(self) -> str:
        return f"{self.work_order} / {self.sequence}. {self.operation_name}"


class WorkOrderMaterial(BaseEntity):
    """
    A material requirement row on a Work Order.
    Tracks required vs. issued quantities for WIP stock control.
    """

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="materials")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="work_order_materials")
    required_qty = models.DecimalField(max_digits=19, decimal_places=4)
    issued_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    returned_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    source_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="work_order_material_sources",
    )
    rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_work_order_materials"

    def __str__(self) -> str:
        return f"{self.work_order} — {self.item} ({self.issued_qty}/{self.required_qty})"


# ---------------------------------------------------------------------------
# MRP
# ---------------------------------------------------------------------------

class MRPRun(BaseEntity):
    """
    A Material Requirements Planning run: explodes demand into purchase/production
    requirements (§7, CLAUDE.md §3 table).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    run_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    planning_horizon_days = models.PositiveSmallIntegerField(default=30)
    from_date = models.DateField()
    to_date = models.DateField()
    warehouses = models.ManyToManyField(Warehouse, blank=True, related_name="mrp_runs")
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_mrp_runs"
        verbose_name = "MRP Run"

    def __str__(self) -> str:
        return self.run_number or f"MRP/{self.pk}"


class MRPRecommendation(BaseEntity):
    """
    A single recommendation produced by an MRP run: make or buy a quantity of an item
    to satisfy projected demand within the planning horizon.
    """

    class RecommendationType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        MANUFACTURE = "manufacture", "Manufacture"

    class ActionStatus(models.TextChoices):
        OPEN = "open", "Open"
        ACTIONED = "actioned", "Actioned"
        IGNORED = "ignored", "Ignored"

    mrp_run = models.ForeignKey(MRPRun, on_delete=models.CASCADE, related_name="recommendations")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="mrp_recommendations")
    recommendation_type = models.CharField(max_length=20, choices=RecommendationType.choices)
    required_qty = models.DecimalField(max_digits=19, decimal_places=4)
    current_stock = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    reorder_qty = models.DecimalField(max_digits=19, decimal_places=4)
    required_by = models.DateField()
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="mrp_recommendations",
    )
    action_status = models.CharField(
        max_length=20, choices=ActionStatus.choices, default=ActionStatus.OPEN
    )
    # Cross-app: link to created PO or Work Order
    actioned_document_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "manufacturing_mrp_recommendations"

    def __str__(self) -> str:
        return f"{self.mrp_run} → {self.recommendation_type} {self.reorder_qty} × {self.item}"
