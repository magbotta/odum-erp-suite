"""HRM models — full §6.4 implementation.

Covers: Department, Employee, Shift scheduling, Holiday lists, Leave management,
Recruitment pipeline, Performance reviews, Goals/OKRs, Employee documents,
Disciplinary cases, Onboarding checklists.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


# ── Org structure ─────────────────────────────────────────────────────────────

class Department(BaseEntity):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    head_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_departments"

    def __str__(self) -> str:
        return self.name


class JobPosition(BaseEntity):
    """An open headcount position / job requisition (§6.4 Recruitment)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On Hold"
        FILLED = "filled", "Filled"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="job_positions"
    )
    headcount = models.PositiveIntegerField(default=1)
    employment_type = models.CharField(
        max_length=20,
        choices=[("full_time","Full-time"),("part_time","Part-time"),("contract","Contract"),("intern","Intern")],
        default="full_time",
    )
    location = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    expected_start_date = models.DateField(null=True, blank=True)
    hiring_manager_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_job_positions"

    def __str__(self) -> str:
        return self.title


# ── Core Employee ─────────────────────────────────────────────────────────────

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
        PROBATION = "probation", "Probation"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT = "prefer_not_to_say", "Prefer not to say"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="employee_profile",
    )
    employee_number = models.CharField(max_length=50, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    personal_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    mobile = models.CharField(max_length=32, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    designation = models.CharField(max_length=150, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports"
    )
    notice_period_days = models.PositiveIntegerField(default=30)
    date_of_resignation = models.DateField(null=True, blank=True)
    date_of_termination = models.DateField(null=True, blank=True)
    exit_reason = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    emergency_contact_relation = models.CharField(max_length=50, blank=True)
    sourced_from_position_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_employees"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.employee_number})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


# ── Shift scheduling ──────────────────────────────────────────────────────────

class Shift(BaseEntity):
    """A named work shift definition (§6.4)."""

    class ShiftType(models.TextChoices):
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"
        EVENING = "evening", "Evening"
        NIGHT = "night", "Night"
        FLEXIBLE = "flexible", "Flexible"

    name = models.CharField(max_length=100)
    shift_type = models.CharField(max_length=20, choices=ShiftType.choices, default=ShiftType.MORNING)
    start_time = models.TimeField()
    end_time = models.TimeField()
    total_hours = models.DecimalField(max_digits=4, decimal_places=2, default=8)
    late_entry_grace_minutes = models.PositiveIntegerField(default=15)
    early_exit_grace_minutes = models.PositiveIntegerField(default=15)
    overtime_threshold_hours = models.DecimalField(max_digits=4, decimal_places=2, default=8)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_shifts"

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time}–{self.end_time})"


class ShiftAssignment(BaseEntity):
    """Assigns a Shift to an Employee for a date range (§6.4)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="shift_assignments")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="assignments")
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_shift_assignments"

    def __str__(self) -> str:
        return f"{self.employee} → {self.shift} from {self.from_date}"


# ── Holiday management ────────────────────────────────────────────────────────

class HolidayList(BaseEntity):
    """A named holiday calendar (e.g. US Public Holidays 2026)."""

    name = models.CharField(max_length=150)
    from_date = models.DateField()
    to_date = models.DateField()
    country = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_holiday_lists"

    def __str__(self) -> str:
        return self.name


class Holiday(BaseEntity):
    """A single holiday entry within a HolidayList."""

    holiday_list = models.ForeignKey(HolidayList, on_delete=models.CASCADE, related_name="holidays")
    holiday_date = models.DateField()
    description = models.CharField(max_length=200)
    is_weekly_off = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_holidays"
        unique_together = [("holiday_list", "holiday_date")]

    def __str__(self) -> str:
        return f"{self.holiday_date} — {self.description}"


# ── Leave management ──────────────────────────────────────────────────────────

class LeaveType(BaseEntity):
    """Configurable leave category (annual, sick, maternity, etc.)."""

    name = models.CharField(max_length=100, unique=True)
    days_allowed_per_year = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False)
    max_carry_forward_days = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    allow_negative_balance = models.BooleanField(default=False)
    accrual_frequency = models.CharField(
        max_length=20,
        choices=[("monthly","Monthly"),("quarterly","Quarterly"),("annually","Annually")],
        default="annually",
    )
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_leave_types"

    def __str__(self) -> str:
        return self.name


class LeaveBalance(BaseEntity):
    """Running leave balance per employee per leave type per year (§6.4)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="balances")
    year = models.PositiveIntegerField()
    total_allocated = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    carried_forward = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    total_taken = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    total_pending = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_leave_balances"
        unique_together = [("employee", "leave_type", "year")]

    @property
    def remaining(self):
        return self.total_allocated + self.carried_forward - self.total_taken - self.total_pending

    def __str__(self) -> str:
        return f"{self.employee} — {self.leave_type} ({self.year})"


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


# ── Attendance ────────────────────────────────────────────────────────────────

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
    shift = models.ForeignKey(
        Shift, null=True, blank=True, on_delete=models.SET_NULL, related_name="attendances"
    )
    late_entry = models.BooleanField(default=False)
    early_exit = models.BooleanField(default=False)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_attendance"
        unique_together = [("employee", "attendance_date")]

    def __str__(self) -> str:
        return f"{self.employee} — {self.attendance_date}"


# ── Employee documents ────────────────────────────────────────────────────────

class EmployeeDocument(BaseEntity):
    """Tracks employee documents with expiry alerts (§6.4)."""

    class DocumentType(models.TextChoices):
        CONTRACT = "contract", "Employment Contract"
        OFFER_LETTER = "offer_letter", "Offer Letter"
        ID = "national_id", "National ID"
        PASSPORT = "passport", "Passport"
        VISA = "visa", "Work Visa / Permit"
        CERTIFICATE = "certificate", "Certificate / Qualification"
        BACKGROUND_CHECK = "background_check", "Background Check"
        NDA = "nda", "NDA / Confidentiality Agreement"
        POLICY_ACK = "policy_ack", "Policy Acknowledgment"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    document_name = models.CharField(max_length=200)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    document_number = models.CharField(max_length=100, blank=True)
    issuing_authority = models.CharField(max_length=150, blank=True)
    is_verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_employee_documents"

    def __str__(self) -> str:
        return f"{self.employee} — {self.get_document_type_display()}"


# ── Recruitment pipeline ──────────────────────────────────────────────────────

class JobApplicant(BaseEntity):
    """A candidate in the recruitment pipeline (§6.4)."""

    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREENING = "screening", "Screening"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer Extended"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Source(models.TextChoices):
        DIRECT = "direct", "Direct Application"
        REFERRAL = "referral", "Employee Referral"
        LINKEDIN = "linkedin", "LinkedIn"
        JOB_BOARD = "job_board", "Job Board"
        RECRUITER = "recruiter", "Recruiter / Agency"
        CAMPUS = "campus", "Campus Recruitment"
        OTHER = "other", "Other"

    job_position = models.ForeignKey(
        JobPosition, null=True, blank=True, on_delete=models.SET_NULL, related_name="applicants"
    )
    applicant_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.DIRECT)
    referred_by_employee_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED)
    applied_date = models.DateField()
    resume_url = models.URLField(blank=True)
    cover_letter = models.TextField(blank=True)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    current_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_job_applicants"

    def __str__(self) -> str:
        return f"{self.applicant_name} → {self.job_position}"


class Interview(BaseEntity):
    """An interview round for a JobApplicant (§6.4)."""

    class InterviewType(models.TextChoices):
        PHONE = "phone", "Phone Screen"
        VIDEO = "video", "Video Call"
        IN_PERSON = "in_person", "In-Person"
        TECHNICAL = "technical", "Technical Assessment"
        PANEL = "panel", "Panel Interview"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-Show"

    job_applicant = models.ForeignKey(
        JobApplicant, on_delete=models.CASCADE, related_name="interviews"
    )
    interview_type = models.CharField(
        max_length=20, choices=InterviewType.choices, default=InterviewType.VIDEO
    )
    interviewer_employee_id = models.UUIDField(null=True, blank=True)
    interviewer_name = models.CharField(max_length=200, blank=True)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    feedback = models.TextField(blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    recommendation = models.CharField(
        max_length=20,
        choices=[("strong_yes","Strong Yes"),("yes","Yes"),("neutral","Neutral"),("no","No"),("strong_no","Strong No")],
        blank=True,
    )

    class Meta(BaseEntity.Meta):
        db_table = "hrm_interviews"

    def __str__(self) -> str:
        return f"Interview: {self.job_applicant} [{self.scheduled_at.date()}]"


# ── Performance management ────────────────────────────────────────────────────

class Goal(BaseEntity):
    """An OKR/goal for an employee (§6.4 Performance)."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    key_results = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    period = models.CharField(max_length=20, blank=True, help_text="e.g. Q3 2026")
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    progress_pct = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    set_by_employee_id = models.UUIDField(null=True, blank=True)
    final_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_goals"

    def __str__(self) -> str:
        return f"{self.employee} — {self.title}"


class PerformanceReview(BaseEntity):
    """A performance review record (§6.4 — self/manager/peer/360)."""

    class CycleType(models.TextChoices):
        SELF = "self", "Self Assessment"
        MANAGER = "manager", "Manager Review"
        PEER = "peer", "Peer Review"
        REVIEW_360 = "360", "360° Review"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="performance_reviews")
    reviewer_employee_id = models.UUIDField(null=True, blank=True)
    reviewer_name = models.CharField(max_length=200, blank=True)
    cycle_type = models.CharField(max_length=10, choices=CycleType.choices, default=CycleType.MANAGER)
    period = models.CharField(max_length=30)
    overall_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_performance_reviews"

    def __str__(self) -> str:
        return f"{self.employee} — {self.period} ({self.cycle_type})"


# ── Disciplinary cases ────────────────────────────────────────────────────────

class DisciplinaryCase(BaseEntity):
    """Tracks disciplinary / grievance proceedings (§6.4)."""

    class CaseType(models.TextChoices):
        VERBAL_WARNING = "verbal_warning", "Verbal Warning"
        WARNING = "warning", "Written Warning"
        SUSPENSION = "suspension", "Suspension"
        DEMOTION = "demotion", "Demotion"
        TERMINATION = "termination", "Termination"
        GRIEVANCE = "grievance", "Employee Grievance"
        INVESTIGATION = "investigation", "Investigation"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under Review"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        APPEALED = "appealed", "Appealed"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="disciplinary_cases")
    case_type = models.CharField(max_length=20, choices=CaseType.choices)
    incident_date = models.DateField()
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    handled_by_employee_id = models.UUIDField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    is_confidential = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_disciplinary_cases"

    def __str__(self) -> str:
        return f"{self.employee} — {self.get_case_type_display()} ({self.incident_date})"


# ── Onboarding / Offboarding checklists ───────────────────────────────────────

class EmployeeChecklist(BaseEntity):
    """An onboarding or offboarding checklist for an employee (§6.4)."""

    class ChecklistType(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        OFFBOARDING = "offboarding", "Offboarding"
        TRANSFER = "transfer", "Transfer / Role Change"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="checklists")
    checklist_type = models.CharField(max_length=20, choices=ChecklistType.choices)
    template_name = models.CharField(max_length=150, blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_employee_checklists"

    def __str__(self) -> str:
        return f"{self.employee} — {self.checklist_type} checklist"


class ChecklistTask(BaseEntity):
    """A single task within an EmployeeChecklist."""

    class ResponsibleType(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        HR = "hr", "HR Team"
        MANAGER = "manager", "Manager"
        IT = "it", "IT / Systems"

    checklist = models.ForeignKey(EmployeeChecklist, on_delete=models.CASCADE, related_name="tasks")
    task_description = models.CharField(max_length=300)
    responsible_type = models.CharField(
        max_length=20, choices=ResponsibleType.choices, default=ResponsibleType.HR
    )
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "hrm_checklist_tasks"

    def __str__(self) -> str:
        return f"[{'done' if self.is_completed else 'todo'}] {self.task_description}"
