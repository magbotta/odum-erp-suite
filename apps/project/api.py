"""Project Management action endpoints (§6.6)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

router = Router(tags=["Project"])


# ── Shared ────────────────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str


# ── Timesheet workflow ────────────────────────────────────────────────────────

@router.post("/timesheets/{ts_id}/submit", response=ActionResponse)
def submit_timesheet(request, ts_id: uuid.UUID):
    """Submit a draft timesheet for approval."""
    from apps.project.hooks.timesheet import submit_timesheet as _submit
    from apps.project.models import Timesheet

    ts = get_object_or_404(Timesheet, id=ts_id, is_deleted=False)
    try:
        _submit(ts)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Timesheet {} submitted.".format(ts.timesheet_number)}


@router.post("/timesheets/{ts_id}/approve", response=ActionResponse)
def approve_timesheet(request, ts_id: uuid.UUID):
    """Approve a submitted timesheet."""
    from apps.project.hooks.timesheet import approve_timesheet as _approve
    from apps.project.models import Timesheet

    ts = get_object_or_404(Timesheet, id=ts_id, is_deleted=False)
    try:
        _approve(ts, approver_id=request.user.pk)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Timesheet {} approved.".format(ts.timesheet_number)}


class RejectIn(Schema):
    reason: str


@router.post("/timesheets/{ts_id}/reject", response=ActionResponse)
def reject_timesheet(request, ts_id: uuid.UUID, payload: RejectIn):
    """Reject a submitted timesheet with a reason."""
    from apps.project.hooks.timesheet import reject_timesheet as _reject
    from apps.project.models import Timesheet

    ts = get_object_or_404(Timesheet, id=ts_id, is_deleted=False)
    try:
        _reject(ts, reason=payload.reason)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Timesheet {} rejected.".format(ts.timesheet_number)}


@router.post("/timesheets/{ts_id}/create-invoice", response=ActionResponse)
def create_invoice(request, ts_id: uuid.UUID):
    """Generate a Sales Invoice from an approved timesheet's billable hours."""
    from apps.project.hooks.timesheet import create_invoice_from_timesheet
    from apps.project.models import Timesheet

    ts = get_object_or_404(Timesheet, id=ts_id, is_deleted=False)
    try:
        invoice_number = create_invoice_from_timesheet(ts)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": "Invoice {} created from timesheet {}.".format(
        invoice_number, ts.timesheet_number
    )}


# ── Risk / Issue log ──────────────────────────────────────────────────────────

class RiskIssueIn(Schema):
    project_id: str
    record_type: str = "risk"
    title: str
    description: Optional[str] = None
    severity: str = "medium"
    probability: Optional[float] = None
    impact: Optional[str] = None
    mitigation_plan: Optional[str] = None
    owner_name: Optional[str] = None
    due_date: Optional[str] = None
    is_confidential: bool = False


class RiskIssueOut(Schema):
    id: str
    record_type: str
    title: str
    severity: str
    status: str


@router.post("/risks", response=RiskIssueOut)
def log_risk_issue(request, payload: RiskIssueIn):
    """Log a new risk or issue against a project."""
    import datetime
    from apps.project.models import Project, RiskIssue

    project = get_object_or_404(Project, id=payload.project_id, is_deleted=False)

    due = None
    if payload.due_date:
        try:
            due = datetime.date.fromisoformat(payload.due_date)
        except ValueError:
            pass

    ri = RiskIssue.objects.create(
        project=project,
        record_type=payload.record_type,
        title=payload.title,
        description=payload.description or "",
        severity=payload.severity,
        probability=payload.probability,
        impact=payload.impact or "",
        mitigation_plan=payload.mitigation_plan or "",
        owner_name=payload.owner_name or "",
        due_date=due,
        is_confidential=payload.is_confidential,
        company_id=project.company_id,
    )
    return RiskIssueOut(
        id=str(ri.pk),
        record_type=ri.record_type,
        title=ri.title,
        severity=ri.severity,
        status=ri.status,
    )


@router.post("/risks/{ri_id}/resolve", response=ActionResponse)
def resolve_risk_issue(request, ri_id: uuid.UUID):
    """Mark a risk or issue as resolved."""
    import datetime
    from apps.project.models import RiskIssue

    ri = get_object_or_404(RiskIssue, id=ri_id, is_deleted=False)
    ri.status = RiskIssue.Status.RESOLVED
    ri.resolved_at = datetime.date.today()
    ri.save(update_fields=["status", "resolved_at"])
    return {"ok": True, "message": "{} '{}' marked resolved.".format(
        ri.get_record_type_display(), ri.title
    )}


# ── Project from template ─────────────────────────────────────────────────────

class FromTemplateIn(Schema):
    template_id: str
    project_name: str
    start_date: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    currency: str = "USD"
    company_id: Optional[str] = None


@router.post("/from-template", response=ActionResponse)
def create_from_template(request, payload: FromTemplateIn):
    """Create a project (with tasks) from a saved template."""
    from apps.project.hooks.project import create_project_from_template

    company_id = payload.company_id or str(getattr(request.user, "company_id", ""))

    try:
        project = create_project_from_template(
            template_id=payload.template_id,
            project_name=payload.project_name,
            start_date=payload.start_date,
            company_id=company_id,
            customer_id=payload.customer_id,
            customer_name=payload.customer_name or "",
            currency=payload.currency,
        )
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    return {"ok": True, "message": "Project '{}' (#{}) created from template.".format(
        project.project_name, str(project.pk)[:8]
    )}


# ── Budget report ─────────────────────────────────────────────────────────────

class BudgetReport(Schema):
    project_name: str
    project_code: str
    status: str
    budget: float
    actual_cost: float
    billed_amount: float
    percent_complete: float
    budget_utilization_pct: float
    over_budget: bool


@router.get("/projects/{project_id}/budget", response=BudgetReport)
def project_budget(request, project_id: uuid.UUID):
    """Return budget vs actual summary for a project."""
    from apps.project.models import Project

    p = get_object_or_404(Project, id=project_id, is_deleted=False)
    utilization = (
        float(p.actual_cost) / float(p.budget) * 100
        if p.budget and p.budget > 0
        else 0.0
    )
    return BudgetReport(
        project_name=p.project_name,
        project_code=p.project_code,
        status=p.status,
        budget=float(p.budget),
        actual_cost=float(p.actual_cost),
        billed_amount=float(p.billed_amount),
        percent_complete=float(p.percent_complete),
        budget_utilization_pct=round(utilization, 2),
        over_budget=p.actual_cost > p.budget if p.budget > 0 else False,
    )


# ── Resource capacity report ──────────────────────────────────────────────────

class MemberCapacityRow(Schema):
    employee_name: str
    role: str
    allocated_hours: float
    timesheet_hours: float
    utilization_pct: float


class CapacityReport(Schema):
    project_name: str
    members: List[MemberCapacityRow]
    total_allocated: float
    total_logged: float


@router.get("/projects/{project_id}/capacity", response=CapacityReport)
def resource_capacity(request, project_id: uuid.UUID):
    """Return resource allocation vs logged hours per project member."""
    from django.db.models import Sum
    from apps.project.models import Project, ProjectMember, TimesheetEntry

    p = get_object_or_404(Project, id=project_id, is_deleted=False)
    members = ProjectMember.objects.filter(project=p, is_deleted=False, is_active=True)

    rows = []
    total_allocated = Decimal("0")
    total_logged = Decimal("0")

    for m in members:
        logged_result = TimesheetEntry.objects.filter(
            project=p,
            timesheet__employee_id=m.employee_id,
            is_deleted=False,
        ).aggregate(total=Sum("hours"))
        logged = logged_result["total"] or Decimal("0")

        utilization = (
            float(logged) / float(m.allocated_hours) * 100
            if m.allocated_hours and m.allocated_hours > 0
            else 0.0
        )
        rows.append(MemberCapacityRow(
            employee_name=m.employee_name,
            role=m.role,
            allocated_hours=float(m.allocated_hours),
            timesheet_hours=float(logged),
            utilization_pct=round(utilization, 2),
        ))
        total_allocated += m.allocated_hours
        total_logged += logged

    return CapacityReport(
        project_name=p.project_name,
        members=rows,
        total_allocated=float(total_allocated),
        total_logged=float(total_logged),
    )


# ── Project analytics summary ─────────────────────────────────────────────────

class ProjectSummaryRow(Schema):
    project_name: str
    status: str
    percent_complete: float
    budget: float
    actual_cost: float
    billed_amount: float
    task_count: int
    open_tasks: int
    open_risks: int


class ProjectAnalytics(Schema):
    projects: List[ProjectSummaryRow]
    active_count: int
    total_budget: float
    total_billed: float


@router.get("/analytics/summary", response=ProjectAnalytics)
def analytics_summary(request, company_id: Optional[str] = None, status: Optional[str] = None):
    """High-level portfolio summary across all projects."""
    from django.db.models import Count, Q, Sum
    from apps.project.models import Project, ProjectTask, RiskIssue

    qs = Project.objects.filter(is_deleted=False)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if status:
        qs = qs.filter(status=status)

    totals = qs.aggregate(tb=Sum("budget"), tbi=Sum("billed_amount"))

    rows = []
    for p in qs.order_by("-created_at")[:50]:
        task_count = ProjectTask.objects.filter(project=p, is_deleted=False).count()
        open_tasks = ProjectTask.objects.filter(
            project=p, is_deleted=False
        ).exclude(status__in=["done", "cancelled"]).count()
        open_risks = RiskIssue.objects.filter(
            project=p, is_deleted=False
        ).exclude(status__in=["resolved", "closed"]).count()

        rows.append(ProjectSummaryRow(
            project_name=p.project_name,
            status=p.status,
            percent_complete=float(p.percent_complete),
            budget=float(p.budget),
            actual_cost=float(p.actual_cost),
            billed_amount=float(p.billed_amount),
            task_count=task_count,
            open_tasks=open_tasks,
            open_risks=open_risks,
        ))

    return ProjectAnalytics(
        projects=rows,
        active_count=qs.filter(status="active").count(),
        total_budget=float(totals["tb"] or 0),
        total_billed=float(totals["tbi"] or 0),
    )
