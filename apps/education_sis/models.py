"""
Education / Student Information System models (§7).
Depends on: HRM (staff/faculty as Employees), Accounting (fee invoicing), CRM (admissions pipeline).
"""
from __future__ import annotations

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


class Term(BaseEntity):
    """A semester/term within an academic year (Fall, Spring, Summer, etc.)."""

    class TermType(models.TextChoices):
        FALL = "fall", "Fall"
        SPRING = "spring", "Spring"
        SUMMER = "summer", "Summer"
        TRIMESTER_1 = "trimester_1", "Trimester 1"
        TRIMESTER_2 = "trimester_2", "Trimester 2"
        TRIMESTER_3 = "trimester_3", "Trimester 3"
        FULL_YEAR = "full_year", "Full Year"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=100)  # e.g. "Fall 2025"
    term_type = models.CharField(max_length=20, choices=TermType.choices, default=TermType.FALL)
    start_date = models.DateField()
    end_date = models.DateField()
    registration_open_date = models.DateField(null=True, blank=True)
    registration_close_date = models.DateField(null=True, blank=True)
    grade_submission_deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "sis_terms"

    def __str__(self) -> str:
        return "{} — {}".format(str(self.academic_year), self.name)


class Room(BaseEntity):
    """Physical classroom, lab, or meeting space with capacity for conflict detection."""

    class RoomType(models.TextChoices):
        LECTURE = "lecture", "Lecture Hall"
        SEMINAR = "seminar", "Seminar Room"
        LAB = "lab", "Laboratory"
        STUDIO = "studio", "Art / Music Studio"
        GYM = "gym", "Gymnasium"
        AUDITORIUM = "auditorium", "Auditorium"
        OFFICE = "office", "Office"
        OTHER = "other", "Other"

    room_number = models.CharField(max_length=20)
    building = models.CharField(max_length=100, blank=True)
    floor = models.CharField(max_length=10, blank=True)
    room_type = models.CharField(max_length=20, choices=RoomType.choices, default=RoomType.LECTURE)
    capacity = models.PositiveSmallIntegerField(default=30)
    has_projector = models.BooleanField(default=False)
    has_whiteboard = models.BooleanField(default=True)
    is_accessible = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_rooms"

    def __str__(self) -> str:
        if self.building:
            return "{} {} ({})".format(self.building, self.room_number, self.room_type)
        return "Room {}".format(self.room_number)


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
        return "{} — {}".format(self.code, self.name)


class CourseSection(BaseEntity):
    """
    A scheduled offering of a Course in a specific term / room.
    Conflict-free scheduling enforced by hooks/scheduling.py before save.
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
    term = models.ForeignKey(
        Term, null=True, blank=True, on_delete=models.SET_NULL, related_name="term_sections"
    )
    section_code = models.CharField(max_length=20)
    instructor_employee_id = models.UUIDField(null=True, blank=True)
    # Legacy plain-text room kept for backwards compat; room_link is the preferred reference
    room = models.CharField(max_length=100, blank=True)
    room_link = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="course_sections"
    )
    capacity = models.PositiveSmallIntegerField(default=30)
    enrolled_count = models.PositiveSmallIntegerField(default=0)
    # Single-day shorthand (legacy); days_of_week supports MWF/TTh patterns
    day_of_week = models.CharField(max_length=3, choices=DayOfWeek.choices, blank=True)
    days_of_week = models.JSONField(
        default=list, blank=True,
        help_text="Multi-day schedule e.g. ['mon','wed','fri']"
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_course_sections"

    def __str__(self) -> str:
        return "{} / {}".format(self.course.code, self.section_code)


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
    actual_graduation_date = models.DateField(null=True, blank=True)
    cumulative_gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
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
        return "{} — {} {}".format(self.student_number, self.first_name, self.last_name)


class AdmissionApplication(BaseEntity):
    """
    Formal admissions application — the pipeline from prospect to enrolled student.
    Reuses CRM admissions pipeline concept (§7): crm_lead_id links to the originating CRM Lead.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        OFFER_MADE = "offer_made", "Offer Made"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        WAITLISTED = "waitlisted", "Waitlisted"
        WITHDRAWN = "withdrawn", "Withdrawn by Applicant"

    application_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    applicant_first_name = models.CharField(max_length=150)
    applicant_last_name = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    program = models.ForeignKey(
        Program, null=True, on_delete=models.SET_NULL, related_name="applications"
    )
    academic_year = models.ForeignKey(
        AcademicYear, null=True, on_delete=models.SET_NULL, related_name="applications"
    )
    term = models.ForeignKey(
        Term, null=True, blank=True, on_delete=models.SET_NULL, related_name="applications"
    )
    previous_institution = models.CharField(max_length=255, blank=True)
    gpa_at_previous_institution = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )
    personal_statement = models.TextField(blank=True)
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    offer_date = models.DateField(null=True, blank=True)
    offer_expiry_date = models.DateField(null=True, blank=True)
    acceptance_date = models.DateField(null=True, blank=True)
    # Set once the application converts to a student record
    student = models.ForeignKey(
        Student, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="admission_applications"
    )
    crm_lead_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_admission_applications"

    def __str__(self) -> str:
        return "{} — {} {}".format(
            self.application_number or str(self.pk)[:8],
            self.applicant_first_name, self.applicant_last_name,
        )


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
        return "{} -> {}".format(str(self.student), str(self.section))


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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_class_attendance"
        unique_together = [("enrollment", "date")]

    def __str__(self) -> str:
        return "{} [{}] {}".format(str(self.enrollment), str(self.date), self.status)


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
        return "{} — {}: {}/{}".format(
            str(self.enrollment), self.assessment_name, self.score, self.max_score
        )


class LearningStandard(BaseEntity):
    """A competency / learning standard for standards-based grading (§7)."""

    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField()
    subject_area = models.CharField(max_length=100, blank=True)
    grade_level = models.CharField(max_length=50, blank=True)
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_standards"
    )
    parent_standard = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="child_standards"
    )
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_learning_standards"

    def __str__(self) -> str:
        return "{}: {}".format(self.code, self.description[:60])


class StandardsGradeEntry(BaseEntity):
    """Proficiency rating for one learning standard in an enrollment (standards-based grading)."""

    class ProficiencyLevel(models.TextChoices):
        EXCEEDING = "exceeding", "Exceeding Standard (4)"
        MEETING = "meeting", "Meeting Standard (3)"
        APPROACHING = "approaching", "Approaching Standard (2)"
        NOT_YET = "not_yet", "Not Yet Meeting Standard (1)"

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="standards_grades"
    )
    standard = models.ForeignKey(
        LearningStandard, on_delete=models.CASCADE, related_name="grade_entries"
    )
    proficiency_level = models.CharField(max_length=20, choices=ProficiencyLevel.choices)
    evidence = models.TextField(blank=True)
    assessed_date = models.DateField(null=True, blank=True)
    assessed_by_id = models.UUIDField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_standards_grade_entries"
        unique_together = [("enrollment", "standard")]

    def __str__(self) -> str:
        return "{} — {} {}".format(
            str(self.enrollment), self.standard.code, self.proficiency_level
        )


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


class GradeScale(BaseEntity):
    """Grade scale — maps score ranges to letter grades and GPA points."""

    name = models.CharField(max_length=100)
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="grade_scales"
    )
    is_default = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "sis_grade_scales"

    def __str__(self):
        return self.name


class GradeScaleEntry(BaseEntity):
    """One row in a grade scale (e.g. A = 90-100 = 4.0)."""

    grade_scale = models.ForeignKey(GradeScale, on_delete=models.CASCADE, related_name="entries")
    letter_grade = models.CharField(max_length=5)
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    gpa_points = models.DecimalField(max_digits=4, decimal_places=2)
    description = models.CharField(max_length=100, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_grade_scale_entries"
        ordering = ["-min_score"]

    def __str__(self):
        return "{}: {} ({}-{})".format(
            str(self.grade_scale), self.letter_grade, self.min_score, self.max_score
        )


class CoursePrerequisite(BaseEntity):
    """A prerequisite relationship between courses."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="prerequisites")
    prerequisite_course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="is_prerequisite_for"
    )
    minimum_grade = models.CharField(max_length=5, blank=True)
    is_mandatory = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_course_prerequisites"
        unique_together = [("course", "prerequisite_course")]

    def __str__(self):
        return "{} requires {}".format(str(self.course), str(self.prerequisite_course))


class Scholarship(BaseEntity):
    """A scholarship or bursary available to students (§7 Financial Aid)."""

    class ScholarshipType(models.TextChoices):
        MERIT = "merit", "Merit-Based"
        NEED = "need", "Need-Based"
        ATHLETIC = "athletic", "Athletic"
        DEPARTMENTAL = "departmental", "Departmental"
        EXTERNAL = "external", "External / Donor"
        BURSARY = "bursary", "Bursary"
        GOVERNMENT_GRANT = "government_grant", "Government Grant"

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, blank=True, db_index=True)
    scholarship_type = models.CharField(
        max_length=20, choices=ScholarshipType.choices, default=ScholarshipType.MERIT
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    is_percentage = models.BooleanField(
        default=False, help_text="If true, amount is % of tuition fee"
    )
    program = models.ForeignKey(
        Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="scholarships"
    )
    eligibility_criteria = models.TextField(blank=True)
    renewable = models.BooleanField(default=False)
    maximum_recipients = models.PositiveSmallIntegerField(null=True, blank=True)
    active_from = models.DateField(null=True, blank=True)
    active_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_scholarships"

    def __str__(self) -> str:
        return self.name


class ScholarshipAward(BaseEntity):
    """Award of a scholarship to a specific student for an academic year."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        COMPLETED = "completed", "Completed"
        REVOKED = "revoked", "Revoked"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scholarship_awards")
    scholarship = models.ForeignKey(Scholarship, on_delete=models.PROTECT, related_name="awards")
    academic_year = models.ForeignKey(
        AcademicYear, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="scholarship_awards"
    )
    awarded_amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    award_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    awarded_by_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    revocation_reason = models.TextField(blank=True)
    # Cross-app: Accounting credit note applied to offset the fee invoice
    accounting_credit_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_scholarship_awards"

    def __str__(self) -> str:
        return "{} -> {} ({})".format(
            str(self.scholarship), str(self.student), self.status
        )


class IEPCase(BaseEntity):
    """
    Special Education IEP / 504 Plan case.
    FERPA/IDEA-aligned field-level access control enforced at the RBAC layer (§13).
    """

    class PlanType(models.TextChoices):
        IEP = "iep", "IEP (Individualized Education Program)"
        PLAN_504 = "plan_504", "504 Accommodation Plan"
        GIFTED = "gifted", "Gifted/Talented Program"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        UNDER_REVIEW = "under_review", "Under Annual Review"
        COMPLETED = "completed", "Completed / Exited"
        TRANSFERRED = "transferred", "Transferred to Another School"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="iep_cases")
    plan_type = models.CharField(max_length=10, choices=PlanType.choices, default=PlanType.IEP)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    case_number = models.CharField(max_length=50, blank=True, db_index=True)
    primary_disability = models.CharField(max_length=150, blank=True)
    eligibility_date = models.DateField(null=True, blank=True)
    plan_start_date = models.DateField(null=True, blank=True)
    plan_end_date = models.DateField(null=True, blank=True)
    annual_review_date = models.DateField(null=True, blank=True)
    triennial_review_date = models.DateField(null=True, blank=True)
    case_manager_employee_id = models.UUIDField(null=True, blank=True)
    case_manager_name = models.CharField(max_length=255, blank=True)
    annual_goals = models.JSONField(default=list, blank=True)
    services = models.JSONField(default=list, blank=True)
    accommodations = models.JSONField(default=list, blank=True)
    last_meeting_date = models.DateField(null=True, blank=True)
    next_meeting_date = models.DateField(null=True, blank=True)
    parent_consent_date = models.DateField(null=True, blank=True)
    parent_consent_obtained = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_iep_cases"
        verbose_name = "IEP/504 Case"

    def __str__(self):
        return "{} — {} ({})".format(
            self.case_number or str(self.pk)[:8], str(self.student), self.plan_type
        )


class StudentDocument(BaseEntity):
    """
    A document attached to a student record.
    FERPA-aligned: confidential flag restricts access at RBAC level.
    """

    class DocumentType(models.TextChoices):
        TRANSCRIPT = "transcript", "Transcript"
        ID_DOCUMENT = "id_document", "ID Document"
        MEDICAL = "medical", "Medical / Health Form"
        LEGAL = "legal", "Legal Document"
        FINANCIAL_AID = "financial_aid", "Financial Aid"
        ADMISSION = "admission", "Admission Document"
        IEP_DOCUMENT = "iep_document", "IEP/504 Document"
        OTHER = "other", "Other"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    title = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, blank=True)
    is_confidential = models.BooleanField(default=False)
    uploaded_by_id = models.UUIDField(null=True, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_student_documents"

    def __str__(self):
        return "{} — {}".format(str(self.student), self.title)


class ComplianceReport(BaseEntity):
    """State/provincial compliance reporting record (§7)."""

    class ReportType(models.TextChoices):
        ENROLLMENT_COUNT = "enrollment_count", "Enrollment Count"
        ATTENDANCE_RATE = "attendance_rate", "Attendance Rate"
        GRADUATION_RATE = "graduation_rate", "Graduation Rate"
        SPECIAL_ED = "special_ed", "Special Education (IDEA)"
        FINANCIAL_AID = "financial_aid", "Financial Aid"
        FERPA_AUDIT = "ferpa_audit", "FERPA Audit"
        CUSTOM = "custom", "Custom Report"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"
        REQUIRES_CORRECTION = "requires_correction", "Requires Correction"

    report_number = models.CharField(max_length=50, blank=True, db_index=True)
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="compliance_reports"
    )
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT)
    jurisdiction = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True)
    submitted_date = models.DateField(null=True, blank=True)
    submitted_by_id = models.UUIDField(null=True, blank=True)
    report_data = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_compliance_reports"

    def __str__(self):
        return "{} — {} ({})".format(
            self.report_number, self.report_type, str(self.academic_year)
        )


class StudentFeeInvoice(BaseEntity):
    """A fee invoice raised for a student for a term (§7, cross-app -> Accounting AR)."""

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
    academic_year = models.ForeignKey(
        AcademicYear, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="fee_invoices"
    )
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    discount_amount = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Scholarship/bursary/financial-aid discount applied"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    # Cross-app: link to Accounting SalesInvoice
    accounting_invoice_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_student_fee_invoices"

    def __str__(self):
        return "{} — {}".format(self.invoice_number, str(self.student))


class FeePaymentPlan(BaseEntity):
    """Instalment payment plan for a StudentFeeInvoice (§7 payment plans)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        DEFAULTED = "defaulted", "Defaulted"

    invoice = models.ForeignKey(
        StudentFeeInvoice, on_delete=models.CASCADE, related_name="payment_plans"
    )
    plan_name = models.CharField(max_length=150, blank=True)
    number_of_instalments = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_fee_payment_plans"

    def __str__(self) -> str:
        return "{}-instalment plan for {}".format(
            self.number_of_instalments, str(self.invoice)
        )


class FeePaymentPlanInstalment(BaseEntity):
    """An individual instalment within a FeePaymentPlan."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        WAIVED = "waived", "Waived"

    payment_plan = models.ForeignKey(
        FeePaymentPlan, on_delete=models.CASCADE, related_name="instalments"
    )
    instalment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    paid_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=150, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_fee_payment_plan_instalments"
        ordering = ["instalment_number"]

    def __str__(self) -> str:
        return "Instalment {} of {} — {}".format(
            self.instalment_number, str(self.payment_plan), self.status
        )


class AcademicTranscript(BaseEntity):
    """Generated academic transcript for a student (§7)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OFFICIAL = "official", "Official"
        SEALED = "sealed", "Sealed / Certified"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="transcripts")
    academic_year = models.ForeignKey(
        AcademicYear, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="transcripts"
    )
    transcript_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_by_id = models.UUIDField(null=True, blank=True)
    sealed_at = models.DateTimeField(null=True, blank=True)
    sealed_by_id = models.UUIDField(null=True, blank=True)
    cumulative_gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    total_credit_hours = models.PositiveSmallIntegerField(default=0)
    transcript_data = models.JSONField(
        default=dict, help_text="Structured content: courses and grades grouped by year/term"
    )
    issued_to = models.CharField(max_length=255, blank=True)
    issued_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "sis_academic_transcripts"

    def __str__(self) -> str:
        return "{} — {} ({})".format(
            self.transcript_number or str(self.pk)[:8], str(self.student), self.status
        )
