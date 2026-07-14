"""Purchasing / Supply Chain models — full §6.7 implementation.

Covers: Purchase Requisition, RFQ (with supplier responses), Purchase Order,
Goods Receipt, Vendor Scorecard, Landed Cost, Supplier Qualification,
Purchase Return.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


# ── Purchase Requisition ──────────────────────────────────────────────────────

class PurchaseRequisition(BaseEntity):
    """
    Internal request for goods/services before a PO is raised (§6.7).
    Draft → Submitted → Approved → Ordered | Rejected.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        ORDERED = "ordered", "Ordered"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    requisition_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    required_by_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    purpose = models.TextField(blank=True)
    requested_by_id = models.UUIDField(null=True, blank=True)   # soft link to HRM Employee
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Cross-app: cost centre / project
    cost_center_id = models.UUIDField(null=True, blank=True)
    project_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_requisitions"
        verbose_name = "Purchase Requisition"

    def __str__(self) -> str:
        return self.requisition_number or f"PR-{self.pk}"


class PurchaseRequisitionItem(BaseEntity):
    """Line item on a PurchaseRequisition."""

    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.CASCADE, related_name="items"
    )
    # Soft link to warehouse.Item — avoids cross-app FK
    item_id = models.UUIDField(db_index=True)
    # Soft link to product_catalogue.Product (UUID only, no FK)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    uom = models.CharField(max_length=20, default="EA")
    estimated_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    estimated_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    warehouse_id = models.UUIDField(null=True, blank=True)   # target warehouse (soft)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_requisition_items"

    def __str__(self) -> str:
        return f"{self.item_code} × {self.qty}"


# ── Request for Quotation ─────────────────────────────────────────────────────

class RequestForQuotation(BaseEntity):
    """
    RFQ sent to one or more suppliers for competitive pricing (§6.7).
    Draft → Sent → Closed → Awarded.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        CLOSED = "closed", "Closed"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"

    rfq_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    response_deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    message_for_supplier = models.TextField(blank=True)
    # Soft link to the PR that originated this RFQ (optional)
    requisition_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_rfqs"
        verbose_name = "Request for Quotation"
        verbose_name_plural = "Requests for Quotation"

    def __str__(self) -> str:
        return self.rfq_number or f"RFQ-{self.pk}"


class RFQItem(BaseEntity):
    """Line item on an RFQ."""

    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name="items")
    item_id = models.UUIDField(db_index=True)
    # Soft link to product_catalogue.Product (UUID only, no FK)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    uom = models.CharField(max_length=20, default="EA")
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_rfq_items"

    def __str__(self) -> str:
        return f"{self.item_code} × {self.qty}"


class RFQSupplierResponse(BaseEntity):
    """
    A supplier's quoted price in response to an RFQ (§6.7).
    Used for side-by-side vendor comparison before PO award.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RESPONDED = "responded", "Responded"
        AWARDED = "awarded", "Awarded"
        REJECTED = "rejected", "Rejected"

    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name="supplier_responses"
    )
    # Cross-app soft link to accounting.Vendor
    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    response_date = models.DateField(null=True, blank=True)
    valid_till = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    delivery_days = models.PositiveIntegerField(default=0)
    payment_terms = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_rfq_supplier_responses"
        unique_together = [("rfq", "vendor_id")]

    def __str__(self) -> str:
        return f"{self.rfq} — {self.vendor_name}"


class RFQSupplierResponseItem(BaseEntity):
    """Quoted price for one line item in an RFQ supplier response."""

    response = models.ForeignKey(
        RFQSupplierResponse, on_delete=models.CASCADE, related_name="items"
    )
    rfq_item = models.ForeignKey(
        RFQItem, on_delete=models.CASCADE, related_name="supplier_items"
    )
    quoted_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    quoted_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    lead_time_days = models.PositiveIntegerField(default=0)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_rfq_response_items"

    def __str__(self) -> str:
        return f"{self.response} / {self.rfq_item}"


# ── Purchase Order ────────────────────────────────────────────────────────────

class PurchaseOrder(BaseEntity):
    """
    Purchase order issued to a vendor (§6.7).
    Draft → Submitted → Partially Received → Received → Billed | Cancelled.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARTIALLY_RECEIVED = "partially_received", "Partially Received"
        RECEIVED = "received", "Received"
        BILLED = "billed", "Billed"
        CANCELLED = "cancelled", "Cancelled"

    class ApprovalStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not Required"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Cross-app soft link to accounting.Vendor
    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    po_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    approval_status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.NOT_REQUIRED
    )
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    terms_and_conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Blanket / contract PO
    is_blanket_order = models.BooleanField(default=False)
    blanket_order_end_date = models.DateField(null=True, blank=True)
    # Drop-ship
    is_drop_ship = models.BooleanField(default=False)
    drop_ship_address = models.TextField(blank=True)
    # Cross-app soft links
    requisition_id = models.UUIDField(null=True, blank=True, db_index=True)
    rfq_id = models.UUIDField(null=True, blank=True, db_index=True)
    purchase_bill_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_purchase_orders"
        verbose_name = "Purchase Order"

    def __str__(self) -> str:
        return self.po_number or f"PO-{self.pk}"


class PurchaseOrderItem(BaseEntity):
    """Line item on a PurchaseOrder."""

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item_id = models.UUIDField(db_index=True)
    # Soft link to product_catalogue.Product (UUID only, no FK)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    uom = models.CharField(max_length=20, default="EA")
    received_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    billed_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    warehouse_id = models.UUIDField(null=True, blank=True)   # target warehouse (soft)
    description = models.TextField(blank=True)
    # RFQ traceability
    rfq_response_item_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_purchase_order_items"

    def __str__(self) -> str:
        return f"{self.item_code} × {self.qty}"


# ── Goods Receipt Note ────────────────────────────────────────────────────────

class GoodsReceipt(BaseEntity):
    """
    Physical receipt of goods against a PO — creates a StockEntry on submit (§6.7).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="goods_receipts"
    )
    grn_number = models.CharField(max_length=50, blank=True, db_index=True)
    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    posting_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.TextField(blank=True)
    # After submission, the StockEntry created is soft-linked here
    stock_entry_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_goods_receipts"
        verbose_name = "Goods Receipt Note"

    def __str__(self) -> str:
        return self.grn_number or f"GRN-{self.pk}"


class GoodsReceiptItem(BaseEntity):
    """Line item on a GoodsReceipt."""

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="items")
    po_item = models.ForeignKey(
        PurchaseOrderItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="receipt_items",
    )
    item_id = models.UUIDField(db_index=True)
    # Soft link to product_catalogue.Product (UUID only, no FK)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    warehouse_id = models.UUIDField(db_index=True)   # target warehouse (soft)
    warehouse_code = models.CharField(max_length=20)
    batch_no = models.CharField(max_length=100, blank=True)
    serial_nos = models.TextField(blank=True, help_text="Newline-separated serial numbers")
    accepted_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    rejected_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_goods_receipt_items"

    def __str__(self) -> str:
        return f"{self.item_code} × {self.qty}"


# ── Landed Cost ───────────────────────────────────────────────────────────────

class LandedCost(BaseEntity):
    """
    Allocates additional costs (freight, duty, insurance) across a GRN (§6.7).
    """

    class AllocationMethod(models.TextChoices):
        BY_QTY = "by_qty", "By Quantity"
        BY_AMOUNT = "by_amount", "By Amount"
        BY_WEIGHT = "by_weight", "By Weight"
        EQUAL = "equal", "Equal Distribution"

    landed_cost_number = models.CharField(max_length=50, blank=True, db_index=True)
    goods_receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.PROTECT, related_name="landed_costs"
    )
    posting_date = models.DateField()
    allocation_method = models.CharField(
        max_length=20, choices=AllocationMethod.choices, default=AllocationMethod.BY_AMOUNT
    )
    total_taxes_and_charges = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    is_posted = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_landed_costs"
        verbose_name = "Landed Cost"

    def __str__(self) -> str:
        return self.landed_cost_number or f"LC-{self.pk}"


class LandedCostCharge(BaseEntity):
    """One charge type within a LandedCost (freight, duty, insurance)."""

    CHARGE_TYPES = [
        ("freight", "Freight"),
        ("insurance", "Insurance"),
        ("duty", "Customs Duty"),
        ("handling", "Handling"),
        ("other", "Other"),
    ]

    landed_cost = models.ForeignKey(LandedCost, on_delete=models.CASCADE, related_name="charges")
    charge_type = models.CharField(max_length=20, choices=CHARGE_TYPES)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    account_id = models.UUIDField(null=True, blank=True)   # GL account (soft)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_landed_cost_charges"

    def __str__(self) -> str:
        return f"{self.charge_type}: {self.amount}"


class LandedCostAllocation(BaseEntity):
    """Allocated portion of a LandedCost charge to one GRN line item."""

    landed_cost = models.ForeignKey(LandedCost, on_delete=models.CASCADE, related_name="allocations")
    grn_item = models.ForeignKey(
        GoodsReceiptItem, on_delete=models.CASCADE, related_name="landed_cost_allocations"
    )
    allocated_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_landed_cost_allocations"


# ── Vendor Scorecard ──────────────────────────────────────────────────────────

class VendorScorecard(BaseEntity):
    """
    Period-level vendor performance scorecard (§6.7).
    Tracks on-time delivery, quality/rejection, and price competitiveness.
    """

    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    period_start = models.DateField()
    period_end = models.DateField()
    # On-time delivery
    total_pos = models.PositiveIntegerField(default=0)
    on_time_pos = models.PositiveIntegerField(default=0)
    on_time_delivery_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Quality
    total_received_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    rejected_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    quality_rejection_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Price competitiveness (vs. average market rate or budget)
    price_variance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Composite score (0–100)
    composite_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_vendor_scorecards"
        verbose_name = "Vendor Scorecard"
        unique_together = [("vendor_id", "period_start", "period_end")]

    def __str__(self) -> str:
        return f"{self.vendor_name} [{self.period_start}–{self.period_end}]"


# ── Supplier Qualification ────────────────────────────────────────────────────

class SupplierQualification(BaseEntity):
    """
    Pre-engagement supplier qualification & onboarding workflow (§6.7).
    New → Under Review → Qualified | Disqualified.
    """

    class Status(models.TextChoices):
        NEW = "new", "New Application"
        UNDER_REVIEW = "under_review", "Under Review"
        ADDITIONAL_INFO = "additional_info", "Additional Info Requested"
        QUALIFIED = "qualified", "Qualified"
        DISQUALIFIED = "disqualified", "Disqualified"

    vendor_id = models.UUIDField(null=True, blank=True, db_index=True)   # set after approval
    vendor_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=150)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    tax_registration_no = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    qualification_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    # Document checklist flags
    has_tax_cert = models.BooleanField(default=False)
    has_insurance_cert = models.BooleanField(default=False)
    has_bank_details = models.BooleanField(default=False)
    esg_questionnaire_completed = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_supplier_qualifications"
        verbose_name = "Supplier Qualification"

    def __str__(self) -> str:
        return f"{self.vendor_name} ({self.status})"


# ── Purchase Return ───────────────────────────────────────────────────────────

class PurchaseReturn(BaseEntity):
    """
    Return of goods to supplier with debit note generation (§6.7).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    return_number = models.CharField(max_length=50, blank=True, db_index=True)
    goods_receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.PROTECT, related_name="returns"
    )
    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    posting_date = models.DateField()
    return_reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Soft link to AP debit note created in Accounting
    debit_note_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_returns"
        verbose_name = "Purchase Return"

    def __str__(self) -> str:
        return self.return_number or f"PRN-{self.pk}"


class PurchaseReturnItem(BaseEntity):
    """Line item on a PurchaseReturn."""

    purchase_return = models.ForeignKey(
        PurchaseReturn, on_delete=models.CASCADE, related_name="items"
    )
    grn_item = models.ForeignKey(
        GoodsReceiptItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="return_items",
    )
    item_id = models.UUIDField(db_index=True)
    # Soft link to product_catalogue.Product (UUID only, no FK)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    warehouse_id = models.UUIDField(db_index=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "purchasing_return_items"

    def __str__(self) -> str:
        return f"{self.item_code} × {self.qty}"
