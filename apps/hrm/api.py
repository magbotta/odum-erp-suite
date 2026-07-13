"""HRM action endpoints (§6.4): leave approval, recruitment pipeline, performance, termination, analytics."""
import uuid
from datetime import date
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError


router = Router(tags=["HRM Actions"])


# ── Shared ────────────────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str
    id: Optional[uuid.UUID] = None


# ── Leave application actions ─────────────────────────────────────────────────

class RejectLeaveSchema(Schema):
    rejection_reason: Optional[str] = None


@router.post("/leave-applications/{leave_id}/approve", response=ActionResponse, summary="Approve Leave Application")
def approve_leave(request, leave_id: uuid.UUID):
    from apps.hrm.models import LeaveApplication
    leave = get_object_or_404(LeaveApplication, id=leave_id, is_deleted=False)
    if leave.status != LeaveApplication.Status.PENDING:
        raise HttpError(400, f"Cannot approve a leave with status '{leave.status}'.")
    leave.status = LeaveApplication.Status.APPROVED
    leave.approved_by = request.user
    leave.approved_at = timezone.now()
    leave.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    from apps.hrm.hooks.leave_application import update_leave_balance
    update_leave_balance(leave)
    return {"ok": True, "message": "Leave approved.", "id": leave.id}


@router.post("/leave-applications/{leave_id}/reject", response=ActionResponse, summary="Reject Leave Application")
def reject_leave(request, leave_id: uuid.UUID, payload: RejectLeaveSchema):
    from apps.hrm.models import LeaveApplication
    leave = get_object_or_404(LeaveApplication, id=leave_id, is_deleted=False)
    if leave.status != LeaveApplication.Status.PENDING:
        raise HttpError(400, f"Cannot reject a leave with status '{leave.status}'.")
    leave.status = LeaveApplication.Status.REJECTED
    leave.rejection_reason = payload.rejection_reason or ""
    leave.save(update_fields=["status", "rejection_reason", "updated_at"])
    from apps.hrm.hooks.leave_application import update_leave_balance
    update_leave_balance(leave)
    return {"ok": True, "message": "Leave rejected.", "id": leave.id}


@router.post("/leave-applications/{leave_id}/cancel", response=ActionResponse, summary="Cancel Leave Application")
def cancel_leave(request, leave_id: uuid.UUID):
    from apps.hrm.models import LeaveApplication
    leave = get_object_or_404(LeaveApplication, id=leave_id, is_deleted=False)
    if leave.status in (LeaveApplication.Status.REJECTED, LeaveApplication.Status.CANCELLED):
        raise HttpError(400, "Leave is already rejected or cancelled.")
    prev_status = leave.status
    leave.status = LeaveApplication.Status.CANCELLED
    leave.save(update_fields=["status", "updated_at"])
    if prev_status in (LeaveApplication.Status.PENDING, LeaveApplication.Status.APPROVED):
        from apps.hrm.hooks.leave_application import update_leave_balance
        update_leave_balance(leave)
    return {"ok": True, "message": "Leave cancelled.", "id": leave.id}


# ── Recruitment pipeline actions ──────────────────────────────────────────────

class MoveApplicantSchema(Schema):
    status: str


@router.post("/job-applicants/{applicant_id}/move-stage", response=ActionResponse, summary="Move Applicant to Stage")
def move_applicant_stage(request, applicant_id: uuid.UUID, payload: MoveApplicantSchema):
    from apps.hrm.models import JobApplicant
    valid = [s.value for s in JobApplicant.Status]
    if payload.status not in valid:
        raise HttpError(400, f"Invalid status '{payload.status}'. Valid: {valid}")
    applicant = get_object_or_404(JobApplicant, id=applicant_id, is_deleted=False)
    applicant.status = payload.status
    applicant.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": f"Applicant moved to '{payload.status}'.", "id": applicant.id}


@router.post("/job-applicants/{applicant_id}/shortlist", response=ActionResponse, summary="Shortlist Applicant")
def shortlist_applicant(request, applicant_id: uuid.UUID):
    from apps.hrm.models import JobApplicant
    applicant = get_object_or_404(JobApplicant, id=applicant_id, is_deleted=False)
    applicant.status = JobApplicant.Status.SHORTLISTED
    applicant.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": "Applicant shortlisted.", "id": applicant.id}


class RejectApplicantSchema(Schema):
    rejection_reason: Optional[str] = None


@router.post("/job-applicants/{applicant_id}/reject", response=ActionResponse, summary="Reject Applicant")
def reject_applicant(request, applicant_id: uuid.UUID, payload: RejectApplicantSchema):
    from apps.hrm.models import JobApplicant
    applicant = get_object_or_404(JobApplicant, id=applicant_id, is_deleted=False)
    if applicant.status in (JobApplicant.Status.HIRED, JobApplicant.Status.WITHDRAWN):
        raise HttpError(400, "Cannot reject a hired or withdrawn applicant.")
    applicant.status = JobApplicant.Status.REJECTED
    applicant.rejection_reason = payload.rejection_reason or ""
    applicant.save(update_fields=["status", "rejection_reason", "updated_at"])
    return {"ok": True, "message": "Applicant rejected.", "id": applicant.id}


@router.post("/job-applicants/{applicant_id}/make-offer", response=ActionResponse, summary="Extend Offer to Applicant")
def make_offer(request, applicant_id: uuid.UUID):
    from apps.hrm.models import JobApplicant
    applicant = get_object_or_404(JobApplicant, id=applicant_id, is_deleted=False)
    if applicant.status not in (JobApplicant.Status.INTERVIEW, JobApplicant.Status.SHORTLISTED):
        raise HttpError(400, "Applicant must be in Interview or Shortlisted stage to receive an offer.")
    applicant.status = JobApplicant.Status.OFFER
    applicant.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": "Offer extended to applicant.", "id": applicant.id}


@router.post("/job-applicants/{applicant_id}/hire", response=ActionResponse, summary="Mark Applicant as Hired")
def hire_applicant(request, applicant_id: uuid.UUID):
    from apps.hrm.models import JobApplicant, JobPosition
    applicant = get_object_or_404(JobApplicant, id=applicant_id, is_deleted=False)
    if applicant.status != JobApplicant.Status.OFFER:
        raise HttpError(400, "Applicant must have an offer extended before hiring.")
    applicant.status = JobApplicant.Status.HIRED
    applicant.save(update_fields=["status", "updated_at"])
    # Auto-fill the job position if headcount allows
    if applicant.job_position_id:
        position = JobPosition.objects.filter(id=applicant.job_position_id).first()
        if position:
            filled = position.applicants.filter(status=JobApplicant.Status.HIRED).count()
            if filled >= position.headcount:
                position.status = JobPosition.Status.FILLED
                position.save(update_fields=["status"])
    return {"ok": True, "message": "Applicant hired.", "id": applicant.id}


# ── Performance review actions ────────────────────────────────────────────────

@router.post("/performance-reviews/{review_id}/submit", response=ActionResponse, summary="Submit Performance Review")
def submit_review(request, review_id: uuid.UUID):
    from apps.hrm.models import PerformanceReview
    review = get_object_or_404(PerformanceReview, id=review_id, is_deleted=False)
    if review.status != PerformanceReview.Status.DRAFT:
        raise HttpError(400, "Only draft reviews can be submitted.")
    review.status = PerformanceReview.Status.SUBMITTED
    review.submitted_at = timezone.now()
    review.save(update_fields=["status", "submitted_at", "updated_at"])
    return {"ok": True, "message": "Review submitted.", "id": review.id}


@router.post("/performance-reviews/{review_id}/acknowledge", response=ActionResponse, summary="Employee Acknowledges Review")
def acknowledge_review(request, review_id: uuid.UUID):
    from apps.hrm.models import PerformanceReview
    review = get_object_or_404(PerformanceReview, id=review_id, is_deleted=False)
    if review.status != PerformanceReview.Status.SUBMITTED:
        raise HttpError(400, "Only submitted reviews can be acknowledged.")
    review.status = PerformanceReview.Status.ACKNOWLEDGED
    review.acknowledged_at = timezone.now()
    review.save(update_fields=["status", "acknowledged_at", "updated_at"])
    return {"ok": True, "message": "Review acknowledged by employee.", "id": review.id}


# ── Employee lifecycle actions ────────────────────────────────────────────────

class TerminateSchema(Schema):
    termination_date: str
    exit_reason: Optional[str] = None


@router.post("/employees/{emp_id}/terminate", response=ActionResponse, summary="Terminate Employee")
def terminate_employee(request, emp_id: uuid.UUID, payload: TerminateSchema):
    from apps.hrm.models import Employee
    employee = get_object_or_404(Employee, id=emp_id, is_deleted=False)
    if employee.status == Employee.Status.TERMINATED:
        raise HttpError(400, "Employee is already terminated.")
    employee.status = Employee.Status.TERMINATED
    employee.date_of_termination = date.fromisoformat(payload.termination_date)
    if payload.exit_reason:
        employee.exit_reason = payload.exit_reason
    employee.save(update_fields=["status", "date_of_termination", "exit_reason", "updated_at"])
    return {"ok": True, "message": f"Employee {employee.full_name} terminated.", "id": employee.id}


class ResignSchema(Schema):
    resignation_date: str
    exit_reason: Optional[str] = None


@router.post("/employees/{emp_id}/resign", response=ActionResponse, summary="Mark Employee as Resigned")
def resign_employee(request, emp_id: uuid.UUID, payload: ResignSchema):
    from apps.hrm.models import Employee
    employee = get_object_or_404(Employee, id=emp_id, is_deleted=False)
    if employee.status in (Employee.Status.TERMINATED, Employee.Status.RESIGNED):
        raise HttpError(400, f"Employee status is already '{employee.status}'.")
    employee.status = Employee.Status.RESIGNED
    employee.date_of_resignation = date.fromisoformat(payload.resignation_date)
    if payload.exit_reason:
        employee.exit_reason = payload.exit_reason
    employee.save(update_fields=["status", "date_of_resignation", "exit_reason", "updated_at"])
    return {"ok": True, "message": f"Employee {employee.full_name} marked as resigned.", "id": employee.id}


# ── Disciplinary case actions ─────────────────────────────────────────────────

class ResolveSchema(Schema):
    resolution: Optional[str] = None


@router.post("/disciplinary-cases/{case_id}/resolve", response=ActionResponse, summary="Resolve Disciplinary Case")
def resolve_case(request, case_id: uuid.UUID, payload: ResolveSchema):
    from apps.hrm.models import DisciplinaryCase
    case = get_object_or_404(DisciplinaryCase, id=case_id, is_deleted=False)
    if case.status in (DisciplinaryCase.Status.RESOLVED, DisciplinaryCase.Status.CLOSED):
        raise HttpError(400, "Case is already resolved or closed.")
    case.status = DisciplinaryCase.Status.RESOLVED
    case.resolved_at = timezone.now()
    if payload.resolution:
        case.resolution = payload.resolution
    case.save(update_fields=["status", "resolved_at", "resolution", "updated_at"])
    return {"ok": True, "message": "Disciplinary case resolved.", "id": case.id}


@router.post("/disciplinary-cases/{case_id}/close", response=ActionResponse, summary="Close Disciplinary Case")
def close_case(request, case_id: uuid.UUID):
    from apps.hrm.models import DisciplinaryCase
    case = get_object_or_404(DisciplinaryCase, id=case_id, is_deleted=False)
    if case.status != DisciplinaryCase.Status.RESOLVED:
        raise HttpError(400, "Only resolved cases can be closed.")
    case.status = DisciplinaryCase.Status.CLOSED
    case.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": "Disciplinary case closed.", "id": case.id}


# ── Analytics ─────────────────────────────────────────────────────────────────

class HeadcountRow(Schema):
    department: str
    active: int
    on_leave: int
    probation: int
    total: int


class HeadcountResponse(Schema):
    rows: List[HeadcountRow]
    grand_total: int


@router.get("/analytics/headcount", response=HeadcountResponse, summary="Headcount by Department")
def headcount(request):
    from apps.hrm.models import Employee, Department
    from django.db.models import Count, Q

    depts = Department.objects.filter(is_deleted=False)
    rows = []
    grand = 0
    for dept in depts:
        qs = Employee.objects.filter(department=dept, is_deleted=False)
        active = qs.filter(status="active").count()
        on_leave = qs.filter(status="on_leave").count()
        probation = qs.filter(status="probation").count()
        total = active + on_leave + probation
        grand += total
        if total > 0:
            rows.append({
                "department": dept.name,
                "active": active,
                "on_leave": on_leave,
                "probation": probation,
                "total": total,
            })
    return {"rows": rows, "grand_total": grand}


class LeaveSummaryRow(Schema):
    leave_type: str
    total_applications: int
    approved: int
    pending: int
    rejected: int
    total_days_taken: float


class LeaveSummaryResponse(Schema):
    rows: List[LeaveSummaryRow]
    year: int


@router.get("/analytics/leave-summary", response=LeaveSummaryResponse, summary="Leave Summary by Type")
def leave_summary(request, year: int = None):
    from apps.hrm.models import LeaveApplication, LeaveType
    from django.db.models import Count, Sum, Q

    if not year:
        year = date.today().year

    leave_types = LeaveType.objects.filter(is_deleted=False)
    rows = []
    for lt in leave_types:
        qs = LeaveApplication.objects.filter(
            leave_type=lt, is_deleted=False, from_date__year=year
        )
        total = qs.count()
        if total == 0:
            continue
        approved = qs.filter(status="approved").count()
        pending = qs.filter(status="pending").count()
        rejected = qs.filter(status="rejected").count()
        days = qs.filter(status="approved").aggregate(d=Sum("total_days"))["d"] or 0
        rows.append({
            "leave_type": lt.name,
            "total_applications": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "total_days_taken": float(days),
        })
    return {"rows": rows, "year": year}
