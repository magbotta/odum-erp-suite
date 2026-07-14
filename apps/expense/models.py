"""Expense & Travel models (§6.11).

Covers: expense categories, policies, claims (with line items and policy-
violation flagging), travel requests, mileage logs, and corporate card
reconciliation.  Cross-app references (Employee, CostCenter, Project,
ChartOfAccount) are soft UUID links — never Django ForeignKeys across app
boundaries.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


# ── Category & Policy ────────────────────────────────────────────────────────

class ExpenseCategory(BaseEntity):
    """A named expense type with per-diem and receipt-threshold policy defaults."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    daily_limit = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Max per-diem spend for this category (0 = no limit)",
    )
    per_claim_limit = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Max single-expense amount (0 = no limit)",
    )
    requires_receipt_above = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Receipt required when expense exceeds this amount",
    )
    is_mileage = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Cross-app: GL account to debit when posting
    gl_account_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_categories"
        verbose_name_plural = "Expense Categories"

    def __str__(self) -> str:
        return self.name


class ExpensePolicy(BaseEntity):
    """Company-wide expense policy; drives policy-violation flagging on claims."""

    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    # Travel-specific caps
    max_hotel_rate_per_night = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Hotel rate cap (0 = no cap)",
    )
    max_flight_fare_class = models.CharField(
        max_length=20, blank=True,
        choices=[("economy", "Economy"), ("business", "Business"), ("first", "First")],
        default="economy",
    )
    mileage_rate_per_km = models.DecimalField(
        max_digits=10, decimal_places=4, default=0,
    )

    class Meta(BaseEntity.Meta):
        db_table = "expense_policies"
        verbose_name_plural = "Expense Policies"

    def __str__(self) -> str:
        return self.name


class ExpensePolicyRule(BaseEntity):
    """Per-category override inside a policy (overrides ExpenseCategory defaults)."""

    policy = models.ForeignKey(ExpensePolicy, on_delete=models.CASCADE, related_name="rules")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="policy_rules")
    daily_limit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    per_claim_limit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    requires_receipt = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_policy_rules"
        unique_together = [("policy", "category")]

    def __str__(self) -> str:
        return "{} / {}".format(self.policy, self.category)


# ── Expense Claim ────────────────────────────────────────────────────────────

class ExpenseClaim(BaseEntity):
    """An employee expense report covering one or more line-item expenses."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REIMBURSED = "reimbursed", "Reimbursed"
        CANCELLED = "cancelled", "Cancelled"

    class ReimbursementMethod(models.TextChoices):
        PAYROLL = "payroll", "Via Payroll"
        AP_PAYMENT = "ap_payment", "Direct AP Payment"

    claim_number = models.CharField(max_length=30, blank=True, db_index=True)
    # Cross-app: HRM Employee
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=200)
    from_date = models.DateField()
    to_date = models.DateField()
    purpose = models.CharField(max_length=255, blank=True)
    policy = models.ForeignKey(ExpensePolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    total_claimed_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_sanctioned_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    has_policy_violations = models.BooleanField(default=False)
    # Approval
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Reimbursement
    reimbursement_method = models.CharField(
        max_length=20, choices=ReimbursementMethod.choices,
        default=ReimbursementMethod.AP_PAYMENT,
    )
    reimbursed_at = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    # Cross-app allocations
    cost_center_id = models.UUIDField(null=True, blank=True)
    project_id = models.UUIDField(null=True, blank=True)
    # Back-link to travel request if this claim follows a trip
    travel_request_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_claims"

    def __str__(self) -> str:
        return self.claim_number or str(self.pk)


class ExpenseClaimLine(BaseEntity):
    """A single line item on an expense claim."""

    claim = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name="lines")
    expense_date = models.DateField()
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="claim_lines")
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    sanctioned_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    amount_in_company_currency = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    receipt_attached = models.BooleanField(default=False)
    receipt_file = models.CharField(max_length=500, blank=True)
    is_billable = models.BooleanField(default=False)
    # Cross-app: billable project
    project_id = models.UUIDField(null=True, blank=True)
    # Policy check results
    policy_violation = models.BooleanField(default=False)
    violation_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_claim_lines"
        ordering = ["expense_date"]

    def __str__(self) -> str:
        return "{} - {} {}".format(self.claim, self.category, self.amount)


# ── Travel Request ───────────────────────────────────────────────────────────

class TravelRequest(BaseEntity):
    """Pre-trip approval request (§6.11 travel booking & policy)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class BookingStatus(models.TextChoices):
        NOT_BOOKED = "not_booked", "Not Booked"
        PARTIALLY_BOOKED = "partially_booked", "Partially Booked"
        BOOKED = "booked", "Booked"

    request_number = models.CharField(max_length=30, blank=True, db_index=True)
    # Cross-app: HRM Employee
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=255)
    destination = models.CharField(max_length=200)
    from_date = models.DateField()
    to_date = models.DateField()
    estimated_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    policy = models.ForeignKey(ExpensePolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="travel_requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    booking_status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.NOT_BOOKED,
    )
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Back-link to resulting expense claim after travel completes
    expense_claim_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_travel_requests"

    def __str__(self) -> str:
        return self.request_number or str(self.pk)


class TravelItinerary(BaseEntity):
    """A single flight/hotel/car segment within a travel request."""

    class SegmentType(models.TextChoices):
        FLIGHT = "flight", "Flight"
        HOTEL = "hotel", "Hotel"
        TRAIN = "train", "Train"
        CAR_RENTAL = "car_rental", "Car Rental"
        OTHER = "other", "Other"

    travel_request = models.ForeignKey(TravelRequest, on_delete=models.CASCADE, related_name="itinerary")
    segment_type = models.CharField(max_length=20, choices=SegmentType.choices)
    description = models.CharField(max_length=255)
    from_date = models.DateField()
    to_date = models.DateField()
    vendor = models.CharField(max_length=150, blank=True)
    booking_ref = models.CharField(max_length=100, blank=True)
    cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    policy_compliant = models.BooleanField(default=True)
    violation_note = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_travel_itineraries"
        ordering = ["from_date"]

    def __str__(self) -> str:
        return "{} {} {}".format(self.travel_request, self.segment_type, self.from_date)


# ── Mileage ──────────────────────────────────────────────────────────────────

class MileageRate(BaseEntity):
    """Configurable reimbursement rate per distance unit (§6.11 mileage tracking)."""

    class VehicleType(models.TextChoices):
        CAR = "car", "Car"
        MOTORCYCLE = "motorcycle", "Motorcycle"
        BICYCLE = "bicycle", "Bicycle"
        OTHER = "other", "Other"

    name = models.CharField(max_length=100)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.CAR)
    rate_per_km = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    rate_per_mile = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_mileage_rates"

    def __str__(self) -> str:
        return "{} ({})".format(self.name, self.vehicle_type)


class MileageLog(BaseEntity):
    """A single mileage trip logged by an employee."""

    claim = models.ForeignKey(
        ExpenseClaim, null=True, blank=True, on_delete=models.SET_NULL, related_name="mileage_logs",
    )
    # Cross-app: HRM Employee
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=200)
    trip_date = models.DateField()
    from_location = models.CharField(max_length=255)
    to_location = models.CharField(max_length=255)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    distance_miles = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mileage_rate = models.ForeignKey(
        MileageRate, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs",
    )
    reimbursable_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    purpose = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_mileage_logs"
        ordering = ["-trip_date"]

    def __str__(self) -> str:
        return "{} → {} on {}".format(self.from_location, self.to_location, self.trip_date)


# ── Corporate Card ───────────────────────────────────────────────────────────

class CorporateCard(BaseEntity):
    """An employee-assigned corporate or purchase card."""

    class CardNetwork(models.TextChoices):
        VISA = "visa", "Visa"
        MASTERCARD = "mastercard", "Mastercard"
        AMEX = "amex", "Amex"
        OTHER = "other", "Other"

    class CardType(models.TextChoices):
        CORPORATE = "corporate", "Corporate"
        PURCHASE = "purchase", "Purchase"
        VIRTUAL = "virtual", "Virtual"

    # Cross-app: HRM Employee
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=200)
    card_number_last4 = models.CharField(max_length=4)
    card_network = models.CharField(max_length=20, choices=CardNetwork.choices, default=CardNetwork.VISA)
    card_type = models.CharField(max_length=20, choices=CardType.choices, default=CardType.CORPORATE)
    credit_limit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_corporate_cards"

    def __str__(self) -> str:
        return "{} *{}".format(self.employee_name, self.card_number_last4)


class CorporateCardStatement(BaseEntity):
    """A monthly card statement imported for reconciliation."""

    class Status(models.TextChoices):
        IMPORTED = "imported", "Imported"
        RECONCILED = "reconciled", "Reconciled"

    card = models.ForeignKey(CorporateCard, on_delete=models.CASCADE, related_name="statements")
    statement_period = models.CharField(max_length=20, help_text="e.g. 2025-06")
    from_date = models.DateField()
    to_date = models.DateField()
    total_charges = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IMPORTED)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta(BaseEntity.Meta):
        db_table = "expense_corporate_card_statements"

    def __str__(self) -> str:
        return "{} {}".format(self.card, self.statement_period)


class CorporateCardCharge(BaseEntity):
    """A single charge on a corporate card statement."""

    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        MATCHED = "matched", "Matched"
        DISPUTED = "disputed", "Disputed"

    statement = models.ForeignKey(CorporateCardStatement, on_delete=models.CASCADE, related_name="charges")
    charge_date = models.DateField()
    merchant_name = models.CharField(max_length=200)
    merchant_category = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED, db_index=True)
    # Soft ref to the matched expense claim line
    matched_claim_line_id = models.UUIDField(null=True, blank=True)
    auto_matched = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "expense_corporate_card_charges"
        ordering = ["-charge_date"]

    def __str__(self) -> str:
        return "{} {} {}".format(self.charge_date, self.merchant_name, self.amount)
