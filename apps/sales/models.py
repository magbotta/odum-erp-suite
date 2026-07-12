"""Sales models (§6.8): Quotation, SalesOrder, Commission, RMA."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounting.models import Customer
from apps.warehouse.models import Item, Warehouse
from core.metadata_engine.base_entity import BaseEntity


class PriceList(BaseEntity):
    """Named price list with optional customer, date range, and currency scope."""

    name = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, default="USD")
    is_buying = models.BooleanField(default=False)
    is_selling = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_price_lists"

    def __str__(self) -> str:
        return self.name


class ItemPrice(BaseEntity):
    """Price of an Item within a PriceList (§6.8)."""

    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="item_prices")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="prices")
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    min_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0,
                                  help_text="Minimum qty for this price to apply (volume pricing)")

    class Meta(BaseEntity.Meta):
        db_table = "sales_item_prices"
        unique_together = [("price_list", "item", "min_qty")]

    def __str__(self) -> str:
        return f"{self.price_list} / {self.item} = {self.rate}"


class Quotation(BaseEntity):
    """A sales quotation (proposal) sent to a customer (§6.8)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        CONVERTED = "converted", "Converted to Order"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="quotations")
    quotation_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    valid_till = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="quotations",
    )
    # CRM cross-app soft link
    opportunity_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_quotations"

    def __str__(self) -> str:
        return self.quotation_number or f"QT-{self.pk}"


class QuotationItem(BaseEntity):
    """Line item on a Quotation."""

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="quotation_items")
    description = models.CharField(max_length=255, blank=True)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4)

    class Meta(BaseEntity.Meta):
        db_table = "sales_quotation_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class SalesOrder(BaseEntity):
    """
    A confirmed customer order (§6.8).
    Links back to a Quotation and forward to delivery + invoice.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PROCESSING = "processing", "Processing"
        PARTIALLY_DELIVERED = "partially_delivered", "Partially Delivered"
        DELIVERED = "delivered", "Delivered"
        BILLED = "billed", "Billed"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_orders")
    so_number = models.CharField(max_length=50, blank=True, db_index=True)
    quotation = models.ForeignKey(
        Quotation, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_orders"
    )
    posting_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales_orders",
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_orders"
        verbose_name = "Sales Order"
        verbose_name_plural = "Sales Orders"

    def __str__(self) -> str:
        return self.so_number or f"SO-{self.pk}"


class SalesOrderItem(BaseEntity):
    """Line item on a SalesOrder."""

    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="sales_order_items")
    description = models.CharField(max_length=255, blank=True)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    delivered_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    billed_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL, related_name="so_items"
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_order_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"
