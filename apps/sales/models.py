"""Sales models — full §6.8 implementation.

Covers: Promotion Rules, Quotations, Sales Orders with credit-limit enforcement,
Delivery Notes (stock out), Commission Structures and Entries, Subscription Contracts,
and RMA Returns.

Note: PriceList and ItemPrice have been moved to apps.product_catalogue.
      All price_list FK references here use price_list_id UUID soft-links.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounting.models import Customer
from apps.warehouse.models import Item, Warehouse
from core.metadata_engine.base_entity import BaseEntity


# ── Promotion Rules ───────────────────────────────────────────────────────────

class PromotionRule(BaseEntity):
    """
    Automatic discount rule applied at order time (§6.8).
    Multiple conditions can be stacked on one rule (all must match).
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "pct", "Percentage"
        FIXED_AMOUNT = "fixed", "Fixed Amount"
        FREE_QTY = "free_qty", "Free Quantity"

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENTAGE
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    # Optional scope limiters
    apply_on_item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="promotion_rules"
    )
    apply_on_customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="promotion_rules"
    )
    min_order_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    priority = models.PositiveSmallIntegerField(
        default=10, help_text="Lower number = higher priority when multiple rules match."
    )
    # Require a discount-approval workflow above this threshold
    approval_required_above = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Discount % above which approval is required (0 = never).",
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_promotion_rules"
        ordering = ["priority"]

    def __str__(self) -> str:
        return self.name


# ── Quotation ─────────────────────────────────────────────────────────────────

class Quotation(BaseEntity):
    """
    A sales quotation (proposal) sent to a customer (§6.8).
    Draft → Sent → Accepted → Converted | Declined | Expired.
    """

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
    discount_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # E-signature
    e_signature_requested = models.BooleanField(default=False)
    e_signature_received_at = models.DateTimeField(null=True, blank=True)
    # Cross-app soft links
    opportunity_id = models.UUIDField(null=True, blank=True, db_index=True)
    price_list_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Soft link to product_catalogue.PriceList.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="quotations",
    )

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
    promotion_rule = models.ForeignKey(
        PromotionRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_items"
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_quotation_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


# ── Sales Order ───────────────────────────────────────────────────────────────

class SalesOrder(BaseEntity):
    """
    A confirmed customer order (§6.8).
    Credit-limit check enforced at submission; links forward to Delivery + Invoice.
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
    discount_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    # Credit control
    credit_limit_exceeded = models.BooleanField(default=False)
    credit_override_by_id = models.UUIDField(null=True, blank=True)
    # Shipping
    shipping_address = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Cross-app soft links
    opportunity_id = models.UUIDField(null=True, blank=True, db_index=True)
    price_list_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Soft link to product_catalogue.PriceList.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales_orders",
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_orders"
        verbose_name = "Sales Order"

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


# ── Delivery Note ─────────────────────────────────────────────────────────────

class DeliveryNote(BaseEntity):
    """
    Outbound delivery against a Sales Order — creates a StockEntry (issue) on submit (§6.8).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    sales_order = models.ForeignKey(
        SalesOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="deliveries")
    dn_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    shipping_address = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    # Soft link to the StockEntry created on submission
    stock_entry_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_delivery_notes"
        verbose_name = "Delivery Note"

    def __str__(self) -> str:
        return self.dn_number or f"DN-{self.pk}"


class DeliveryNoteItem(BaseEntity):
    """Line item on a DeliveryNote."""

    delivery_note = models.ForeignKey(
        DeliveryNote, on_delete=models.CASCADE, related_name="items"
    )
    so_item = models.ForeignKey(
        SalesOrderItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="delivery_items"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="delivery_items")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="delivery_items"
    )
    batch_no = models.CharField(max_length=100, blank=True)
    serial_nos = models.TextField(blank=True, help_text="Newline-separated serial numbers")

    class Meta(BaseEntity.Meta):
        db_table = "sales_delivery_note_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


# ── Commission Structure & Entries ────────────────────────────────────────────

class CommissionStructure(BaseEntity):
    """
    Defines how commissions are calculated for a rep/team/product line (§6.8).
    """

    class BasisType(models.TextChoices):
        REVENUE = "revenue", "% of Revenue"
        GROSS_PROFIT = "gross_profit", "% of Gross Profit"
        FLAT = "flat", "Flat Amount per Order"

    name = models.CharField(max_length=150)
    basis = models.CharField(max_length=15, choices=BasisType.choices, default=BasisType.REVENUE)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_commission_structures"

    def __str__(self) -> str:
        return self.name


class CommissionRate(BaseEntity):
    """
    A tiered commission rate within a CommissionStructure.
    The highest applicable `min_amount` tier is used.
    """

    structure = models.ForeignKey(
        CommissionStructure, on_delete=models.CASCADE, related_name="rates"
    )
    min_amount = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Min order/revenue amount for this rate to apply.",
    )
    rate_pct = models.DecimalField(
        max_digits=6, decimal_places=4,
        help_text="Commission percentage or flat amount depending on structure basis.",
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_commission_rates"
        ordering = ["-min_amount"]

    def __str__(self) -> str:
        return f"{self.structure} @ {self.min_amount}+ → {self.rate_pct}%"


class CommissionEntry(BaseEntity):
    """
    Commission earned by a sales rep on a submitted/delivered Sales Order (§6.8).
    Created automatically when an SO is delivered.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, related_name="commission_entries"
    )
    rep_id = models.UUIDField(db_index=True, help_text="Soft link to HRM Employee")
    rep_name = models.CharField(max_length=200)
    structure = models.ForeignKey(
        CommissionStructure, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="entries",
    )
    base_amount = models.DecimalField(max_digits=19, decimal_places=4, help_text="Amount the rate was applied to")
    rate_pct = models.DecimalField(max_digits=6, decimal_places=4)
    commission_amount = models.DecimalField(max_digits=19, decimal_places=4)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    payout_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_commission_entries"

    def __str__(self) -> str:
        return f"{self.rep_name} / {self.sales_order} → {self.commission_amount}"


# ── Subscription Contracts ────────────────────────────────────────────────────

class SubscriptionContract(BaseEntity):
    """
    Recurring/subscription billing contract (§6.8).
    Drives automatic Sales Order or Invoice generation on each billing date.
    """

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="subscriptions"
    )
    contract_number = models.CharField(max_length=50, blank=True, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    frequency = models.CharField(max_length=15, choices=Frequency.choices, default=Frequency.MONTHLY)
    currency = models.CharField(max_length=3, default="USD")
    monthly_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    next_billing_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    price_list_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Soft link to product_catalogue.PriceList.",
    )

    class Meta(BaseEntity.Meta):
        db_table = "sales_subscription_contracts"

    def __str__(self) -> str:
        return self.contract_number or f"SUB-{self.pk}"


class SubscriptionItem(BaseEntity):
    """Line item on a SubscriptionContract — defines the recurring service/product."""

    contract = models.ForeignKey(
        SubscriptionContract, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="subscription_items")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    description = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_subscription_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty} ({self.contract})"


class SubscriptionBillingRun(BaseEntity):
    """
    Records a single billing cycle execution for a SubscriptionContract.
    Soft-links to the Sales Order or Invoice generated.
    """

    contract = models.ForeignKey(
        SubscriptionContract, on_delete=models.CASCADE, related_name="billing_runs"
    )
    billing_date = models.DateField()
    period_start = models.DateField()
    period_end = models.DateField()
    sales_order_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, default="generated")

    class Meta(BaseEntity.Meta):
        db_table = "sales_subscription_billing_runs"
        unique_together = [("contract", "billing_date")]


# ── Sales Return (RMA) ────────────────────────────────────────────────────────

class SalesReturn(BaseEntity):
    """
    Return Merchandise Authorization — customer returns goods (§6.8).
    Creates a StockEntry (receipt) on submit to bring stock back in.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    return_number = models.CharField(max_length=50, blank=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="returns")
    delivery_note = models.ForeignKey(
        DeliveryNote, null=True, blank=True, on_delete=models.SET_NULL, related_name="returns"
    )
    posting_date = models.DateField()
    return_reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Soft link to credit note in Accounting
    credit_note_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_returns"
        verbose_name = "Sales Return"

    def __str__(self) -> str:
        return self.return_number or f"SRN-{self.pk}"


class SalesReturnItem(BaseEntity):
    """Line item on a SalesReturn."""

    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name="items")
    dn_item = models.ForeignKey(
        DeliveryNoteItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="return_items",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="return_items")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="return_items"
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sales_return_items"

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"
