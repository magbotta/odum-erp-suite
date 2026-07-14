"""Warehouse / Inventory models — full §6.9 implementation.

Covers: UOM, Item master, Warehouses, Bins, Price lists, Batch/Serial tracking,
Stock entries, Stock ledger, Reorder rules, Cycle count sheets.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


# ── Units of Measure ──────────────────────────────────────────────────────────

class UOM(BaseEntity):
    """Unit of Measure (Kg, Pcs, Ltr, Box, etc.)."""
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_uoms"
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"

    def __str__(self) -> str:
        return self.abbreviation


class UOMConversion(BaseEntity):
    """Conversion factor between two UOMs (e.g. 1 Box = 12 Pcs)."""
    from_uom = models.ForeignKey(UOM, on_delete=models.CASCADE, related_name="conversions_from")
    to_uom = models.ForeignKey(UOM, on_delete=models.CASCADE, related_name="conversions_to")
    conversion_factor = models.DecimalField(max_digits=19, decimal_places=6)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_uom_conversions"
        unique_together = [("from_uom", "to_uom")]

    def __str__(self) -> str:
        return f"1 {self.from_uom} = {self.conversion_factor} {self.to_uom}"


# ── Item master ───────────────────────────────────────────────────────────────

class ItemCategory(BaseEntity):
    name = models.CharField(max_length=150)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_item_categories"
        verbose_name = "Item Category"
        verbose_name_plural = "Item Categories"

    def __str__(self) -> str:
        return self.name


class Item(BaseEntity):
    """
    A product, raw material, or service (§6.9).
    The central item master used by Warehouse, Sales, and Purchasing.
    """

    class ValuationMethod(models.TextChoices):
        FIFO = "fifo", "FIFO"
        MOVING_AVG = "moving_avg", "Moving Average"
        STANDARD = "standard", "Standard Cost"

    item_code = models.CharField(max_length=100, unique=True, db_index=True)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ItemCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )
    uom = models.ForeignKey(
        UOM, null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )
    purchase_uom = models.ForeignKey(
        UOM, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_items"
    )
    # Flags
    is_stock_item = models.BooleanField(default=True)
    is_purchase_item = models.BooleanField(default=True)
    is_sales_item = models.BooleanField(default=True)
    is_service_item = models.BooleanField(default=False)
    has_serial_no = models.BooleanField(default=False)
    has_batch = models.BooleanField(default=False)
    # Shelf life / expiry
    has_expiry_date = models.BooleanField(default=False)
    shelf_life_days = models.PositiveIntegerField(default=0)
    # Pricing
    standard_selling_price = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    standard_buying_price = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    valuation_method = models.CharField(
        max_length=20, choices=ValuationMethod.choices, default=ValuationMethod.FIFO
    )
    # Physical attributes
    weight_per_unit = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    weight_uom = models.ForeignKey(
        UOM, null=True, blank=True, on_delete=models.SET_NULL, related_name="weight_items"
    )
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    # Cross-app GL soft links
    income_account_id = models.UUIDField(null=True, blank=True)
    expense_account_id = models.UUIDField(null=True, blank=True)
    stock_account_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Soft link to product_catalogue.Product — UUID only, no FK across app boundary
    product_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="UUID of the product_catalogue.Product this Item extends.",
    )

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_items"

    def __str__(self) -> str:
        return f"{self.item_code} — {self.item_name}"


# ── Warehouse & Bin structure ─────────────────────────────────────────────────

class Warehouse(BaseEntity):
    """
    A physical or virtual storage location (§6.9).
    Supports multi-warehouse and hierarchical bin/location structure.
    """

    class WarehouseType(models.TextChoices):
        TRANSIT = "transit", "Transit"
        STORES = "stores", "Stores"
        WORK_IN_PROGRESS = "wip", "Work-in-Progress"
        FINISHED_GOODS = "finished_goods", "Finished Goods"
        RETURNS = "returns", "Returns"
        VIRTUAL = "virtual", "Virtual"

    warehouse_name = models.CharField(max_length=150)
    warehouse_code = models.CharField(max_length=20, unique=True)
    warehouse_type = models.CharField(
        max_length=20, choices=WarehouseType.choices, default=WarehouseType.STORES
    )
    is_group = models.BooleanField(default=False)
    parent_warehouse = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="child_warehouses"
    )
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_warehouses"

    def __str__(self) -> str:
        return f"{self.warehouse_code} — {self.warehouse_name}"


class Bin(BaseEntity):
    """
    A specific bin / shelf / rack location within a Warehouse (§6.9).
    Enables bin-level putaway and picking strategies.
    """

    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="bins")
    bin_code = models.CharField(max_length=50)
    aisle = models.CharField(max_length=20, blank=True)
    rack = models.CharField(max_length=20, blank=True)
    level = models.CharField(max_length=20, blank=True)
    position = models.CharField(max_length=20, blank=True)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_bins"
        unique_together = [("warehouse", "bin_code")]

    def __str__(self) -> str:
        return f"{self.warehouse.warehouse_code}/{self.bin_code}"


# ── Batch & Serial tracking ───────────────────────────────────────────────────

class Batch(BaseEntity):
    """
    A batch/lot of items with expiry date tracking (§6.9).
    Used for Healthcare, Agriculture, and any perishable goods.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        RECALLED = "recalled", "Recalled"
        CONSUMED = "consumed", "Fully Consumed"

    batch_id = models.CharField(max_length=100, db_index=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="batches")
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    batch_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    remaining_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    supplier_lot_no = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_batches"
        unique_together = [("batch_id", "item")]

    def __str__(self) -> str:
        return f"Batch {self.batch_id} — {self.item.item_code}"


class SerialNo(BaseEntity):
    """
    An individual serialised unit of a tracked item (§6.9).
    Tracks provenance from receipt through sale.
    """

    class Status(models.TextChoices):
        IN_STORE = "in_store", "In Store"
        DELIVERED = "delivered", "Delivered"
        RETURNED = "returned", "Returned"
        SCRAPPED = "scrapped", "Scrapped"

    serial_no = models.CharField(max_length=150, db_index=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="serial_numbers")
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL, related_name="serial_numbers"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_STORE)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry_date = models.DateField(null=True, blank=True, db_index=True)
    # Voucher refs (soft)
    purchase_document_no = models.CharField(max_length=100, blank=True)
    delivery_document_no = models.CharField(max_length=100, blank=True)
    # Cross-app: who owns this now
    customer_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_serial_numbers"
        unique_together = [("serial_no", "item")]

    def __str__(self) -> str:
        return f"SN:{self.serial_no} — {self.item.item_code}"


# ── Reorder rules ─────────────────────────────────────────────────────────────

class ReorderRule(BaseEntity):
    """
    Reorder point, safety stock, and reorder qty per Item per Warehouse (§6.9).
    Triggers auto purchase-requisition generation when stock falls below re_order_level.
    """

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="reorder_rules")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="reorder_rules")
    re_order_level = models.DecimalField(max_digits=19, decimal_places=4, help_text="Trigger reorder when stock drops to this level")
    re_order_qty = models.DecimalField(max_digits=19, decimal_places=4, help_text="Quantity to order / produce")
    safety_stock = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    material_request_type = models.CharField(
        max_length=20,
        choices=[("purchase","Purchase"),("manufacture","Manufacture"),("transfer","Transfer")],
        default="purchase",
    )

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_reorder_rules"
        unique_together = [("item", "warehouse")]

    def __str__(self) -> str:
        return f"Reorder: {self.item.item_code} @ {self.warehouse.warehouse_code} ≤ {self.re_order_level}"


# ── Stock entries ─────────────────────────────────────────────────────────────

class StockEntry(BaseEntity):
    """
    A head record for any stock movement — receipt, issue, transfer, adjustment (§6.9).
    Lines are in StockEntryDetail.
    """

    class EntryType(models.TextChoices):
        RECEIPT = "receipt", "Material Receipt"
        ISSUE = "issue", "Material Issue"
        TRANSFER = "transfer", "Stock Transfer"
        ADJUSTMENT = "adjustment", "Stock Reconciliation"
        MANUFACTURE = "manufacture", "Manufacture (WO Issue + Receipt)"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    posting_date = models.DateField()
    from_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL, related_name="outbound_entries"
    )
    to_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL, related_name="inbound_entries"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.TextField(blank=True)
    voucher_type = models.CharField(max_length=50, blank=True)
    voucher_no = models.CharField(max_length=100, blank=True, db_index=True)
    total_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_stock_entries"

    def __str__(self) -> str:
        return f"{self.entry_type} / {self.posting_date}"


class StockEntryDetail(BaseEntity):
    """Line item within a StockEntry."""

    stock_entry = models.ForeignKey(StockEntry, on_delete=models.CASCADE, related_name="details")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_entry_details")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    basic_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_entry_details"
    )
    serial_no = models.TextField(blank=True, help_text="Newline-separated serial numbers")
    uom = models.ForeignKey(
        UOM, null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_entry_details"
    )
    bin_from = models.ForeignKey(
        Bin, null=True, blank=True, on_delete=models.SET_NULL, related_name="outbound_details"
    )
    bin_to = models.ForeignKey(
        Bin, null=True, blank=True, on_delete=models.SET_NULL, related_name="inbound_details"
    )

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_stock_entry_details"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


# ── Stock Ledger ──────────────────────────────────────────────────────────────

class StockLedger(BaseEntity):
    """
    Immutable append-only ledger of every stock movement (§6.9).
    Never updated — new corrections are additional entries with reversed qty.
    """

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="ledger_entries")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="ledger_entries")
    posting_date = models.DateField(db_index=True)
    posting_time = models.TimeField()
    voucher_type = models.CharField(max_length=50, db_index=True)
    voucher_no = models.CharField(max_length=100, db_index=True)
    actual_qty = models.DecimalField(max_digits=19, decimal_places=4)
    qty_after_transaction = models.DecimalField(max_digits=19, decimal_places=4)
    incoming_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    valuation_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    stock_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    stock_value_difference = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries"
    )
    is_cancelled = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_stock_ledger"
        indexes = [
            models.Index(fields=["item", "warehouse", "posting_date"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.actual_qty >= 0 else ""
        return f"{self.item} {sign}{self.actual_qty} @ {self.warehouse}"


# ── Cycle Count / Physical Inventory ─────────────────────────────────────────

class CycleCountSheet(BaseEntity):
    """
    A physical stock count sheet for a warehouse or sub-location (§6.9).
    After completion, submitting it posts StockLedger adjustments.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="cycle_count_sheets")
    count_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.TextField(blank=True)
    total_variance_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_cycle_count_sheets"

    def __str__(self) -> str:
        return f"Cycle Count — {self.warehouse} [{self.count_date}]"


class CycleCountDetail(BaseEntity):
    """One item line in a CycleCountSheet."""

    sheet = models.ForeignKey(CycleCountSheet, on_delete=models.CASCADE, related_name="details")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="cycle_count_details")
    bin = models.ForeignKey(
        Bin, null=True, blank=True, on_delete=models.SET_NULL, related_name="cycle_count_details"
    )
    system_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0, help_text="Qty per stock ledger")
    counted_qty = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    variance_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    valuation_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    variance_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    is_counted = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_cycle_count_details"

    def __str__(self) -> str:
        return f"{self.item.item_code}: sys={self.system_qty} counted={self.counted_qty}"
