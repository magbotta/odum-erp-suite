"""CRM models: Account, Contact, Lead, Opportunity, Activity, Pipeline."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Account(BaseEntity):
    """A company or organization. The top-level CRM entity (§6.3)."""

    class Industry(models.TextChoices):
        TECHNOLOGY = "technology", "Technology"
        FINANCE = "finance", "Finance"
        HEALTHCARE = "healthcare", "Healthcare"
        MANUFACTURING = "manufacturing", "Manufacturing"
        RETAIL = "retail", "Retail"
        EDUCATION = "education", "Education"
        GOVERNMENT = "government", "Government"
        OTHER = "other", "Other"

    name = models.CharField(max_length=255, db_index=True)
    industry = models.CharField(max_length=50, choices=Industry.choices, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    parent_account = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subsidiaries"
    )
    annual_revenue = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    employee_count = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owned_accounts",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_accounts"
        verbose_name = "Account"
        verbose_name_plural = "Accounts"

    def __str__(self) -> str:
        return self.name


class Contact(BaseEntity):
    """A person associated with an Account (§6.3)."""

    class LeadSource(models.TextChoices):
        WEBSITE = "website", "Website"
        REFERRAL = "referral", "Referral"
        COLD_OUTREACH = "cold_outreach", "Cold Outreach"
        EVENT = "event", "Event"
        ADVERTISEMENT = "advertisement", "Advertisement"
        OTHER = "other", "Other"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    mobile = models.CharField(max_length=32, blank=True)
    title = models.CharField(max_length=100, blank=True, help_text="Job title")
    department = models.CharField(max_length=100, blank=True)
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts"
    )
    lead_source = models.CharField(max_length=20, choices=LeadSource.choices, blank=True)
    do_not_contact = models.BooleanField(default=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owned_contacts",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_contacts"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Lead(BaseEntity):
    """An unqualified inbound or outbound prospect (§6.3)."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        WORKING = "working", "Working"
        NURTURING = "nurturing", "Nurturing"
        CONVERTED = "converted", "Converted"
        DISQUALIFIED = "disqualified", "Disqualified"

    class LeadSource(models.TextChoices):
        WEBSITE = "website", "Website"
        REFERRAL = "referral", "Referral"
        COLD_OUTREACH = "cold_outreach", "Cold Outreach"
        EVENT = "event", "Event"
        ADVERTISEMENT = "advertisement", "Advertisement"
        OTHER = "other", "Other"

    title = models.CharField(max_length=255, help_text="Lead subject / company name")
    contact_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    company = models.CharField(max_length=255, blank=True)
    lead_source = models.CharField(max_length=20, choices=LeadSource.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    score = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_leads",
    )
    # Set when a lead is converted to an Opportunity
    converted_to_opportunity_id = models.UUIDField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_leads"

    def __str__(self) -> str:
        return self.title


class Pipeline(BaseEntity):
    """A named sales pipeline with configurable stages."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "crm_pipelines"

    def __str__(self) -> str:
        return self.name


class PipelineStage(BaseEntity):
    """An ordered stage within a Pipeline."""

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=100)
    sequence = models.PositiveIntegerField(default=0)
    probability = models.IntegerField(default=0, help_text="Default win probability %")
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "crm_pipeline_stages"
        ordering = ["pipeline", "sequence"]

    def __str__(self) -> str:
        return f"{self.pipeline.name} → {self.name}"


class Opportunity(BaseEntity):
    """A qualified sales opportunity (§6.3)."""

    class ForecastCategory(models.TextChoices):
        PIPELINE = "pipeline", "Pipeline"
        BEST_CASE = "best_case", "Best Case"
        COMMIT = "commit", "Commit"
        CLOSED_WON = "closed_won", "Closed Won"
        CLOSED_LOST = "closed_lost", "Closed Lost"

    name = models.CharField(max_length=255)
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities"
    )
    primary_contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities"
    )
    pipeline = models.ForeignKey(
        Pipeline, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities"
    )
    stage = models.ForeignKey(
        PipelineStage, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities"
    )
    amount = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    probability = models.IntegerField(default=0, help_text="Win probability 0–100")
    expected_close_date = models.DateField(null=True, blank=True)
    forecast_category = models.CharField(
        max_length=20, choices=ForecastCategory.choices, default=ForecastCategory.PIPELINE
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_opportunities",
    )
    lead = models.ForeignKey(
        Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities",
        help_text="Source lead if converted",
    )
    win_reason = models.TextField(blank=True)
    loss_reason = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_opportunities"
        verbose_name_plural = "Opportunities"

    def __str__(self) -> str:
        return self.name


class Activity(BaseEntity):
    """A logged call, email, meeting, task, or note (§6.3)."""

    class Type(models.TextChoices):
        CALL = "call", "Call"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        TASK = "task", "Task"
        NOTE = "note", "Note"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    activity_type = models.CharField(max_length=20, choices=Type.choices)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    due_date = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)

    # Polymorphic parent — link to account, contact, or opportunity (not all three required)
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities"
    )
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities"
    )
    opportunity = models.ForeignKey(
        Opportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_activities",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_activities"
        verbose_name_plural = "Activities"

    def __str__(self) -> str:
        return f"[{self.activity_type}] {self.subject}"
