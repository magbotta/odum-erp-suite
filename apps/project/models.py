"""Project Management models (§6.6): projects, tasks, milestones, timesheets."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Project(BaseEntity):
    """A project with budget, timeline, and billability tracking (§6.6)."""

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "On Hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    project_name = models.CharField(max_length=255)
    project_code = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNING)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    is_billable = models.BooleanField(default=False)
    budget = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Cross-app soft links
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)
    project_manager_id = models.UUIDField(null=True, blank=True)
    # Cost center link to Accounting
    cost_center_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "project_projects"

    def __str__(self) -> str:
        return self.project_name


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
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="project_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    parent_task = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subtasks"
    )
    sequence = models.PositiveIntegerField(default=0)
    depends_on = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="dependents")

    class Meta(BaseEntity.Meta):
        db_table = "project_tasks"
        ordering = ["project", "sequence"]

    def __str__(self) -> str:
        return f"[{self.project.project_name}] {self.title}"


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

    class Meta(BaseEntity.Meta):
        db_table = "project_milestones"

    def __str__(self) -> str:
        return f"{self.project} — {self.title}"


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

    # Cross-app: Employee from HRM
    employee_id = models.UUIDField(db_index=True)
    employee_name = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    total_billable_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_timesheets",
    )

    class Meta(BaseEntity.Meta):
        db_table = "project_timesheets"

    def __str__(self) -> str:
        return f"Timesheet {self.employee_name} [{self.start_date} – {self.end_date}]"


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
        return f"{self.project} / {self.activity_type} — {self.hours}h"
