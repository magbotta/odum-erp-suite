"""Warehouse / Inventory models (§6.9)."""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class UOM(BaseEntity):
    """Unit of Measure (Kg, Pcs, Ltr, etc.)."""
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_uoms"
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"

    def __str__(self) -> str:
        return self.abbreviation


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
    is_stock_item = models.BooleanField(default=True)
    is_purchase_item = models.BooleanField(default=True)
    is_sales_item = models.BooleanField(default=True)
    is_service_item = models.BooleanField(default=False)
    has_serial_no = models.BooleanField(default=False)
    has_batch = models.BooleanField(default=False)
    standard_selling_price = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    standard_buying_price = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    valuation_method = models.CharField(
        max_length=20, choices=ValuationMethod.choices, default=ValuationMethod.FIFO
    )
    # Cross-app: income account UUID (Accounting)
    income_account_id = models.UUIDField(null=True, blank=True)
    expense_account_id = models.UUIDField(null=True, blank=True)
    stock_account_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_items"

    def __str__(self) -> str:
        return f"{self.item_code} — {self.item_name}"


class Warehouse(BaseEntity):
    """
    A physical or virtual storage location (§6.9).
    Supports multi-warehouse and hierarchical bin/location structure.
    """

    warehouse_name = models.CharField(max_length=150)
    warehouse_code = models.CharField(max_length=20, unique=True)
    is_group = models.BooleanField(default=False)
    parent_warehouse = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="child_warehouses"
    )
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_warehouses"

    def __str__(self) -> str:
        return f"{self.warehouse_code} — {self.warehouse_name}"


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
    # Voucher linkage: which source document triggered this movement
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
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.TextField(blank=True, help_text="Newline-separated serial numbers")

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_stock_entry_details"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


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
    actual_qty = models.DecimalField(max_digits=19, decimal_places=4, help_text="Negative=issue, positive=receipt")
    qty_after_transaction = models.DecimalField(max_digits=19, decimal_places=4)
    incoming_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    valuation_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    stock_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    stock_value_difference = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    is_cancelled = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "warehouse_stock_ledger"
        indexes = [
            models.Index(fields=["item", "warehouse", "posting_date"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.actual_qty >= 0 else ""
        return f"{self.item} {sign}{self.actual_qty} @ {self.warehouse} [{self.voucher_no}]"
