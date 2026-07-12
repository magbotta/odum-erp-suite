"""
Government models (§7).
Tendering (OCDS), Permitting/Licensing, GASB Fund Accounting, Grants, 311/Cases, FOIA.
Extends: Purchasing (tendering), Accounting (fund accounting), Website (citizen portal).
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class GASBFund(BaseEntity):
    """
    A GASB-compliant governmental fund (General, Special Revenue, Debt Service,
    Capital Projects, Permanent) with encumbrance / budgetary-control fields (§7).
    """

    class FundType(models.TextChoices):
        GENERAL = "general", "General Fund"
        SPECIAL_REVENUE = "special_revenue", "Special Revenue"
        DEBT_SERVICE = "debt_service", "Debt Service"
        CAPITAL_PROJECTS = "capital_projects", "Capital Projects"
        PERMANENT = "permanent", "Permanent"
        ENTERPRISE = "enterprise", "Enterprise"
        INTERNAL_SERVICE = "internal_service", "Internal Service"

    name = models.CharField(max_length=255)
    fund_number = models.CharField(max_length=20, blank=True, db_index=True)
    fund_type = models.CharField(max_length=25, choices=FundType.choices)
    fiscal_year = models.PositiveSmallIntegerField()
    appropriated_budget = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    encumbered_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    expended_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    available_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)
    # Cross-app: Accounting cost center
    cost_center_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_gasb_funds"
        verbose_name = "GASB Fund"

    def __str__(self) -> str:
        return f"{self.fund_number} — {self.name}"


class Tender(BaseEntity):
    """
    A public procurement tender / RFP with OCDS (Open Contracting Data Standard) fields (§7).
    Extends Purchasing's RFx framework rather than building a separate bidding mechanism.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SUBMISSIONS_OPEN = "submissions_open", "Submissions Open"
        EVALUATION = "evaluation", "Under Evaluation"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"

    class ProcurementMethod(models.TextChoices):
        OPEN = "open", "Open Tender"
        RESTRICTED = "restricted", "Restricted / Selective"
        DIRECT = "direct", "Direct Award"
        FRAMEWORK = "framework", "Framework Agreement"

    tender_number = models.CharField(max_length=50, blank=True, db_index=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    procurement_method = models.CharField(
        max_length=20, choices=ProcurementMethod.choices, default=ProcurementMethod.OPEN
    )
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL, related_name="tenders"
    )
    estimated_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    publication_date = models.DateField(null=True, blank=True)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    award_date = models.DateField(null=True, blank=True)
    # OCDS: Open Contracting Data Standard ID
    ocds_ocid = models.CharField(max_length=255, blank=True, db_index=True,
                                  help_text="OCDS Open Contracting Identifier")
    awarded_vendor_id = models.UUIDField(null=True, blank=True)
    awarded_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "gov_tenders"

    def __str__(self) -> str:
        return f"{self.tender_number} — {self.title}"


class TenderBid(BaseEntity):
    """A vendor submission / bid against a Tender (§7)."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        UNDER_EVALUATION = "under_evaluation", "Under Evaluation"
        SHORTLISTED = "shortlisted", "Shortlisted"
        AWARDED = "awarded", "Awarded"
        REJECTED = "rejected", "Rejected"

    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="bids")
    vendor_id = models.UUIDField(db_index=True)
    vendor_name = models.CharField(max_length=255)
    bid_amount = models.DecimalField(max_digits=19, decimal_places=4)
    submission_date = models.DateTimeField()
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.RECEIVED)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    financial_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    evaluation_notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_tender_bids"

    def __str__(self) -> str:
        return f"{self.tender} — {self.vendor_name}"


class Permit(BaseEntity):
    """A government-issued permit (building, business license, environmental, etc.) (§7)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft Application"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        ISSUED = "issued", "Issued"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"
        REJECTED = "rejected", "Rejected"

    permit_number = models.CharField(max_length=50, blank=True, db_index=True)
    permit_type = models.CharField(max_length=100)
    applicant_name = models.CharField(max_length=255)
    applicant_crm_id = models.UUIDField(null=True, blank=True)
    property_address = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    application_date = models.DateField(null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    reviewing_officer_id = models.UUIDField(null=True, blank=True)
    inspection_required = models.BooleanField(default=False)
    inspection_passed = models.BooleanField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_permits"

    def __str__(self) -> str:
        return f"{self.permit_number} — {self.permit_type}"


class CitizenServiceRequest(BaseEntity):
    """
    A 311-style citizen service request (pothole, streetlight, noise complaint, etc.) (§7).
    """

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        EMERGENCY = "emergency", "Emergency"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    request_number = models.CharField(max_length=50, blank=True, db_index=True)
    service_type = models.CharField(max_length=150)
    description = models.TextField()
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.NORMAL
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    # Citizen reporter (may be anonymous)
    reporter_name = models.CharField(max_length=255, blank=True)
    reporter_email = models.EmailField(blank=True)
    reporter_phone = models.CharField(max_length=32, blank=True)
    location_address = models.TextField(blank=True)
    location_geojson = models.JSONField(null=True, blank=True)
    assigned_department = models.CharField(max_length=150, blank=True)
    assigned_to_employee_id = models.UUIDField(null=True, blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_citizen_service_requests"

    def __str__(self) -> str:
        return f"{self.request_number} — {self.service_type}"


class FOIARequest(BaseEntity):
    """A Freedom of Information Act (public records) request (§7)."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        IN_REVIEW = "in_review", "In Review"
        AWAITING_INFO = "awaiting_info", "Awaiting Additional Information"
        FULFILLED = "fulfilled", "Fulfilled"
        DENIED = "denied", "Denied"
        APPEALED = "appealed", "Under Appeal"

    request_number = models.CharField(max_length=50, blank=True, db_index=True)
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField(blank=True)
    description = models.TextField()
    records_requested = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    received_date = models.DateField()
    due_date = models.DateField(null=True, blank=True,
                                help_text="Statutory response deadline")
    fulfilled_date = models.DateField(null=True, blank=True)
    denial_reason = models.TextField(blank=True)
    assigned_to_employee_id = models.UUIDField(null=True, blank=True)
    fee_waived = models.BooleanField(default=False)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "gov_foia_requests"
        verbose_name = "FOIA Request"

    def __str__(self) -> str:
        return f"{self.request_number} — {self.requester_name}"
