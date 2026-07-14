"""Education SIS action endpoints (§7) — full implementation."""
import datetime
import uuid
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from core.platform_api.security import AuthBearer

router = Router(tags=["Education SIS Actions"], auth=AuthBearer())


class ActionResponse(Schema):
    ok: bool
    message: str


# ── Student lifecycle ─────────────────────────────────────────────────────────

@router.post("/students/{student_id}/admit", response=ActionResponse)
def admit_student(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import admit_student as do_admit, set_student_number
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    if student.status != "applicant":
        return {"ok": False, "message": "Only Applicant students can be admitted."}
    set_student_number(student)
    do_admit(student)
    student.save()
    return {"ok": True, "message": "Student {} admitted (enrolled).".format(
        student.student_number)}


@router.post("/students/{student_id}/activate", response=ActionResponse)
def activate_student(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import activate_student as do_activate
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    if student.status != "enrolled":
        return {"ok": False, "message": "Student must be Enrolled to activate."}
    do_activate(student)
    student.save()
    return {"ok": True, "message": "Student {} activated.".format(student.student_number)}


@router.post("/students/{student_id}/graduate", response=ActionResponse)
def graduate_student(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import graduate_student as do_graduate
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    if student.status not in ("active", "enrolled"):
        return {"ok": False, "message": "Student must be Active or Enrolled to graduate."}
    do_graduate(student)
    student.save()
    return {"ok": True, "message": "Student {} graduated.".format(student.student_number)}


@router.post("/students/{student_id}/withdraw", response=ActionResponse)
def withdraw_student(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import withdraw_student as do_withdraw
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    if student.status not in ("active", "enrolled"):
        return {"ok": False, "message": "Student must be Active or Enrolled to withdraw."}
    do_withdraw(student)
    student.save()
    return {"ok": True, "message": "Student {} withdrawn.".format(student.student_number)}


@router.post("/students/{student_id}/suspend", response=ActionResponse)
def suspend_student(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    from apps.education_sis.hooks.student import suspend_student as do_suspend
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    if student.status not in ("active", "enrolled"):
        return {"ok": False, "message": "Student must be Active or Enrolled to suspend."}
    do_suspend(student)
    student.save()
    return {"ok": True, "message": "Student {} suspended.".format(student.student_number)}


# ── Admissions pipeline ───────────────────────────────────────────────────────

class ApplicationIn(Schema):
    applicant_first_name: str
    applicant_last_name: str
    email: str
    phone: Optional[str] = None
    program_id: Optional[str] = None
    academic_year_id: Optional[str] = None
    term_id: Optional[str] = None
    previous_institution: Optional[str] = None
    personal_statement: Optional[str] = None


class OfferIn(Schema):
    offer_expiry_days: int = 30


class RejectApplicationIn(Schema):
    reason: str = ""


@router.post("/applications", response=ActionResponse)
def create_application(request, payload: ApplicationIn):
    from apps.education_sis.models import AdmissionApplication, Program, AcademicYear, Term
    from apps.education_sis.hooks.admissions import set_application_number
    from core.platform_api.security import get_company_id
    company_id = get_company_id(request)

    program = None
    if payload.program_id:
        program = get_object_or_404(Program, id=uuid.UUID(payload.program_id), is_deleted=False)
    ay = None
    if payload.academic_year_id:
        ay = get_object_or_404(AcademicYear, id=uuid.UUID(payload.academic_year_id))
    term = None
    if payload.term_id:
        term = get_object_or_404(Term, id=uuid.UUID(payload.term_id), is_deleted=False)

    app = AdmissionApplication(
        applicant_first_name=payload.applicant_first_name,
        applicant_last_name=payload.applicant_last_name,
        email=payload.email,
        phone=payload.phone or "",
        program=program,
        academic_year=ay,
        term=term,
        previous_institution=payload.previous_institution or "",
        personal_statement=payload.personal_statement or "",
        company_id=company_id,
    )
    set_application_number(app)
    app.save()
    return {"ok": True, "message": "Application {} created.".format(app.application_number)}


@router.post("/applications/{app_id}/submit", response=ActionResponse)
def submit_application(request, app_id: uuid.UUID):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import submit_application as do_submit
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status != "draft":
        return {"ok": False, "message": "Only draft applications can be submitted."}
    do_submit(app)
    return {"ok": True, "message": "Application {} submitted.".format(app.application_number)}


@router.post("/applications/{app_id}/review", response=ActionResponse)
def review_application(request, app_id: uuid.UUID):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import start_review
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status != "submitted":
        return {"ok": False, "message": "Application must be Submitted to start review."}
    start_review(app)
    return {"ok": True, "message": "Application {} is now under review.".format(
        app.application_number)}


@router.post("/applications/{app_id}/offer", response=ActionResponse)
def make_offer(request, app_id: uuid.UUID, payload: OfferIn):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import make_offer as do_offer
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status not in ("under_review", "waitlisted"):
        return {"ok": False,
                "message": "Application must be Under Review or Waitlisted to make an offer."}
    do_offer(app, offer_expiry_days=payload.offer_expiry_days)
    return {"ok": True, "message": "Offer made for application {}. Expires on {}.".format(
        app.application_number, str(app.offer_expiry_date))}


@router.post("/applications/{app_id}/accept", response=ActionResponse)
def accept_application(request, app_id: uuid.UUID):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import accept_offer
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status != "offer_made":
        return {"ok": False, "message": "An offer must have been made before acceptance."}
    accept_offer(app)
    return {"ok": True, "message": "Application {} accepted. Ready to convert to student.".format(
        app.application_number)}


@router.post("/applications/{app_id}/reject", response=ActionResponse)
def reject_application(request, app_id: uuid.UUID, payload: RejectApplicationIn):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import reject_application as do_reject
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status in ("accepted", "withdrawn"):
        return {"ok": False, "message": "Cannot reject an application in {} status.".format(
            app.status)}
    do_reject(app, reason=payload.reason)
    return {"ok": True, "message": "Application {} rejected.".format(app.application_number)}


@router.post("/applications/{app_id}/waitlist", response=ActionResponse)
def waitlist_application(request, app_id: uuid.UUID):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import waitlist_application as do_waitlist
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    if app.status not in ("submitted", "under_review"):
        return {"ok": False,
                "message": "Application must be Submitted or Under Review to waitlist."}
    do_waitlist(app)
    return {"ok": True, "message": "Application {} waitlisted.".format(app.application_number)}


@router.post("/applications/{app_id}/convert-to-student", response=ActionResponse)
def convert_to_student(request, app_id: uuid.UUID):
    from apps.education_sis.models import AdmissionApplication
    from apps.education_sis.hooks.admissions import convert_to_student as do_convert
    app = get_object_or_404(AdmissionApplication, id=app_id, is_deleted=False)
    try:
        student = do_convert(app)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Student {} created from application {}.".format(
        student.student_number, app.application_number)}


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollIn(Schema):
    section_id: str
    enrollment_date: Optional[str] = None


@router.post("/students/{student_id}/enroll", response=ActionResponse)
def enroll_student(request, student_id: uuid.UUID, payload: EnrollIn):
    from apps.education_sis.models import Student, CourseSection
    from apps.education_sis.hooks.enrollment import enroll_in_section
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    section = get_object_or_404(CourseSection, id=uuid.UUID(payload.section_id), is_deleted=False)
    enroll_date = datetime.date.today()
    if payload.enrollment_date:
        try:
            enroll_date = datetime.date.fromisoformat(payload.enrollment_date)
        except ValueError:
            return {"ok": False, "message": "Invalid enrollment_date. Use YYYY-MM-DD."}
    try:
        enroll_in_section(student, section, enroll_date)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Student {} enrolled in section {}.".format(
        student.student_number, section.section_code)}


@router.post("/enrollments/{enrollment_id}/drop", response=ActionResponse)
def drop_enrollment(request, enrollment_id: uuid.UUID):
    from apps.education_sis.models import Enrollment
    from apps.education_sis.hooks.enrollment import drop_from_section
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, is_deleted=False)
    if enrollment.status in ("dropped", "completed", "failed"):
        return {"ok": False, "message": "Enrollment already {}.".format(enrollment.status)}
    drop_from_section(enrollment)
    return {"ok": True, "message": "Enrollment dropped from {}.".format(
        enrollment.section.section_code)}


@router.post("/enrollments/{enrollment_id}/complete", response=ActionResponse)
def complete_enrollment(request, enrollment_id: uuid.UUID):
    from apps.education_sis.models import Enrollment
    from apps.education_sis.hooks.enrollment import complete_enrollment as do_complete
    from apps.education_sis.hooks.grade import compute_final_grade
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, is_deleted=False)
    if enrollment.status not in ("registered", "attending"):
        return {"ok": False, "message": "Enrollment must be active to complete."}
    compute_final_grade(enrollment)
    do_complete(enrollment)
    return {"ok": True, "message": "Enrollment completed. Final grade: {}.".format(
        enrollment.final_grade or "N/A")}


# ── Scheduling conflict check ─────────────────────────────────────────────────

@router.post("/sections/{section_id}/check-conflicts", response=ActionResponse)
def check_section_conflicts(request, section_id: uuid.UUID):
    from apps.education_sis.models import CourseSection
    from apps.education_sis.hooks.scheduling import check_scheduling_conflicts
    section = get_object_or_404(CourseSection, id=section_id, is_deleted=False)
    try:
        check_scheduling_conflicts(section)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "No scheduling conflicts detected for section {}.".format(
        section.section_code)}


# ── Grade entry ───────────────────────────────────────────────────────────────

class GradeEntryIn(Schema):
    enrollment_id: str
    assessment_name: str
    max_score: float
    score: float
    weight_pct: float = 0


@router.post("/grades/submit", response=ActionResponse)
def submit_grade(request, payload: GradeEntryIn):
    from apps.education_sis.models import Enrollment, GradeEntry
    enrollment = get_object_or_404(
        Enrollment, id=uuid.UUID(payload.enrollment_id), is_deleted=False
    )
    if payload.score > payload.max_score:
        return {"ok": False, "message": "Score cannot exceed max_score."}
    GradeEntry.objects.create(
        enrollment=enrollment,
        assessment_name=payload.assessment_name,
        max_score=Decimal(str(payload.max_score)),
        score=Decimal(str(payload.score)),
        weight_pct=Decimal(str(payload.weight_pct)),
        company_id=enrollment.company_id,
    )
    return {"ok": True, "message": "Grade submitted: {}/{} for {}.".format(
        payload.score, payload.max_score, payload.assessment_name)}


@router.post("/enrollments/{enrollment_id}/compute-grade", response=ActionResponse)
def compute_grade(request, enrollment_id: uuid.UUID):
    from apps.education_sis.models import Enrollment
    from apps.education_sis.hooks.grade import compute_final_grade
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, is_deleted=False)
    compute_final_grade(enrollment)
    return {"ok": True, "message": "Final grade computed: {} ({} GPA points).".format(
        enrollment.final_grade or "N/A",
        float(enrollment.grade_points) if enrollment.grade_points else 0)}


# ── Standards-based grading ───────────────────────────────────────────────────

class StandardsGradeIn(Schema):
    enrollment_id: str
    standard_id: str
    proficiency_level: str  # exceeding / meeting / approaching / not_yet
    evidence: Optional[str] = None
    assessed_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/standards-grades/record", response=ActionResponse)
def record_standards_grade(request, payload: StandardsGradeIn):
    from apps.education_sis.models import Enrollment, LearningStandard, StandardsGradeEntry
    enrollment = get_object_or_404(
        Enrollment, id=uuid.UUID(payload.enrollment_id), is_deleted=False
    )
    standard = get_object_or_404(
        LearningStandard, id=uuid.UUID(payload.standard_id), is_deleted=False
    )
    valid_levels = ("exceeding", "meeting", "approaching", "not_yet")
    if payload.proficiency_level not in valid_levels:
        return {"ok": False, "message": "proficiency_level must be one of: {}.".format(
            ", ".join(valid_levels))}
    assessed = None
    if payload.assessed_date:
        try:
            assessed = datetime.date.fromisoformat(payload.assessed_date)
        except ValueError:
            return {"ok": False, "message": "Invalid assessed_date. Use YYYY-MM-DD."}

    _, created = StandardsGradeEntry.objects.update_or_create(
        enrollment=enrollment,
        standard=standard,
        defaults={
            "proficiency_level": payload.proficiency_level,
            "evidence": payload.evidence or "",
            "assessed_date": assessed,
            "notes": payload.notes or "",
            "company_id": enrollment.company_id,
        }
    )
    action = "recorded" if created else "updated"
    return {"ok": True, "message": "Standards grade {} for {} as {}.".format(
        action, standard.code, payload.proficiency_level)}


# ── Fee invoices ──────────────────────────────────────────────────────────────

class PaymentIn(Schema):
    amount: float


@router.post("/fee-invoices/{invoice_id}/issue", response=ActionResponse)
def issue_fee_invoice(request, invoice_id: uuid.UUID):
    from apps.education_sis.models import StudentFeeInvoice
    from apps.education_sis.hooks.fee_invoice import issue_fee_invoice as do_issue
    invoice = get_object_or_404(StudentFeeInvoice, id=invoice_id, is_deleted=False)
    if invoice.status != "draft":
        return {"ok": False, "message": "Only Draft invoices can be issued."}
    do_issue(invoice)
    invoice.save()
    return {"ok": True, "message": "Invoice {} issued for {}.".format(
        invoice.invoice_number, invoice.student)}


@router.post("/fee-invoices/{invoice_id}/pay", response=ActionResponse)
def record_payment(request, invoice_id: uuid.UUID, payload: PaymentIn):
    from apps.education_sis.models import StudentFeeInvoice
    from apps.education_sis.hooks.fee_invoice import record_payment as do_pay
    invoice = get_object_or_404(StudentFeeInvoice, id=invoice_id, is_deleted=False)
    if invoice.status in ("paid", "cancelled"):
        return {"ok": False, "message": "Invoice is already {}.".format(invoice.status)}
    do_pay(invoice, amount=payload.amount)
    return {"ok": True, "message": "Payment of {:.2f} recorded. Status: {}.".format(
        payload.amount, invoice.status)}


@router.post("/fee-invoices/{invoice_id}/cancel", response=ActionResponse)
def cancel_fee_invoice(request, invoice_id: uuid.UUID):
    from apps.education_sis.models import StudentFeeInvoice
    from apps.education_sis.hooks.fee_invoice import cancel_fee_invoice as do_cancel
    invoice = get_object_or_404(StudentFeeInvoice, id=invoice_id, is_deleted=False)
    if invoice.status in ("paid", "cancelled"):
        return {"ok": False, "message": "Cannot cancel a {} invoice.".format(invoice.status)}
    do_cancel(invoice)
    invoice.save()
    return {"ok": True, "message": "Invoice {} cancelled.".format(invoice.invoice_number)}


# ── Payment plans ─────────────────────────────────────────────────────────────

class PaymentPlanIn(Schema):
    invoice_id: str
    number_of_instalments: int = 2
    plan_name: Optional[str] = None
    first_due_date: Optional[str] = None


class InstalmentPayIn(Schema):
    amount: float
    payment_reference: Optional[str] = None


@router.post("/payment-plans", response=ActionResponse)
def create_payment_plan(request, payload: PaymentPlanIn):
    from apps.education_sis.models import (
        StudentFeeInvoice, FeePaymentPlan, FeePaymentPlanInstalment
    )
    invoice = get_object_or_404(
        StudentFeeInvoice, id=uuid.UUID(payload.invoice_id), is_deleted=False
    )
    if invoice.status not in ("issued", "overdue", "partially_paid"):
        return {"ok": False,
                "message": "Invoice must be issued/overdue/partially_paid to set up a plan."}
    if payload.number_of_instalments < 2:
        return {"ok": False, "message": "A payment plan must have at least 2 instalments."}

    first_due = datetime.date.today()
    if payload.first_due_date:
        try:
            first_due = datetime.date.fromisoformat(payload.first_due_date)
        except ValueError:
            return {"ok": False, "message": "Invalid first_due_date. Use YYYY-MM-DD."}

    plan = FeePaymentPlan.objects.create(
        invoice=invoice,
        plan_name=payload.plan_name or "{}-instalment plan".format(payload.number_of_instalments),
        number_of_instalments=payload.number_of_instalments,
        status="active",
        company_id=invoice.company_id,
    )

    remaining = invoice.amount - invoice.paid_amount - invoice.discount_amount
    inst_amount = (remaining / Decimal(str(payload.number_of_instalments))).quantize(
        Decimal("0.01")
    )
    for i in range(1, payload.number_of_instalments + 1):
        due = first_due + datetime.timedelta(days=30 * (i - 1))
        FeePaymentPlanInstalment.objects.create(
            payment_plan=plan,
            instalment_number=i,
            due_date=due,
            amount=inst_amount,
            status="pending",
            company_id=invoice.company_id,
        )

    return {"ok": True, "message": "Payment plan created with {} instalments of {:.2f}.".format(
        payload.number_of_instalments, float(inst_amount))}


@router.post("/payment-plans/{plan_id}/instalments/{inst_id}/pay", response=ActionResponse)
def pay_instalment(request, plan_id: uuid.UUID, inst_id: uuid.UUID, payload: InstalmentPayIn):
    from apps.education_sis.models import FeePaymentPlan, FeePaymentPlanInstalment
    plan = get_object_or_404(FeePaymentPlan, id=plan_id, is_deleted=False)
    inst = get_object_or_404(FeePaymentPlanInstalment, id=inst_id, payment_plan=plan)
    if inst.status == "paid":
        return {"ok": False, "message": "Instalment {} is already paid.".format(
            inst.instalment_number)}
    inst.paid_amount = Decimal(str(payload.amount))
    inst.paid_date = datetime.date.today()
    inst.payment_reference = payload.payment_reference or ""
    inst.status = "paid"
    inst.save()

    # If all instalments are settled, mark plan and invoice as completed/paid
    all_done = not plan.instalments.exclude(status__in=("paid", "waived")).exists()
    if all_done:
        plan.status = "completed"
        plan.save(update_fields=["status"])
        invoice = plan.invoice
        invoice.paid_amount += Decimal(str(payload.amount))
        invoice.status = "paid"
        invoice.save(update_fields=["paid_amount", "status"])

    return {"ok": True, "message": "Instalment {} paid ({:.2f}).".format(
        inst.instalment_number, payload.amount)}


# ── Scholarships & financial aid ──────────────────────────────────────────────

class AwardIn(Schema):
    student_id: str
    scholarship_id: str
    academic_year_id: Optional[str] = None
    awarded_amount: float
    notes: Optional[str] = None


class RevokeIn(Schema):
    reason: str = ""


class ApplyAwardIn(Schema):
    invoice_id: str


@router.post("/scholarship-awards", response=ActionResponse)
def create_scholarship_award(request, payload: AwardIn):
    from apps.education_sis.models import Student, Scholarship, AcademicYear, ScholarshipAward
    student = get_object_or_404(Student, id=uuid.UUID(payload.student_id), is_deleted=False)
    scholarship = get_object_or_404(
        Scholarship, id=uuid.UUID(payload.scholarship_id), is_deleted=False
    )
    ay = None
    if payload.academic_year_id:
        ay = get_object_or_404(AcademicYear, id=uuid.UUID(payload.academic_year_id))

    ScholarshipAward.objects.create(
        student=student,
        scholarship=scholarship,
        academic_year=ay,
        awarded_amount=Decimal(str(payload.awarded_amount)),
        currency=scholarship.currency,
        status="pending",
        notes=payload.notes or "",
        company_id=student.company_id,
    )
    return {"ok": True, "message": "Scholarship award created for {} ({}).".format(
        str(student), str(scholarship))}


@router.post("/scholarship-awards/{award_id}/activate", response=ActionResponse)
def activate_scholarship_award(request, award_id: uuid.UUID):
    from apps.education_sis.models import ScholarshipAward
    from apps.education_sis.hooks.financial_aid import activate_award
    award = get_object_or_404(ScholarshipAward, id=award_id, is_deleted=False)
    activate_award(award)
    return {"ok": True, "message": "Scholarship award activated for {}.".format(
        str(award.student))}


@router.post("/scholarship-awards/{award_id}/revoke", response=ActionResponse)
def revoke_scholarship_award(request, award_id: uuid.UUID, payload: RevokeIn):
    from apps.education_sis.models import ScholarshipAward
    from apps.education_sis.hooks.financial_aid import revoke_award
    award = get_object_or_404(ScholarshipAward, id=award_id, is_deleted=False)
    revoke_award(award, reason=payload.reason)
    return {"ok": True, "message": "Scholarship award revoked for {}.".format(
        str(award.student))}


@router.post("/scholarship-awards/{award_id}/apply-to-invoice", response=ActionResponse)
def apply_award_to_invoice(request, award_id: uuid.UUID, payload: ApplyAwardIn):
    from apps.education_sis.models import ScholarshipAward, StudentFeeInvoice
    from apps.education_sis.hooks.financial_aid import apply_award_to_invoice as do_apply
    award = get_object_or_404(ScholarshipAward, id=award_id, is_deleted=False)
    invoice = get_object_or_404(
        StudentFeeInvoice, id=uuid.UUID(payload.invoice_id), is_deleted=False
    )
    do_apply(award, invoice)
    return {"ok": True, "message": "Award of {:.2f} applied to invoice {} as discount.".format(
        float(award.awarded_amount), invoice.invoice_number)}


# ── IEP Cases ─────────────────────────────────────────────────────────────────

class IEPCaseIn(Schema):
    student_id: str
    plan_type: str = "iep"
    primary_disability: Optional[str] = None
    case_manager_name: Optional[str] = None
    plan_start_date: Optional[str] = None
    plan_end_date: Optional[str] = None


@router.post("/iep-cases", response=ActionResponse)
def create_iep_case(request, payload: IEPCaseIn):
    from apps.education_sis.models import Student, IEPCase
    from core.numbering.service import get_next_number
    student = get_object_or_404(Student, id=uuid.UUID(payload.student_id), is_deleted=False)
    start = None
    end = None
    if payload.plan_start_date:
        try:
            start = datetime.date.fromisoformat(payload.plan_start_date)
        except ValueError:
            return {"ok": False, "message": "Invalid plan_start_date. Use YYYY-MM-DD."}
    if payload.plan_end_date:
        try:
            end = datetime.date.fromisoformat(payload.plan_end_date)
        except ValueError:
            return {"ok": False, "message": "Invalid plan_end_date. Use YYYY-MM-DD."}
    case = IEPCase.objects.create(
        student=student,
        plan_type=payload.plan_type,
        status=IEPCase.Status.DRAFT,
        case_number=get_next_number("IEP", company_id=student.company_id),
        primary_disability=payload.primary_disability or "",
        case_manager_name=payload.case_manager_name or "",
        plan_start_date=start,
        plan_end_date=end,
        company_id=student.company_id,
    )
    student.has_iep = True
    student.save(update_fields=["has_iep"])
    return {"ok": True, "message": "IEP case {} created for {}.".format(
        case.case_number, student)}


@router.post("/iep-cases/{case_id}/activate", response=ActionResponse)
def activate_iep_case(request, case_id: uuid.UUID):
    from apps.education_sis.models import IEPCase
    case = get_object_or_404(IEPCase, id=case_id, is_deleted=False)
    if case.status not in ("draft", "under_review"):
        return {"ok": False, "message": "IEP case cannot be activated from {} status.".format(
            case.status)}
    case.status = IEPCase.Status.ACTIVE
    case.save(update_fields=["status"])
    return {"ok": True, "message": "IEP case {} activated.".format(case.case_number)}


@router.post("/iep-cases/{case_id}/close", response=ActionResponse)
def close_iep_case(request, case_id: uuid.UUID):
    from apps.education_sis.models import IEPCase
    case = get_object_or_404(IEPCase, id=case_id, is_deleted=False)
    case.status = IEPCase.Status.COMPLETED
    case.save(update_fields=["status"])
    return {"ok": True, "message": "IEP case {} closed.".format(case.case_number)}


# ── Attendance ────────────────────────────────────────────────────────────────

class AttendanceMark(Schema):
    enrollment_id: str
    date: str
    status: str = "present"
    remarks: Optional[str] = None


@router.post("/attendance/mark", response=ActionResponse)
def mark_attendance(request, payload: AttendanceMark):
    from apps.education_sis.models import Enrollment, ClassAttendance
    enrollment = get_object_or_404(
        Enrollment, id=uuid.UUID(payload.enrollment_id), is_deleted=False
    )
    try:
        att_date = datetime.date.fromisoformat(payload.date)
    except ValueError:
        return {"ok": False, "message": "Invalid date. Use YYYY-MM-DD."}
    att, created = ClassAttendance.objects.get_or_create(
        enrollment=enrollment,
        date=att_date,
        defaults={
            "status": payload.status,
            "remarks": payload.remarks or "",
            "company_id": enrollment.company_id,
        }
    )
    if not created:
        att.status = payload.status
        att.remarks = payload.remarks or ""
        att.save(update_fields=["status", "remarks"])
    return {"ok": True, "message": "Attendance marked {} for {} on {}.".format(
        payload.status, enrollment.student, att_date)}


# ── Transcript ────────────────────────────────────────────────────────────────

class TranscriptIn(Schema):
    academic_year_id: Optional[str] = None


@router.post("/students/{student_id}/generate-transcript", response=ActionResponse)
def generate_transcript(request, student_id: uuid.UUID, payload: TranscriptIn):
    from apps.education_sis.models import Student, AcademicYear
    from apps.education_sis.hooks.transcript import generate_transcript as do_generate
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    ay = None
    if payload.academic_year_id:
        ay = get_object_or_404(AcademicYear, id=uuid.UUID(payload.academic_year_id))
    transcript = do_generate(student, academic_year=ay)
    return {"ok": True, "message": "Transcript {} generated. GPA: {}, Credit Hours: {}.".format(
        transcript.transcript_number,
        float(transcript.cumulative_gpa) if transcript.cumulative_gpa else 0,
        transcript.total_credit_hours)}


@router.post("/transcripts/{transcript_id}/seal", response=ActionResponse)
def seal_transcript(request, transcript_id: uuid.UUID):
    from apps.education_sis.models import AcademicTranscript
    from apps.education_sis.hooks.transcript import seal_transcript as do_seal
    transcript = get_object_or_404(AcademicTranscript, id=transcript_id, is_deleted=False)
    if transcript.status == "sealed":
        return {"ok": False, "message": "Transcript is already sealed."}
    do_seal(transcript)
    return {"ok": True, "message": "Transcript {} sealed and certified.".format(
        transcript.transcript_number)}


# ── Analytics ─────────────────────────────────────────────────────────────────

class AcademicAnalytics(Schema):
    total_students: int
    active_students: int
    enrolled_students: int
    graduated_students: int
    withdrawn_students: int
    total_enrollments: int
    active_enrollments: int
    total_iep_cases: int
    active_iep_cases: int
    total_applications: int
    pending_applications: int
    total_fee_invoices: int
    outstanding_invoices: int
    total_billed: float
    total_collected: float
    total_scholarships_awarded: float
    sections_at_capacity: int


@router.get("/analytics/summary", response=AcademicAnalytics)
def analytics_summary(request, academic_year_id: Optional[str] = None,
                      company_id: Optional[str] = None):
    from django.db.models import Sum, F
    from apps.education_sis.models import (
        Student, Enrollment, IEPCase, StudentFeeInvoice, CourseSection,
        AdmissionApplication, ScholarshipAward,
    )

    def qs(model):
        q = model.objects.filter(is_deleted=False)
        if company_id:
            q = q.filter(company_id=company_id)
        return q

    enroll_qs = qs(Enrollment)
    if academic_year_id:
        enroll_qs = enroll_qs.filter(section__academic_year_id=academic_year_id)

    fee_qs = qs(StudentFeeInvoice)
    fee_totals = fee_qs.aggregate(billed=Sum("amount"), collected=Sum("paid_amount"))
    award_totals = qs(ScholarshipAward).filter(status="active").aggregate(
        total=Sum("awarded_amount")
    )
    sections_full = qs(CourseSection).filter(enrolled_count__gte=F("capacity")).count()

    return AcademicAnalytics(
        total_students=qs(Student).count(),
        active_students=qs(Student).filter(status="active").count(),
        enrolled_students=qs(Student).filter(status="enrolled").count(),
        graduated_students=qs(Student).filter(status="graduated").count(),
        withdrawn_students=qs(Student).filter(status="withdrawn").count(),
        total_enrollments=enroll_qs.count(),
        active_enrollments=enroll_qs.filter(status__in=["registered", "attending"]).count(),
        total_iep_cases=qs(IEPCase).count(),
        active_iep_cases=qs(IEPCase).filter(status="active").count(),
        total_applications=qs(AdmissionApplication).count(),
        pending_applications=qs(AdmissionApplication).filter(
            status__in=["submitted", "under_review", "offer_made", "waitlisted"]
        ).count(),
        total_fee_invoices=fee_qs.count(),
        outstanding_invoices=fee_qs.filter(
            status__in=["issued", "partially_paid", "overdue"]
        ).count(),
        total_billed=float(fee_totals["billed"] or 0),
        total_collected=float(fee_totals["collected"] or 0),
        total_scholarships_awarded=float(award_totals["total"] or 0),
        sections_at_capacity=sections_full,
    )


# ── Student / Guardian self-service portal (§10 — Consumer API) ──────────────

class EnrollmentRow(Schema):
    course_code: str
    course_name: str
    section_code: str
    status: str
    final_grade: Optional[str]
    grade_points: Optional[float]
    enrollment_date: str


class AttendanceSummary(Schema):
    course_code: str
    section_code: str
    total_classes: int
    present: int
    absent: int
    late: int
    excused: int
    attendance_pct: float


class InvoiceRow(Schema):
    invoice_number: str
    amount: float
    discount_amount: float
    paid_amount: float
    balance: float
    due_date: str
    status: str


class StudentPortalOverview(Schema):
    student_number: str
    first_name: str
    last_name: str
    program: Optional[str]
    status: str
    cumulative_gpa: Optional[float]
    enrollment_date: Optional[str]
    expected_graduation_date: Optional[str]


class TranscriptRow(Schema):
    transcript_number: str
    status: str
    cumulative_gpa: Optional[float]
    total_credit_hours: int
    generated_at: Optional[str]
    transcript_data: dict


@router.get("/portal/students/{student_id}/overview", response=StudentPortalOverview,
            auth=None)
def portal_student_overview(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    return StudentPortalOverview(
        student_number=student.student_number,
        first_name=student.first_name,
        last_name=student.last_name,
        program=str(student.program) if student.program else None,
        status=student.status,
        cumulative_gpa=float(student.cumulative_gpa) if student.cumulative_gpa else None,
        enrollment_date=str(student.enrollment_date) if student.enrollment_date else None,
        expected_graduation_date=(
            str(student.expected_graduation_date)
            if student.expected_graduation_date else None
        ),
    )


@router.get("/portal/students/{student_id}/grades", response=List[EnrollmentRow], auth=None)
def portal_student_grades(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student, Enrollment
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    enrollments = Enrollment.objects.filter(
        student=student, is_deleted=False
    ).select_related("section__course").order_by("-enrollment_date")
    rows = []
    for enr in enrollments:
        rows.append(EnrollmentRow(
            course_code=enr.section.course.code,
            course_name=enr.section.course.name,
            section_code=enr.section.section_code,
            status=enr.status,
            final_grade=enr.final_grade or None,
            grade_points=float(enr.grade_points) if enr.grade_points else None,
            enrollment_date=str(enr.enrollment_date),
        ))
    return rows


@router.get("/portal/students/{student_id}/attendance",
            response=List[AttendanceSummary], auth=None)
def portal_student_attendance(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student, Enrollment, ClassAttendance
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    enrollments = Enrollment.objects.filter(
        student=student, is_deleted=False
    ).select_related("section__course")
    rows = []
    for enr in enrollments:
        att_qs = ClassAttendance.objects.filter(enrollment=enr, is_deleted=False)
        total = att_qs.count()
        present = att_qs.filter(status="present").count()
        absent = att_qs.filter(status="absent").count()
        late = att_qs.filter(status="late").count()
        excused = att_qs.filter(status="excused").count()
        pct = round((present + late) / total * 100, 1) if total else 0.0
        rows.append(AttendanceSummary(
            course_code=enr.section.course.code,
            section_code=enr.section.section_code,
            total_classes=total,
            present=present,
            absent=absent,
            late=late,
            excused=excused,
            attendance_pct=pct,
        ))
    return rows


@router.get("/portal/students/{student_id}/invoices", response=List[InvoiceRow], auth=None)
def portal_student_invoices(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student, StudentFeeInvoice
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    invoices = StudentFeeInvoice.objects.filter(
        student=student, is_deleted=False
    ).order_by("-due_date")
    rows = []
    for inv in invoices:
        balance = float(inv.amount - inv.discount_amount - inv.paid_amount)
        rows.append(InvoiceRow(
            invoice_number=inv.invoice_number,
            amount=float(inv.amount),
            discount_amount=float(inv.discount_amount),
            paid_amount=float(inv.paid_amount),
            balance=max(balance, 0.0),
            due_date=str(inv.due_date),
            status=inv.status,
        ))
    return rows


@router.get("/portal/students/{student_id}/transcript",
            response=Optional[TranscriptRow], auth=None)
def portal_student_transcript(request, student_id: uuid.UUID):
    from apps.education_sis.models import Student, AcademicTranscript
    student = get_object_or_404(Student, id=student_id, is_deleted=False)
    transcript = AcademicTranscript.objects.filter(
        student=student, is_deleted=False
    ).order_by("-generated_at").first()
    if not transcript:
        return None
    return TranscriptRow(
        transcript_number=transcript.transcript_number,
        status=transcript.status,
        cumulative_gpa=(
            float(transcript.cumulative_gpa) if transcript.cumulative_gpa else None
        ),
        total_credit_hours=transcript.total_credit_hours,
        generated_at=str(transcript.generated_at) if transcript.generated_at else None,
        transcript_data=transcript.transcript_data,
    )
