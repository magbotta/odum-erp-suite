"""CRM models: Account, Contact, Lead, Opportunity, Activity, Pipeline, Quote, Case, Campaign, Territory."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.metadata_engine.base_entity import BaseEntity


class Territory(BaseEntity):
    """A geographic, vertical, or account-based sales territory (§6.3)."""

    name = models.CharField(max_length=150, db_index=True)
    description = models.TextField(blank=True)
    territory_type = models.CharField(
        max_length=20,
        choices=[("geographic", "Geographic"), ("vertical", "Vertical"), ("account", "Account-Based")],
        default="geographic",
    )
    parent_territory = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="sub_territories"
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="managed_territories",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_territories"
        verbose_name_plural = "Territories"

    def __str__(self) -> str:
        return self.name


class Account(BaseEntity):
    """A company or organization. Top-level CRM entity (§6.3)."""

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
    territory = models.ForeignKey(
        Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="accounts"
    )
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
    territory = models.ForeignKey(
        Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts"
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


class Campaign(BaseEntity):
    """A marketing campaign for UTM/source tracking on Leads (§6.3)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class CampaignType(models.TextChoices):
        EMAIL = "email", "Email"
        SOCIAL = "social", "Social Media"
        PPC = "ppc", "Pay-Per-Click"
        EVENT = "event", "Event"
        WEBINAR = "webinar", "Webinar"
        CONTENT = "content", "Content Marketing"
        OTHER = "other", "Other"

    name = models.CharField(max_length=255, db_index=True)
    campaign_type = models.CharField(max_length=20, choices=CampaignType.choices, default=CampaignType.EMAIL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    expected_revenue = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owned_campaigns",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_campaigns"

    def __str__(self) -> str:
        return self.name


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
    campaign = models.ForeignKey(
        Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
        help_text="Campaign that generated this lead",
    )
    territory = models.ForeignKey(
        Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_leads",
    )
    converted_to_opportunity_id = models.UUIDField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_leads"

    def __str__(self) -> str:
        return self.title


class Pipeline(BaseEntity):
    """A named sales pipeline with configurable stages (§6.3)."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "crm_pipelines"

    def __str__(self) -> str:
        return self.name


class PipelineStage(BaseEntity):
    """An ordered stage within a Pipeline (§6.3)."""

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


class Competitor(BaseEntity):
    """A competitor tracked against opportunities (§6.3)."""

    name = models.CharField(max_length=255, db_index=True)
    website = models.URLField(blank=True)
    strengths = models.TextField(blank=True)
    weaknesses = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_competitors"

    def __str__(self) -> str:
        return self.name


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
    territory = models.ForeignKey(
        Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_opportunities",
    )
    lead = models.ForeignKey(
        Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities",
        help_text="Source lead if converted",
    )
    competitors = models.ManyToManyField(
        Competitor, through="OpportunityCompetitor", blank=True, related_name="opportunities"
    )
    win_reason = models.TextField(blank=True)
    loss_reason = models.TextField(blank=True)
    description = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_opportunities"
        verbose_name_plural = "Opportunities"

    def __str__(self) -> str:
        return self.name

    @property
    def weighted_amount(self):
        if self.amount is None:
            return None
        return self.amount * self.probability / 100


class OpportunityCompetitor(BaseEntity):
    """Tracks which competitors are involved in an opportunity (§6.3)."""

    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="opportunity_competitors")
    competitor = models.ForeignKey(Competitor, on_delete=models.CASCADE, related_name="opportunity_links")
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_opportunity_competitors"
        unique_together = [("opportunity", "competitor")]


class OpportunityTeamMember(BaseEntity):
    """Team selling — multiple reps with split-credit on an opportunity (§6.3)."""

    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="team_members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opportunity_team_roles"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g. Account Executive, SE, BDR")
    credit_split = models.IntegerField(default=100, help_text="Percentage of deal credit 0–100")

    class Meta(BaseEntity.Meta):
        db_table = "crm_opportunity_team_members"
        unique_together = [("opportunity", "user")]


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


class Quote(BaseEntity):
    """A sales quote / light CPQ document (§6.3)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to Customer"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CONVERTED = "converted", "Converted to Order"

    opportunity = models.ForeignKey(
        Opportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes"
    )
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes"
    )
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    quote_number = models.CharField(max_length=50, blank=True, db_index=True)
    valid_until = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    terms_and_conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    esignature_url = models.URLField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_quotes",
    )

    class Meta(BaseEntity.Meta):
        db_table = "crm_quotes"

    def __str__(self) -> str:
        return self.quote_number or str(self.id)

    def recalculate_totals(self) -> None:
        line_total = sum(item.line_total for item in self.items.filter(is_deleted=False))
        self.subtotal = line_total
        self.grand_total = line_total - self.discount_amount + self.tax_amount


class QuoteItem(BaseEntity):
    """A line item on a Quote (§6.3)."""

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    unit_price = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Discount %")
    line_total = models.DecimalField(max_digits=19, decimal_places=2, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "crm_quote_items"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price * (1 - self.discount_pct / 100)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.description


class Case(BaseEntity):
    """A customer support case / service request (§6.3)."""

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        OPEN = "open", "Open"
        PENDING = "pending", "Pending Customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        ESCALATED = "escalated", "Escalated"

    subject = models.CharField(max_length=500, db_index=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases"
    )
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases"
    )
    opportunity = models.ForeignKey(
        Opportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_cases",
    )
    sla_hours = models.IntegerField(null=True, blank=True, help_text="SLA response time in hours")
    sla_due_at = models.DateTimeField(null=True, blank=True)
    sla_breached = models.BooleanField(default=False)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_cases"

    def __str__(self) -> str:
        return self.subject


class Quota(BaseEntity):
    """Sales quota for a rep or team over a time period (§6.3)."""

    class Period(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="quotas",
    )
    territory = models.ForeignKey(
        Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotas"
    )
    period = models.CharField(max_length=20, choices=Period.choices, default=Period.QUARTERLY)
    period_start = models.DateField()
    period_end = models.DateField()
    target_amount = models.DecimalField(max_digits=19, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "crm_quotas"

    def __str__(self) -> str:
        user_label = str(self.user) if self.user else "Team"
        return f"{user_label} — {self.period} {self.period_start}"
