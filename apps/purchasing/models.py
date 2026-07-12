"""Purchasing models (§6.7): PurchaseOrder, GoodsReceipt, VendorScorecard."""
from __future__ import annotations

from django.db import models

from apps.accounting.models import Vendor
from apps.warehouse.models import Item, Warehouse
from core.metadata_engine.base_entity import BaseEntity


class PurchaseOrder(BaseEntity):
    """
    A purchase order issued to a vendor (§6.7).
    Transitions: Draft → Submitted → (Partially Received) → Received → Billed.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARTIALLY_RECEIVED = "partially_received", "Partially Received"
        RECEIVED = "received", "Received"
        BILLED = "billed", "Billed"
        CANCELLED = "cancelled", "Cancelled"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="purchase_orders")
    po_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    terms_and_conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Links back to the AP bill once it is created
    purchase_bill_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_purchase_orders"
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"

    def __str__(self) -> str:
        return self.po_number or f"PO-{self.pk}"


class PurchaseOrderItem(BaseEntity):
    """Line item on a PurchaseOrder."""

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="purchase_order_items")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    received_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    billed_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    target_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL, related_name="po_items"
    )

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_purchase_order_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class GoodsReceipt(BaseEntity):
    """
    Records the physical receipt of goods against a PurchaseOrder (§6.7).
    Posting triggers StockEntry + StockLedger update.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="goods_receipts"
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="goods_receipts")
    grn_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_goods_receipts"
        verbose_name = "Goods Receipt"
        verbose_name_plural = "Goods Receipts"

    def __str__(self) -> str:
        return self.grn_number or f"GRN-{self.pk}"


class GoodsReceiptItem(BaseEntity):
    """Line item on a GoodsReceipt."""

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="goods_receipt_items")
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="receipt_items",
    )
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="received_items")
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_goods_receipt_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"
