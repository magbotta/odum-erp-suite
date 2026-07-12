"""HRM models: Department, Employee, LeaveType, LeaveApplication, Attendance (§6.4)."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class Department(BaseEntity):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    # head is set after Employee is created — avoids circular FK at migration time
    head_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_departments"

    def __str__(self) -> str:
        return self.name


class Employee(BaseEntity):
    """Core employee record (§6.4)."""

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"
        INTERN = "intern", "Intern"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On Leave"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"

    # Optional link to platform user account
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="employee_profile",
    )
    employee_number = models.CharField(max_length=50, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    designation = models.CharField(max_length=150, blank=True, help_text="Job title / designation")
    date_of_joining = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports"
    )
    # Salary stored as UUID reference to a Payroll component, not a plain field —
    # to enforce field-level access control (only Payroll/HR roles can see it).
    # Actual salary data lives in the Payroll app.

    class Meta(BaseEntity.Meta):
        db_table = "hrm_employees"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.employee_number})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class LeaveType(BaseEntity):
    """Configurable leave category (annual, sick, maternity, etc.)."""

    name = models.CharField(max_length=100, unique=True)
    days_allowed_per_year = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False)
    max_carry_forward_days = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    allow_negative_balance = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_leave_types"

    def __str__(self) -> str:
        return self.name


class LeaveApplication(BaseEntity):
    """An employee's leave request with approval workflow (§6.4)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_applications")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="applications")
    from_date = models.DateField()
    to_date = models.DateField()
    total_days = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leave_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_leave_applications"

    def __str__(self) -> str:
        return f"{self.employee} — {self.leave_type} ({self.from_date} to {self.to_date})"


class Attendance(BaseEntity):
    """
    One record per clock-in/out event (§6.4).
    Granular — not pre-aggregated — so exceptions can be resolved before payroll.
    """

    class Method(models.TextChoices):
        MANUAL = "manual", "Manual Entry"
        GEO = "geo", "Geo Check-in"
        QR = "qr", "QR / Kiosk"
        BIOMETRIC = "biometric", "Badge / Biometric"

    class DayStatus(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        HALF_DAY = "half_day", "Half Day"
        ON_LEAVE = "on_leave", "On Leave"
        HOLIDAY = "holiday", "Holiday"
        WEEKEND = "weekend", "Weekend"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendances")
    attendance_date = models.DateField(db_index=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    working_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.MANUAL)
    status = models.CharField(max_length=20, choices=DayStatus.choices, default=DayStatus.PRESENT)
    shift = models.CharField(max_length=50, blank=True)
    late_entry = models.BooleanField(default=False)
    early_exit = models.BooleanField(default=False)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_attendance"
        unique_together = [("employee", "attendance_date")]

    def __str__(self) -> str:
        return f"{self.employee} — {self.attendance_date}"
