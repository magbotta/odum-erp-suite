"""
Education / Student Information System models (§7).
Depends on: HRM (staff/faculty as Employees), Accounting (fee invoicing), CRM (admissions pipeline).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class AcademicYear(BaseEntity):
    name = models.CharField(max_length=50)  # e.g. "2025-2026"
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "sis_academic_years"

    def __str__(self) -> str:
        return self.name


class Program(BaseEntity):
    """An academic program / degree track (e.g. Bachelor of Science)."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, blank=True)
    duration_years = models.PositiveSmallIntegerField(default=4)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_programs"

    def __str__(self) -> str:
        return self.name


class Course(BaseEntity):
    """A subject / unit of study offered across terms."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, db_index=True)
    credit_hours = models.PositiveSmallIntegerField(default=3)
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="courses"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_courses"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class CourseSection(BaseEntity):
    """
    A scheduled offering of a Course in a specific term / room.
    Conflict-free scheduling is enforced by the schedule fields.
    """

    class DayOfWeek(models.TextChoices):
        MON = "mon", "Monday"
        TUE = "tue", "Tuesday"
        WED = "wed", "Wednesday"
        THU = "thu", "Thursday"
        FRI = "fri", "Friday"
        SAT = "sat", "Saturday"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="sections")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="course_sections"
    )
    section_code = models.CharField(max_length=20)
    instructor_employee_id = models.UUIDField(null=True, blank=True)
    room = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(default=30)
    enrolled_count = models.PositiveSmallIntegerField(default=0)
    day_of_week = models.CharField(
        max_length=3, choices=DayOfWeek.choices, blank=True
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_course_sections"

    def __str__(self) -> str:
        return f"{self.course.code} / {self.section_code}"


class Student(BaseEntity):
    """A registered student in the institution."""

    class Status(models.TextChoices):
        APPLICANT = "applicant", "Applicant"
        ENROLLED = "enrolled", "Enrolled"
        ACTIVE = "active", "Active"
        GRADUATED = "graduated", "Graduated"
        WITHDRAWN = "withdrawn", "Withdrawn"
        SUSPENDED = "suspended", "Suspended"

    student_number = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="students"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLICANT)
    enrollment_date = models.DateField(null=True, blank=True)
    expected_graduation_date = models.DateField(null=True, blank=True)
    # Cross-app: CRM lead/contact that became this student
    crm_contact_id = models.UUIDField(null=True, blank=True)
    # Guardian / parent contact
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_email = models.EmailField(blank=True)
    guardian_phone = models.CharField(max_length=32, blank=True)
    # Special education support flag — see §13 FERPA/IDEA access controls
    has_iep = models.BooleanField(default=False, help_text="Has an active IEP/504 plan")

    class Meta(BaseEntity.Meta):
        db_table = "sis_students"

    def __str__(self) -> str:
        return f"{self.student_number} — {self.first_name} {self.last_name}"


class Enrollment(BaseEntity):
    """A student's registration in a CourseSection for a term."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        ATTENDING = "attending", "Attending"
        DROPPED = "dropped", "Dropped"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    section = models.ForeignKey(
        CourseSection, on_delete=models.PROTECT, related_name="enrollments"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REGISTERED)
    enrollment_date = models.DateField()
    final_grade = models.CharField(max_length=10, blank=True)
    grade_points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_enrollments"
        unique_together = [("student", "section")]

    def __str__(self) -> str:
        return f"{self.student} ↔ {self.section}"


class ClassAttendance(BaseEntity):
    """Daily attendance record per student per course section."""

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PRESENT
    )
    remarks = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_class_attendance"
        unique_together = [("enrollment", "date")]

    def __str__(self) -> str:
        return f"{self.enrollment} [{self.date}] {self.status}"


class GradeEntry(BaseEntity):
    """A single graded assessment for an Enrollment (quiz, exam, assignment)."""

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="grade_entries"
    )
    assessment_name = models.CharField(max_length=150)
    max_score = models.DecimalField(max_digits=7, decimal_places=2)
    score = models.DecimalField(max_digits=7, decimal_places=2)
    weight_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Weight of this assessment in the final grade %"
    )
    graded_by_employee_id = models.UUIDField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_grade_entries"

    def __str__(self) -> str:
        return f"{self.enrollment} — {self.assessment_name}: {self.score}/{self.max_score}"


class FeeSchedule(BaseEntity):
    """Tuition and fee structure per program/year (§7)."""

    name = models.CharField(max_length=150)
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="fee_schedules"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="fee_schedules"
    )
    tuition_amount = models.DecimalField(max_digits=19, decimal_places=4)
    other_fees = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta(BaseEntity.Meta):
        db_table = "sis_fee_schedules"

    def __str__(self) -> str:
        return self.name


class StudentFeeInvoice(BaseEntity):
    """A fee invoice raised for a student for a term (§7, cross-app → Accounting AR)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_invoices")
    fee_schedule = models.ForeignKey(
        FeeSchedule, null=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    invoice_number = models.CharField(max_length=50, blank=True, db_index=True)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Cross-app: link to Accounting SalesInvoice
    accounting_invoice_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_student_fee_invoices"

    def __str__(self) -> str:
        return f"{self.invoice_number} — {self.student}"
