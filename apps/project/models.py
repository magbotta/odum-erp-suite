"""Project Management models (§6.6): projects, tasks, milestones, timesheets."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class ProjectTemplate(BaseEntity):
    """A reusable project template for repeatable engagement types (§6.6)."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    estimated_days = models.PositiveIntegerField(default=0)
    default_billing_type = models.CharField(max_length=20, default="time_and_material")
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_templates"

    def __str__(self) -> str:
        return self.name


class ProjectTemplateTask(BaseEntity):
    """A task blueprint within a ProjectTemplate."""

    template = models.ForeignKey(ProjectTemplate, on_delete=models.CASCADE, related_name="template_tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sequence = models.PositiveIntegerField(default=0)
    estimated_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    day_offset = models.IntegerField(default=0, help_text="Days from project start date")
    duration_days = models.PositiveIntegerField(default=1)

    class Meta(BaseEntity.Meta):
        db_table = "project_template_tasks"
        ordering = ["template", "sequence"]

    def __str__(self) -> str:
        return "{} / {}".format(self.template.name, self.title)


class Project(BaseEntity):
    """A project with budget, timeline, and billability tracking (§6.6)."""

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "On Hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class BillingType(models.TextChoices):
        TIME_AND_MATERIAL = "time_and_material", "Time & Material"
        FIXED_PRICE = "fixed_price", "Fixed Price"
        MILESTONE = "milestone", "Milestone-Based"
        RETAINER = "retainer", "Retainer"
        NON_BILLABLE = "non_billable", "Non-Billable"

    project_name = models.CharField(max_length=255)
    project_code = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNING)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    is_billable = models.BooleanField(default=False)
    billing_type = models.CharField(
        max_length=20, choices=BillingType.choices, default=BillingType.TIME_AND_MATERIAL
    )
    budget = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    billed_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Cross-app soft links
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    project_manager_id = models.UUIDField(null=True, blank=True)
    project_manager_name = models.CharField(max_length=255, blank=True)
    # Cost center link to Accounting
    cost_center_id = models.UUIDField(null=True, blank=True)
    # Template this project was created from
    template = models.ForeignKey(
        ProjectTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "project_projects"

    def __str__(self) -> str:
        return self.project_name


class ProjectPhase(BaseEntity):
    """A phase or work breakdown structure node within a project (§6.6)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="phases")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sequence = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=19, decimal_places=2, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "project_phases"
        ordering = ["project", "sequence"]

    def __str__(self) -> str:
        return "{} / {}".format(self.project.project_name, self.name)


class ProjectMember(BaseEntity):
    """A team member assigned to a project with billing rate and capacity (§6.6)."""

    class Role(models.TextChoices):
        MANAGER = "manager", "Project Manager"
        LEAD = "lead", "Team Lead"
        MEMBER = "member", "Member"
        CONSULTANT = "consultant", "Consultant"
        REVIEWER = "reviewer", "Reviewer"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    # Cross-app soft reference to Employee
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    billing_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    cost_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    allocated_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_members"
        unique_together = [("project", "employee_id")]

    def __str__(self) -> str:
        return "{} — {}".format(self.project.project_name, self.employee_name)


class ProjectTask(BaseEntity):
    """A unit of work within a project, supports parent-child nesting (§6.6)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        REVIEW = "review", "In Review"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    phase = models.ForeignKey(
        ProjectPhase, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="project_tasks",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    parent_task = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subtasks"
    )
    sequence = models.PositiveIntegerField(default=0)
    depends_on = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="dependents")
    is_critical_path = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "project_tasks"
        ordering = ["project", "sequence"]

    def __str__(self) -> str:
        return "[{}] {}".format(self.project.project_name, self.title)


class Milestone(BaseEntity):
    """A key project deliverable with a target date (§6.6)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACHIEVED = "achieved", "Achieved"
        MISSED = "missed", "Missed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=255)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    description = models.TextField(blank=True)
    achieved_at = models.DateField(null=True, blank=True)
    # Invoice generated from this milestone (cross-app soft ref)
    invoice_id = models.UUIDField(null=True, blank=True)
    billing_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "project_milestones"

    def __str__(self) -> str:
        return "{} — {}".format(self.project, self.title)


class BillingRule(BaseEntity):
    """Defines how and when a project gets billed (§6.6)."""

    class BillingEvent(models.TextChoices):
        TIMESHEET_APPROVAL = "timesheet_approval", "On Timesheet Approval"
        MILESTONE = "milestone", "On Milestone"
        PERIODIC = "periodic", "Periodic (Monthly/Weekly)"
        MANUAL = "manual", "Manual"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="billing_rules")
    billing_event = models.CharField(
        max_length=30, choices=BillingEvent.choices, default=BillingEvent.TIMESHEET_APPROVAL
    )
    description = models.CharField(max_length=255, blank=True)
    # For milestone billing: which milestone triggers the invoice
    milestone = models.ForeignKey(
        Milestone, null=True, blank=True, on_delete=models.SET_NULL, related_name="billing_rules"
    )
    # For periodic billing
    billing_day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    # Percentage of contract value (for fixed price / milestone billing)
    billing_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    billing_amount = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    # Accounting references for invoice generation
    income_account_id = models.UUIDField(null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    last_billed_at = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_billing_rules"

    def __str__(self) -> str:
        return "{} — {}".format(self.project.project_name, self.get_billing_event_display())


class RiskIssue(BaseEntity):
    """Risk and issue log per project with confidentiality-aware permissions (§6.6)."""

    class RecordType(models.TextChoices):
        RISK = "risk", "Risk"
        ISSUE = "issue", "Issue"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        ACCEPTED = "accepted", "Accepted (Risk)"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="risks_issues")
    record_type = models.CharField(max_length=10, choices=RecordType.choices, default=RecordType.RISK)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    probability = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                      help_text="Probability % for risks (0-100)")
    impact = models.TextField(blank=True)
    mitigation_plan = models.TextField(blank=True)
    owner_id = models.UUIDField(null=True, blank=True)
    owner_name = models.CharField(max_length=255, blank=True)
    due_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateField(null=True, blank=True)
    is_confidential = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "project_risks_issues"

    def __str__(self) -> str:
        return "[{}] {} — {}".format(
            self.get_record_type_display(), self.project.project_name, self.title
        )


class Timesheet(BaseEntity):
    """
    A timesheet header per employee per period (§6.6).
    Contains one or more TimesheetEntry rows.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    timesheet_number = models.CharField(max_length=50, blank=True, db_index=True)
    # Cross-app: Employee from HRM
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    total_billable_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    total_billing_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_timesheets",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Invoice generated from this timesheet (cross-app soft ref)
    invoice_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_timesheets"

    def __str__(self) -> str:
        return "Timesheet {} [{} - {}]".format(
            self.employee_name, self.start_date, self.end_date
        )


class TimesheetEntry(BaseEntity):
    """One time log row within a Timesheet (§6.6)."""

    class ActivityType(models.TextChoices):
        DEVELOPMENT = "development", "Development"
        DESIGN = "design", "Design"
        MEETING = "meeting", "Meeting"
        REVIEW = "review", "Review / QA"
        DOCUMENTATION = "documentation", "Documentation"
        SUPPORT = "support", "Support"
        TRAVEL = "travel", "Travel"
        OTHER = "other", "Other"

    timesheet = models.ForeignKey(Timesheet, on_delete=models.CASCADE, related_name="entries")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="timesheet_entries")
    task = models.ForeignKey(
        ProjectTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="timesheet_entries"
    )
    activity_type = models.CharField(
        max_length=20, choices=ActivityType.choices, default=ActivityType.DEVELOPMENT
    )
    from_time = models.DateTimeField()
    to_time = models.DateTimeField()
    hours = models.DecimalField(max_digits=7, decimal_places=2)
    is_billable = models.BooleanField(default=True)
    billing_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    billing_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_timesheet_entries"

    def __str__(self) -> str:
        return "{} / {} — {}h".format(self.project, self.activity_type, self.hours)
