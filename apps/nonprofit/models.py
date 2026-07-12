"""
Nonprofit Management models (§7).
Extends CRM (donors=Contacts/Accounts), Accounting (fund accounting), HRM (volunteers).
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Fund(BaseEntity):
    """
    An accounting fund with a restriction type (restricted/unrestricted/temp-restricted).
    Extends Accounting's GL structure rather than duplicating it (§7).
    """

    class RestrictionType(models.TextChoices):
        UNRESTRICTED = "unrestricted", "Unrestricted"
        TEMPORARILY_RESTRICTED = "temp_restricted", "Temporarily Restricted"
        PERMANENTLY_RESTRICTED = "permanently_restricted", "Permanently Restricted"

    name = models.CharField(max_length=255)
    fund_code = models.CharField(max_length=20, blank=True, db_index=True)
    restriction_type = models.CharField(
        max_length=30, choices=RestrictionType.choices, default=RestrictionType.UNRESTRICTED
    )
    purpose = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    target_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Cross-app: Accounting cost center / GL tag for this fund
    cost_center_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_funds"

    def __str__(self) -> str:
        return self.name


class Donor(BaseEntity):
    """
    A donor — extends the CRM Contact/Account model via crm_contact_id
    rather than duplicating the contact concept (§7).
    """

    class DonorType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        CORPORATE = "corporate", "Corporate"
        FOUNDATION = "foundation", "Foundation"
        GOVERNMENT = "government", "Government"

    # Cross-app: CRM Contact or Account UUID
    crm_contact_id = models.UUIDField(db_index=True)
    donor_number = models.CharField(max_length=50, blank=True, unique=True)
    donor_type = models.CharField(
        max_length=20, choices=DonorType.choices, default=DonorType.INDIVIDUAL
    )
    major_donor = models.BooleanField(default=False)
    solicitor_employee_id = models.UUIDField(null=True, blank=True)
    first_gift_date = models.DateField(null=True, blank=True)
    last_gift_date = models.DateField(null=True, blank=True)
    total_giving = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Moves management stage (analogue of CRM pipeline stage)
    moves_stage = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_donors"

    def __str__(self) -> str:
        return self.donor_number or str(self.crm_contact_id)


class Donation(BaseEntity):
    """A single gift from a Donor to one or more Funds."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        CARD = "card", "Card"
        WIRE = "wire", "Wire / ACH"
        STOCK = "stock", "Stock / Securities"
        IN_KIND = "in_kind", "In-Kind"
        MOBILE_MONEY = "mobile_money", "Mobile Money"

    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        RECEIVED = "received", "Received"
        RECEIPTED = "receipted", "Receipted"
        FAILED = "failed", "Failed"

    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="donations")
    fund = models.ForeignKey(
        Fund, null=True, blank=True, on_delete=models.SET_NULL, related_name="donations"
    )
    donation_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLEDGED)
    is_recurring = models.BooleanField(default=False)
    campaign = models.ForeignKey(
        "FundraisingCampaign", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="donations",
    )
    receipt_number = models.CharField(max_length=50, blank=True)
    # Cross-app: Accounting Payment
    accounting_payment_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_donations"

    def __str__(self) -> str:
        return f"{self.donor} — {self.amount} {self.currency} [{self.donation_date}]"


class FundraisingCampaign(BaseEntity):
    """A multi-channel fundraising campaign (§7)."""

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=255)
    campaign_code = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNING)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    goal_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    raised_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_campaigns"

    def __str__(self) -> str:
        return self.name


class Grant(BaseEntity):
    """A grant received from (or applied to) a foundation / government body (§7)."""

    class Status(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        APPLIED = "applied", "Applied"
        AWARDED = "awarded", "Awarded"
        ACTIVE = "active", "Active (Reporting)"
        CLOSED = "closed", "Closed"
        DECLINED = "declined", "Declined"

    name = models.CharField(max_length=255)
    grant_number = models.CharField(max_length=50, blank=True)
    grantor_name = models.CharField(max_length=255)
    fund = models.ForeignKey(
        Fund, null=True, blank=True, on_delete=models.SET_NULL, related_name="grants"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROSPECT)
    applied_date = models.DateField(null=True, blank=True)
    award_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    amount_requested = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount_awarded = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount_spent = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    next_report_due = models.DateField(null=True, blank=True)
    purpose = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_grants"

    def __str__(self) -> str:
        return self.name


class Beneficiary(BaseEntity):
    """A program beneficiary / service recipient tracked for outcomes (§7)."""

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    registration_date = models.DateField(null=True, blank=True)
    program_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_beneficiaries"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Volunteer(BaseEntity):
    """
    A volunteer — extends HRM via hrm_employee_id (if staff) or standalone (§7).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    skills = models.TextField(blank=True)
    availability = models.TextField(blank=True)
    total_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Link to HRM employee record if volunteer is also on payroll
    hrm_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "nonprofit_volunteers"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"
