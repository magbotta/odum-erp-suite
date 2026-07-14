"""
Government models (§7 / §7.9).

Covers:
  - GASB fund accounting + encumbrance/budgetary control
  - Tendering with OCDS publication
  - Permitting / licensing case workflow
  - Grants management (grantor + grantee)
  - 311/citizen case management
  - FOIA / public records
  - Property/parcel register with geopoint + geofence (stored as GeoJSON in JSONB)
  - Revenue billing: property rates, permit fees, market tolls, service charges
  - GovernmentRevenueBill (the payable document routed to the Payment Gateway)
  - GovernmentPaymentReceipt (generated after a confirmed PaymentEvent)
  - LocalLevy (market tolls, lorry-park fees, recurring local levies)
  - PublicInfrastructureAsset (MMDA public assets)
  - OCDSRelease (Open Contracting Data Standard publication log)

Extends: Purchasing (tendering), Accounting (fund accounting), Website (citizen portal).
All cross-app references are UUID soft-links — no ForeignKeys to other apps.
"""
from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone

from core.metadata_engine.base_entity import BaseEntity


# ---------------------------------------------------------------------------
# GASB Fund Accounting
# ---------------------------------------------------------------------------

class GASBFund(BaseEntity):
    """
    A GASB-compliant governmental fund (General, Special Revenue, Debt Service,
    Capital Projects, Permanent) with encumbrance / budgetary-control fields.
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
    description = models.TextField(blank=True)
    cost_center_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_gasb_funds"
        verbose_name = "GASB Fund"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.fund_number, self.name)


class BudgetaryControl(BaseEntity):
    """
    GASB encumbrance/budgetary control entry — tracks commitments against a GASB fund
    before the actual expenditure is recorded. Full lifecycle:
    pre-encumbrance (requisition) → encumbrance (PO) → expenditure (invoice).
    """

    class EntryType(models.TextChoices):
        PRE_ENCUMBRANCE = "pre_encumbrance", "Pre-Encumbrance (Requisition)"
        ENCUMBRANCE = "encumbrance", "Encumbrance (Purchase Order)"
        EXPENDITURE = "expenditure", "Expenditure (Invoice/Payment)"
        BUDGET_AMENDMENT = "budget_amendment", "Budget Amendment"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        LIQUIDATED = "liquidated", "Liquidated"
        CANCELLED = "cancelled", "Cancelled"

    entry_number = models.CharField(max_length=50, blank=True, db_index=True)
    gasb_fund_id = models.UUIDField(null=True, blank=True, db_index=True)
    entry_type = models.CharField(max_length=25, choices=EntryType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    description = models.TextField(blank=True)
    entry_date = models.DateField()
    source_document_type = models.CharField(
        max_length=50, blank=True,
        help_text="purchase_order, requisition, invoice",
    )
    source_document_id = models.UUIDField(null=True, blank=True)
    liquidates_entry_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_budgetary_control"
        verbose_name = "Budgetary Control Entry"

    def __str__(self) -> str:
        return "{0} — {1} ({2})".format(self.entry_number, self.entry_type, self.amount)


# ---------------------------------------------------------------------------
# Tendering / Procurement
# ---------------------------------------------------------------------------

class Tender(BaseEntity):
    """
    A public procurement tender / RFP with OCDS (Open Contracting Data Standard) fields.
    Extends Purchasing's RFx framework — not a separate bidding mechanism.
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
        max_length=20, choices=ProcurementMethod.choices,
        default=ProcurementMethod.OPEN,
    )
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL, related_name="tenders"
    )
    estimated_value = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="GHS")
    publication_date = models.DateField(null=True, blank=True)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    award_date = models.DateField(null=True, blank=True)
    ocds_ocid = models.CharField(
        max_length=255, blank=True, db_index=True,
        help_text="OCDS Open Contracting Identifier",
    )
    awarded_vendor_id = models.UUIDField(null=True, blank=True)
    awarded_vendor_name = models.CharField(max_length=255, blank=True)
    awarded_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    eligibility_criteria = models.TextField(blank=True)
    technical_requirements = models.TextField(blank=True)
    contact_person = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_tenders"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.tender_number, self.title)


class TenderEvaluationCriteria(BaseEntity):
    """Weighted scoring criteria for evaluating bids on a tender."""

    tender = models.ForeignKey(
        Tender, on_delete=models.CASCADE, related_name="evaluation_criteria"
    )
    criterion_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    weight_pct = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Weight as percentage of total score",
    )
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)

    class Meta(BaseEntity.Meta):
        db_table = "gov_tender_evaluation_criteria"

    def __str__(self) -> str:
        return "{0} — {1} ({2}%)".format(self.tender, self.criterion_name, self.weight_pct)


class TenderBid(BaseEntity):
    """A vendor submission / bid against a Tender."""

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
    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.RECEIVED
    )
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    financial_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    evaluation_notes = models.TextField(blank=True)
    has_tax_clearance = models.BooleanField(default=False)
    has_company_registration = models.BooleanField(default=False)
    disqualification_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_tender_bids"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.tender, self.vendor_name)


class OCDSRelease(BaseEntity):
    """
    An OCDS (Open Contracting Data Standard) publication log entry.
    One release per stage change on a Tender (Planning, Tender, Award, Contract, Implementation).
    The full JSON OCDS release package is stored in release_json for export/API publication.
    """

    class Tag(models.TextChoices):
        PLANNING = "planning", "Planning"
        TENDER = "tender", "Tender"
        AWARD = "award", "Award"
        CONTRACT = "contract", "Contract"
        IMPLEMENTATION = "implementation", "Implementation"
        CANCELLATION = "cancellation", "Cancellation"

    tender = models.ForeignKey(
        Tender, on_delete=models.CASCADE, related_name="ocds_releases"
    )
    ocid = models.CharField(max_length=255, db_index=True)
    release_id = models.CharField(max_length=100, unique=True)
    tag = models.CharField(max_length=20, choices=Tag.choices)
    published_at = models.DateTimeField(default=timezone.now)
    release_json = models.JSONField(
        default=dict,
        help_text="Full OCDS release package JSON, suitable for open data publication.",
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_ocds_releases"
        verbose_name = "OCDS Release"

    def __str__(self) -> str:
        return "{0} / {1}".format(self.ocid, self.tag)


# ---------------------------------------------------------------------------
# Permitting / Licensing
# ---------------------------------------------------------------------------

class Permit(BaseEntity):
    """A government-issued permit (building, business license, environmental, etc.)."""

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
    fee_paid = models.BooleanField(default=False)
    reviewing_officer_id = models.UUIDField(null=True, blank=True)
    reviewing_officer_name = models.CharField(max_length=255, blank=True)
    review_deadline = models.DateField(null=True, blank=True)
    applicant_email = models.EmailField(blank=True)
    applicant_phone = models.CharField(max_length=32, blank=True)
    inspection_required = models.BooleanField(default=False)
    inspection_passed = models.BooleanField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    conditions = models.TextField(blank=True, help_text="Conditions attached to the permit")
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL, related_name="permits"
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_permits"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.permit_number, self.permit_type)


class PermitInspection(BaseEntity):
    """An inspection record linked to a permit application."""

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed / Requires Correction"
        WAIVED = "waived", "Waived"

    permit = models.ForeignKey(
        Permit, on_delete=models.CASCADE, related_name="inspections"
    )
    inspection_type = models.CharField(max_length=100)
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.PENDING
    )
    inspector_name = models.CharField(max_length=255, blank=True)
    inspector_employee_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    corrections_required = models.TextField(blank=True)
    reinspection_required = models.BooleanField(default=False)
    reinspection_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_permit_inspections"

    def __str__(self) -> str:
        return "{0} — {1} [{2}]".format(self.permit, self.inspection_type, self.outcome)


# ---------------------------------------------------------------------------
# Grants Management
# ---------------------------------------------------------------------------

class GrantApplication(BaseEntity):
    """
    A grant application — supports both grantor (government issuing grants) and
    grantee (government receiving grants) use cases.
    """

    class GrantType(models.TextChoices):
        ISSUED = "issued", "Issued (Grantor)"
        RECEIVED = "received", "Received (Grantee)"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ACTIVE = "active", "Active / Disbursing"
        CLOSED = "closed", "Closed"

    grant_number = models.CharField(max_length=50, blank=True, db_index=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    grant_type = models.CharField(
        max_length=10, choices=GrantType.choices, default=GrantType.RECEIVED
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="grant_applications",
    )
    counterpart_name = models.CharField(
        max_length=255, blank=True,
        help_text="Grantor (if received) or Grantee (if issued)",
    )
    counterpart_contact = models.EmailField(blank=True)
    requested_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    approved_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    disbursed_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="GHS")
    application_date = models.DateField(null=True, blank=True)
    award_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    reporting_requirements = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    program_officer_id = models.UUIDField(null=True, blank=True)
    program_officer_name = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_grant_applications"
        verbose_name = "Grant Application"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.grant_number, self.title)


# ---------------------------------------------------------------------------
# 311 Citizen Services + FOIA
# ---------------------------------------------------------------------------

class CitizenServiceRequest(BaseEntity):
    """A 311-style citizen service request (pothole, streetlight, noise, etc.)."""

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
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    reporter_name = models.CharField(max_length=255, blank=True)
    reporter_email = models.EmailField(blank=True)
    reporter_phone = models.CharField(max_length=32, blank=True)
    location_address = models.TextField(blank=True)
    location_geojson = models.JSONField(null=True, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    assigned_department = models.CharField(max_length=150, blank=True)
    assigned_to_employee_id = models.UUIDField(null=True, blank=True)
    assigned_to_name = models.CharField(max_length=255, blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)
    target_resolution_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    satisfaction_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1-5 citizen satisfaction rating"
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_citizen_service_requests"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.request_number, self.service_type)


class FOIARequest(BaseEntity):
    """A Freedom of Information Act (public records) request."""

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
    requester_phone = models.CharField(max_length=32, blank=True)
    requester_organization = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    records_requested = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    received_date = models.DateField()
    acknowledged_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(
        null=True, blank=True, help_text="Statutory response deadline"
    )
    fulfilled_date = models.DateField(null=True, blank=True)
    denial_reason = models.TextField(blank=True)
    denial_exemption = models.CharField(
        max_length=100, blank=True,
        help_text="e.g. FOIA Exemption (b)(6) — personal privacy",
    )
    assigned_to_employee_id = models.UUIDField(null=True, blank=True)
    fee_waived = models.BooleanField(default=False)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fee_paid = models.BooleanField(default=False)
    is_sensitive = models.BooleanField(
        default=False, help_text="Requires senior review before fulfillment"
    )
    response_notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_foia_requests"
        verbose_name = "FOIA Request"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.request_number, self.requester_name)


# ---------------------------------------------------------------------------
# Property / Parcel Register
# ---------------------------------------------------------------------------

class PropertyParcel(BaseEntity):
    """
    A rateable property/parcel in the MMDA's property register.
    The primary basis for property rate billing.

    Geo fields (geopoint, geofence) are stored as GeoJSON dicts in JSONField —
    the same PostGIS-backed approach used platform-wide (§5), queryable via
    the raw PostgreSQL GeoJSON operators or the AI copilot's geo-aware queries.
    """

    class PropertyUse(models.TextChoices):
        RESIDENTIAL = "residential", "Residential"
        COMMERCIAL = "commercial", "Commercial"
        INDUSTRIAL = "industrial", "Industrial"
        AGRICULTURAL = "agricultural", "Agricultural"
        MIXED_USE = "mixed_use", "Mixed Use"
        GOVERNMENT = "government", "Government / Institutional"
        VACANT = "vacant", "Vacant Land"

    class ValuationBasis(models.TextChoices):
        ANNUAL_VALUE = "annual_value", "Annual Rental Value"
        CAPITAL_VALUE = "capital_value", "Capital Market Value"
        REPLACEMENT_VALUE = "replacement_value", "Replacement Cost Value"
        AREA_BASED = "area_based", "Area-Based (per sqm)"

    parcel_number = models.CharField(max_length=80, unique=True, db_index=True)
    block_number = models.CharField(max_length=40, blank=True)
    plot_number = models.CharField(max_length=40, blank=True)
    street_address = models.TextField()
    ward = models.CharField(max_length=100, db_index=True)
    ward_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Geo: single centroid coordinate {type: "Point", coordinates: [lon, lat]}
    geopoint = models.JSONField(null=True, blank=True)
    # Geo: polygon boundary {type: "Polygon", coordinates: [...]}
    geofence = models.JSONField(null=True, blank=True)

    property_use = models.CharField(
        max_length=20, choices=PropertyUse.choices, default=PropertyUse.RESIDENTIAL
    )
    total_area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    structure_area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    valuation_basis = models.CharField(
        max_length=20, choices=ValuationBasis.choices,
        default=ValuationBasis.ANNUAL_VALUE,
    )
    rateable_value = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="The assessed value on which the rate impost is applied.",
    )
    last_valuation_date = models.DateField(null=True, blank=True)
    next_valuation_due = models.DateField(null=True, blank=True)

    # Owner / occupier (payer)
    owner_name = models.CharField(max_length=255)
    owner_phone = models.CharField(max_length=32, blank=True)
    owner_email = models.EmailField(blank=True)
    owner_crm_id = models.UUIDField(null=True, blank=True)
    occupier_name = models.CharField(max_length=255, blank=True)
    occupier_phone = models.CharField(max_length=32, blank=True)
    # Rate payer: owner by default; overridden to occupier if so agreed
    rate_payer = models.CharField(
        max_length=10,
        choices=[("owner", "Owner"), ("occupier", "Occupier")],
        default="owner",
    )

    is_active = models.BooleanField(default=True)
    exemption_reason = models.CharField(
        max_length=255, blank=True,
        help_text="If set, this parcel is exempt from rates billing.",
    )
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="parcels",
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_property_parcels"
        verbose_name = "Property Parcel"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.parcel_number, self.street_address)


# ---------------------------------------------------------------------------
# Rate Impost (annual property rate rule)
# ---------------------------------------------------------------------------

class RateImpost(BaseEntity):
    """
    The annual property rate rule set by the Assembly.
    One row per fiscal_year × property_use × valuation_basis combination.
    The rate_pct is applied to PropertyParcel.rateable_value to derive the annual demand.
    """

    fiscal_year = models.PositiveSmallIntegerField(db_index=True)
    property_use = models.CharField(
        max_length=20,
        choices=PropertyParcel.PropertyUse.choices,
        default=PropertyParcel.PropertyUse.RESIDENTIAL,
    )
    valuation_basis = models.CharField(
        max_length=20, choices=PropertyParcel.ValuationBasis.choices
    )
    rate_pct = models.DecimalField(
        max_digits=7, decimal_places=4,
        help_text="Annual rate as a % of rateable value, e.g. 0.5 = 0.5%",
    )
    minimum_charge = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Minimum annual charge regardless of rateable value.",
    )
    penalty_rate_pct = models.DecimalField(
        max_digits=7, decimal_places=4, default=0,
        help_text="Additional % charged per dunning cycle on overdue bills.",
    )
    grace_period_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Days after due date before overdue status and penalty apply.",
    )
    approved_by = models.CharField(max_length=255, blank=True)
    effective_from = models.DateField()
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="rate_impostes",
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_rate_impostes"
        verbose_name = "Rate Impost"
        unique_together = [("fiscal_year", "property_use", "valuation_basis")]

    def __str__(self) -> str:
        return "FY{0} {1} @ {2}%".format(
            self.fiscal_year, self.property_use, self.rate_pct
        )


# ---------------------------------------------------------------------------
# Local Levies (market tolls, lorry-park fees, etc.)
# ---------------------------------------------------------------------------

class LocalLevy(BaseEntity):
    """
    A recurring or one-off local levy collected by the MMDA:
    market stalls, lorry-park fees, hawker licences, etc.
    Each levy definition specifies the charge schedule; GovernmentRevenueBill
    is generated from these for individual payers.
    """

    class FrequencyChoices(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"
        ONE_OFF = "one_off", "One-Off"

    name = models.CharField(max_length=255)
    levy_code = models.CharField(max_length=30, blank=True, unique=True, db_index=True)
    description = models.TextField(blank=True)
    frequency = models.CharField(
        max_length=15, choices=FrequencyChoices.choices, default=FrequencyChoices.MONTHLY
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="GHS")
    location = models.CharField(
        max_length=255, blank=True,
        help_text="Market name, lorry park name, or zone.",
    )
    is_active = models.BooleanField(default=True)
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="levies",
    )

    class Meta(BaseEntity.Meta):
        db_table = "gov_local_levies"
        verbose_name = "Local Levy"
        verbose_name_plural = "Local Levies"

    def __str__(self) -> str:
        return "{0} ({1})".format(self.name, self.frequency)


# ---------------------------------------------------------------------------
# Government Revenue Bill (the payable document)
# ---------------------------------------------------------------------------

class GovernmentRevenueBill(BaseEntity):
    """
    A payable demand / bill issued by the MMDA.

    Every revenue stream — property rate, permit fee, market toll,
    service charge — generates one of these.  This is what gets passed to
    the Payment Gateway: GovernmentRevenueBill is the payable_document_type.

    bill_type maps to revenue_type in PaymentEvent for IGF reporting.
    """

    class BillType(models.TextChoices):
        PROPERTY_RATE = "property_rate", "Property Rate"
        PERMIT_FEE = "permit_fee", "Permit / Licence Fee"
        MARKET_TOLL = "market_toll", "Market Toll / Local Levy"
        SERVICE_CHARGE = "service_charge", "Service Charge"
        FINES_PENALTIES = "fines_penalties", "Fines & Penalties"
        OTHER = "other", "Other IGF Revenue"

    class BillStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid in Full"
        OVERDUE = "overdue", "Overdue"
        ESCALATED = "escalated", "Escalated / Legal"
        CANCELLED = "cancelled", "Cancelled"
        WRITTEN_OFF = "written_off", "Written Off"

    bill_number = models.CharField(max_length=50, blank=True, db_index=True)
    bill_type = models.CharField(
        max_length=25, choices=BillType.choices, db_index=True
    )
    fiscal_year = models.PositiveSmallIntegerField(db_index=True)

    # Payer — UUID soft-link; name + phone denormalised for offline receipts
    payer_id = models.UUIDField(null=True, blank=True, db_index=True)
    payer_name = models.CharField(max_length=255)
    payer_phone = models.CharField(max_length=32, blank=True)
    payer_email = models.EmailField(blank=True)

    # Source document soft-links (nullable — depends on bill_type)
    parcel_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="PropertyParcel.id for property_rate bills.",
    )
    permit_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Permit.id for permit_fee bills.",
    )
    levy_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="LocalLevy.id for market_toll bills.",
    )

    # Amounts
    payable_amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    penalty_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="GHS")

    # Dates
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    grace_period_end = models.DateField(null=True, blank=True)
    overdue_since = models.DateField(null=True, blank=True)

    bill_status = models.CharField(
        max_length=20, choices=BillStatus.choices,
        default=BillStatus.UNPAID, db_index=True,
    )
    dunning_count = models.PositiveSmallIntegerField(
        default=0, help_text="Number of dunning notices dispatched."
    )

    description = models.TextField(blank=True)
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="revenue_bills",
    )
    # GL posting soft-link (set after journal entry created)
    journal_entry_id = models.CharField(max_length=36, blank=True, null=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_revenue_bills"
        verbose_name = "Government Revenue Bill"
        indexes = [
            models.Index(fields=["bill_type", "fiscal_year", "bill_status"],
                         name="gov_bill_type_fy_status_idx"),
            models.Index(fields=["parcel_id", "fiscal_year"],
                         name="gov_bill_parcel_fy_idx"),
        ]

    @property
    def outstanding_amount(self):
        return max(self.payable_amount + self.penalty_amount - self.paid_amount, 0)

    def __str__(self) -> str:
        return "{0} — {1} {2} {3}".format(
            self.bill_number, self.bill_type, self.payable_amount, self.currency
        )


# ---------------------------------------------------------------------------
# Government Payment Receipt
# ---------------------------------------------------------------------------

class GovernmentPaymentReceipt(BaseEntity):
    """
    Official receipt issued after a confirmed PaymentEvent against a GovernmentRevenueBill.
    One receipt per payment event (partial or full).
    """

    receipt_number = models.CharField(max_length=50, unique=True, db_index=True)
    # Soft-links — no FK to payment_gateway to avoid cross-core coupling
    payment_event_id = models.CharField(max_length=36, db_index=True)
    bill = models.ForeignKey(
        GovernmentRevenueBill, on_delete=models.PROTECT, related_name="receipts"
    )
    payer_name = models.CharField(max_length=255)
    payer_phone = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="GHS")
    channel = models.CharField(
        max_length=50,
        help_text="mtn_momo, airteltigo, vodafone_cash, cash, bank_transfer",
    )
    issued_at = models.DateTimeField(default=timezone.now)
    issued_by_employee_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_payment_receipts"
        verbose_name = "Government Payment Receipt"

    def __str__(self) -> str:
        return "{0} — {1} {2}".format(self.receipt_number, self.amount, self.currency)


# ---------------------------------------------------------------------------
# Public Infrastructure Asset
# ---------------------------------------------------------------------------

class PublicInfrastructureAsset(BaseEntity):
    """
    A public asset owned/maintained by the MMDA (road, drain, borehole,
    public toilet, community centre, market shed, etc.).
    Extends the asset tracking pattern from AssetManagement (§6.2) with
    public-sector fields: ward, maintenance responsibility, GPS location.
    """

    class AssetCategory(models.TextChoices):
        ROAD = "road", "Road / Street"
        DRAIN = "drain", "Drainage"
        WATER = "water", "Water / Borehole"
        MARKET = "market", "Market / Stall"
        TOILET = "toilet", "Public Toilet"
        PARK = "park", "Park / Garden"
        OFFICE = "office", "Office / Admin Building"
        COMMUNITY = "community", "Community Centre"
        OTHER = "other", "Other"

    class Condition(models.TextChoices):
        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"
        CRITICAL = "critical", "Critical"
        DECOMMISSIONED = "decommissioned", "Decommissioned"

    asset_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=AssetCategory.choices)
    description = models.TextField(blank=True)
    ward = models.CharField(max_length=100, db_index=True)
    ward_id = models.UUIDField(null=True, blank=True)
    location_address = models.TextField(blank=True)
    geopoint = models.JSONField(null=True, blank=True)
    geofence = models.JSONField(null=True, blank=True)
    condition = models.CharField(
        max_length=20, choices=Condition.choices, default=Condition.GOOD
    )
    construction_date = models.DateField(null=True, blank=True)
    last_inspection_date = models.DateField(null=True, blank=True)
    next_maintenance_due = models.DateField(null=True, blank=True)
    estimated_replacement_cost = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True
    )
    responsible_department = models.CharField(max_length=150, blank=True)
    gasb_fund = models.ForeignKey(
        GASBFund, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="infrastructure_assets",
    )
    # Link to AssetManagement.Asset for depreciation tracking (UUID soft-link)
    asset_management_asset_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "gov_public_infrastructure_assets"
        verbose_name = "Public Infrastructure Asset"

    def __str__(self) -> str:
        return "{0} — {1}".format(self.asset_code, self.name)
