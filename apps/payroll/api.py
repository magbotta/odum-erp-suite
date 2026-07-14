"""Payroll action endpoints (§6.5)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["Payroll"])


# ── Shared ────────────────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str


# ── Payroll Entry ─────────────────────────────────────────────────────────────

@router.post("/entries/{entry_id}/process", response=ActionResponse)
def process_payroll(request, entry_id: uuid.UUID):
    """Compute salary slips for all employees in scope (Draft → Processing)."""
    from apps.payroll.hooks.payroll_entry import compute_salary_slips, set_payroll_number
    from apps.payroll.models import PayrollEntry

    entry = get_object_or_404(PayrollEntry, id=entry_id, is_deleted=False)
    if entry.status != PayrollEntry.Status.DRAFT:
        return {"ok": False, "message": "Entry is already {}.".format(entry.status)}

    set_payroll_number(entry)
    entry.save(update_fields=["payroll_number"])
    compute_salary_slips(entry)
    entry.status = PayrollEntry.Status.PROCESSING
    entry.save(update_fields=["status"])
    slip_count = entry.salary_slips.count()
    return {"ok": True, "message": "Processed {} salary slips for {}.".format(
        slip_count, entry.payroll_number
    )}


@router.post("/entries/{entry_id}/complete", response=ActionResponse)
def complete_payroll(request, entry_id: uuid.UUID):
    """Verify slips and mark payroll completed (Processing → Completed)."""
    from apps.payroll.hooks.payroll_entry import verify_slips
    from apps.payroll.models import PayrollEntry

    entry = get_object_or_404(PayrollEntry, id=entry_id, is_deleted=False)
    if entry.status != PayrollEntry.Status.PROCESSING:
        return {"ok": False, "message": "Entry is {}, not in Processing.".format(entry.status)}

    try:
        verify_slips(entry)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    entry.status = PayrollEntry.Status.COMPLETED
    entry.save(update_fields=["status"])
    return {"ok": True, "message": "Payroll {} completed — ready to post to GL.".format(
        entry.payroll_number
    )}


@router.post("/entries/{entry_id}/submit", response=ActionResponse)
def submit_payroll(request, entry_id: uuid.UUID):
    """Post payroll to GL (Completed → Submitted)."""
    from apps.payroll.hooks.payroll_entry import post_to_gl
    from apps.payroll.models import PayrollEntry

    entry = get_object_or_404(PayrollEntry, id=entry_id, is_deleted=False)
    if entry.status != PayrollEntry.Status.COMPLETED:
        return {"ok": False, "message": "Entry is {}, not Completed.".format(entry.status)}

    post_to_gl(entry)
    entry.status = PayrollEntry.Status.SUBMITTED
    entry.save(update_fields=["status"])
    return {"ok": True, "message": "Payroll {} submitted and posted to GL.".format(
        entry.payroll_number
    )}


@router.post("/entries/{entry_id}/cancel", response=ActionResponse)
def cancel_payroll(request, entry_id: uuid.UUID):
    """Cancel a draft or processing payroll entry."""
    from apps.payroll.models import PayrollEntry

    entry = get_object_or_404(PayrollEntry, id=entry_id, is_deleted=False)
    if entry.status in (PayrollEntry.Status.SUBMITTED,):
        return {"ok": False, "message": "Cannot cancel a submitted payroll. Reverse via GL instead."}

    entry.status = PayrollEntry.Status.CANCELLED
    entry.save(update_fields=["status"])
    return {"ok": True, "message": "Payroll {} cancelled.".format(entry.payroll_number)}


class SlipSummaryRow(Schema):
    slip_number: str
    employee_name: str
    base_salary: float
    gross_pay: float
    total_deduction: float
    loan_deduction_amount: float
    net_pay: float
    working_hours: float
    overtime_hours: float


@router.get("/entries/{entry_id}/slips", response=List[SlipSummaryRow])
def list_slips(request, entry_id: uuid.UUID):
    """List all salary slips for a payroll entry."""
    from apps.payroll.models import PayrollEntry, SalarySlip

    entry = get_object_or_404(PayrollEntry, id=entry_id, is_deleted=False)
    slips = SalarySlip.objects.filter(
        payroll_entry=entry, is_deleted=False
    ).select_related("employee")

    return [
        SlipSummaryRow(
            slip_number=s.slip_number or str(s.pk),
            employee_name=str(s.employee),
            base_salary=float(s.base_salary),
            gross_pay=float(s.gross_pay),
            total_deduction=float(s.total_deduction),
            loan_deduction_amount=float(s.loan_deduction_amount),
            net_pay=float(s.net_pay),
            working_hours=float(s.working_hours),
            overtime_hours=float(s.overtime_hours),
        )
        for s in slips
    ]


# ── Employee Loans ────────────────────────────────────────────────────────────

@router.post("/loans/{loan_id}/approve", response=ActionResponse)
def approve_loan(request, loan_id: uuid.UUID):
    """Approve a loan and generate its repayment schedule."""
    from apps.payroll.hooks.loan import generate_repayment_schedule
    from apps.payroll.models import EmployeeLoan
    from core.numbering.service import get_next_number

    loan = get_object_or_404(EmployeeLoan, id=loan_id, is_deleted=False)
    if loan.status != EmployeeLoan.Status.DRAFT:
        return {"ok": False, "message": "Loan is already {}.".format(loan.status)}

    if not loan.loan_number:
        loan.loan_number = get_next_number("LOAN", loan.company_id)

    generate_repayment_schedule(loan)
    loan.status = EmployeeLoan.Status.APPROVED
    loan.approved_by_id = request.user.pk if request.user.is_authenticated else None
    loan.approved_at = timezone.now()
    loan.save(update_fields=["status", "loan_number", "approved_by_id", "approved_at"])
    return {"ok": True, "message": "Loan {} approved. {} installments scheduled.".format(
        loan.loan_number, loan.repayment_periods
    )}


class DisburseIn(Schema):
    disbursement_date: str
    start_period_id: Optional[str] = None


@router.post("/loans/{loan_id}/disburse", response=ActionResponse)
def disburse_loan(request, loan_id: uuid.UUID, payload: DisburseIn):
    """Mark loan as disbursed and set the repayment start period."""
    import datetime
    from apps.payroll.models import EmployeeLoan, PayrollPeriod

    loan = get_object_or_404(EmployeeLoan, id=loan_id, is_deleted=False)
    if loan.status != EmployeeLoan.Status.APPROVED:
        return {"ok": False, "message": "Loan is {}, not approved.".format(loan.status)}

    try:
        disb_date = datetime.date.fromisoformat(payload.disbursement_date)
    except ValueError:
        return {"ok": False, "message": "Invalid date format. Use YYYY-MM-DD."}

    loan.disbursement_date = disb_date
    loan.status = EmployeeLoan.Status.ACTIVE

    if payload.start_period_id:
        try:
            period = PayrollPeriod.objects.get(id=payload.start_period_id)
            loan.repayment_start_period = period
        except PayrollPeriod.DoesNotExist:
            pass

    loan.save(update_fields=["disbursement_date", "status", "repayment_start_period"])
    return {"ok": True, "message": "Loan {} disbursed on {}.".format(
        loan.loan_number, disb_date
    )}


class LoanScheduleRow(Schema):
    installment_no: int
    principal_component: float
    interest_component: float
    total_amount: float
    status: str
    deducted_on: Optional[str]


@router.get("/loans/{loan_id}/schedule", response=List[LoanScheduleRow])
def loan_schedule(request, loan_id: uuid.UUID):
    """Return the full repayment schedule for a loan."""
    from apps.payroll.models import EmployeeLoan, LoanRepaymentSchedule

    loan = get_object_or_404(EmployeeLoan, id=loan_id, is_deleted=False)
    rows = LoanRepaymentSchedule.objects.filter(loan=loan).order_by("installment_no")
    return [
        LoanScheduleRow(
            installment_no=r.installment_no,
            principal_component=float(r.principal_component),
            interest_component=float(r.interest_component),
            total_amount=float(r.total_amount),
            status=r.status,
            deducted_on=str(r.deducted_on) if r.deducted_on else None,
        )
        for r in rows
    ]


# ── Analytics ─────────────────────────────────────────────────────────────────

class PayrollSummaryRow(Schema):
    payroll_number: str
    period: str
    run_type: str
    status: str
    slip_count: int
    total_gross: float
    total_deductions: float
    total_net: float


class PayrollAnalytics(Schema):
    entries: List[PayrollSummaryRow]
    ytd_gross: float
    ytd_net: float
    active_loans: int
    active_loan_balance: float


@router.get("/analytics/summary", response=PayrollAnalytics)
def payroll_summary(request, company_id: Optional[str] = None):
    from django.db.models import Count, Sum
    from apps.payroll.models import EmployeeLoan, PayrollEntry

    qs = PayrollEntry.objects.filter(is_deleted=False).exclude(status="cancelled")
    if company_id:
        qs = qs.filter(company_id=company_id)

    entries = qs.annotate(slip_count=Count("salary_slips")).order_by("-created_at")[:20]
    totals = qs.aggregate(tg=Sum("total_gross_pay"), tn=Sum("total_net_pay"))

    loan_qs = EmployeeLoan.objects.filter(status=EmployeeLoan.Status.ACTIVE, is_deleted=False)
    if company_id:
        loan_qs = loan_qs.filter(company_id=company_id)
    loan_totals = loan_qs.aggregate(bal=Sum("outstanding_balance"))

    return PayrollAnalytics(
        entries=[
            PayrollSummaryRow(
                payroll_number=e.payroll_number or str(e.pk),
                period=str(e.period),
                run_type=e.run_type,
                status=e.status,
                slip_count=e.slip_count,
                total_gross=float(e.total_gross_pay),
                total_deductions=float(e.total_deductions),
                total_net=float(e.total_net_pay),
            )
            for e in entries
        ],
        ytd_gross=float(totals["tg"] or 0),
        ytd_net=float(totals["tn"] or 0),
        active_loans=loan_qs.count(),
        active_loan_balance=float(loan_totals["bal"] or 0),
    )
