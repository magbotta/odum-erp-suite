"""Payroll entry hooks: compute salary slips, statutory deductions, loan deductions, GL post."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.payroll.models import PayrollEntry


def set_payroll_number(entry: "PayrollEntry") -> None:
    if not entry.payroll_number:
        from core.numbering.service import get_next_number
        entry.payroll_number = get_next_number("PAYROLL", company_id=entry.company_id)


def compute_salary_slips(entry: "PayrollEntry") -> None:
    """
    For each employee with an active SalaryStructureAssignment:
    1. Evaluate salary components (fixed or formula-based).
    2. Apply statutory deductions from the entry's StatutoryPack.
    3. Apply pending loan installment deductions.
    4. Source attendance hours from HRM Attendance for hour-based components.
    5. Aggregate slip totals onto the PayrollEntry.
    """
    from apps.payroll.models import (
        LoanRepaymentSchedule,
        SalarySlip,
        SalarySlipComponent,
        SalaryStructureAssignment,
    )
    from core.numbering.service import get_next_number

    assignments = SalaryStructureAssignment.objects.filter(
        effective_from__lte=entry.period.end_date,
        is_deleted=False,
    ).filter(
        _q_effective_to_ok(entry.period.start_date)
    ).select_related("employee", "structure")

    total_gross = Decimal("0")
    total_ded = Decimal("0")
    total_loan = Decimal("0")
    total_net = Decimal("0")

    for assignment in assignments:
        structure = assignment.structure
        base = assignment.base_salary
        employee = assignment.employee

        # ── Attendance hours (cross-app, best-effort) ──────────────────────
        working_hrs, overtime_hrs = _get_attendance_hours(
            employee.id, entry.period.start_date, entry.period.end_date
        )

        slip, _ = SalarySlip.objects.get_or_create(
            payroll_entry=entry,
            employee=employee,
            defaults={
                "period": entry.period,
                "structure": structure,
                "base_salary": base,
                "slip_number": get_next_number("SLIP", company_id=entry.company_id),
                "working_hours": working_hrs,
                "overtime_hours": overtime_hrs,
                "company_id": entry.company_id,
            },
        )

        # ── Salary components ───────────────────────────────────────────────
        gross = Decimal("0")
        deductions = Decimal("0")
        # Use floats in formula context so float literals in formulas (0.2, 1.5) work
        context = {
            "base": float(base),
            "hours": float(working_hrs),
            "overtime": float(overtime_hrs),
        }

        ordered_components = structure.components.order_by("sequence").select_related("component")
        for sc in ordered_components:
            comp = sc.component
            amount = sc.amount_override if sc.amount_override is not None else comp.amount
            if comp.is_based_on_formula and comp.formula:
                try:
                    amount = Decimal(str(eval(comp.formula, {"__builtins__": {}}, context)))  # noqa: S307
                except Exception:
                    amount = Decimal("0")

            context[comp.abbr or comp.name] = amount
            SalarySlipComponent.objects.update_or_create(
                slip=slip, salary_component=comp,
                defaults={"amount": amount, "company_id": entry.company_id},
            )

            if comp.component_type == "earning":
                gross += amount
            elif comp.component_type in ("deduction", "benefit"):
                deductions += amount

        # ── Statutory deductions ────────────────────────────────────────────
        if entry.statutory_pack_id:
            statutory_total = _apply_statutory_deductions(slip, entry, gross, base)
            deductions += statutory_total

        # ── Loan deductions ─────────────────────────────────────────────────
        loan_ded = _apply_loan_deductions(slip, employee, entry.period)
        deductions += loan_ded
        total_loan += loan_ded

        net = gross - deductions
        slip.gross_pay = gross
        slip.total_deduction = deductions
        slip.loan_deduction_amount = loan_ded
        slip.net_pay = net
        slip.working_hours = working_hrs
        slip.overtime_hours = overtime_hrs
        slip.save(update_fields=[
            "gross_pay", "total_deduction", "loan_deduction_amount",
            "net_pay", "working_hours", "overtime_hours", "slip_number",
        ])

        total_gross += gross
        total_ded += deductions
        total_net += net

    entry.total_gross_pay = total_gross
    entry.total_deductions = total_ded
    entry.total_loan_deductions = total_loan
    entry.total_net_pay = total_net
    entry.save(update_fields=[
        "total_gross_pay", "total_deductions", "total_loan_deductions", "total_net_pay"
    ])


def _get_attendance_hours(employee_id, start_date, end_date):
    """
    Read HRM Attendance records for this employee/period and return
    (regular_hours, overtime_hours).  Returns (0, 0) if the Attendance model
    is unavailable or has no records.
    """
    try:
        from apps.hrm.models import Attendance
        records = Attendance.objects.filter(
            employee_id=employee_id,
            check_in__date__gte=start_date,
            check_in__date__lte=end_date,
            is_deleted=False,
        )
        total = Decimal("0")
        overtime = Decimal("0")
        for r in records:
            if r.check_in and r.check_out:
                delta = r.check_out - r.check_in
                hrs = Decimal(str(round(delta.total_seconds() / 3600, 2)))
                standard = Decimal("8")
                if hrs > standard:
                    total += standard
                    overtime += hrs - standard
                else:
                    total += hrs
        return total, overtime
    except Exception:
        return Decimal("0"), Decimal("0")


def _apply_statutory_deductions(slip, entry, gross, base):
    """
    Compute employee-side statutory deductions from the pack and record them
    as SalarySlipComponent rows with a synthetic SalaryComponent per rule.
    Returns total statutory deduction amount.
    """
    from apps.payroll.models import SalaryComponent, SalarySlipComponent, StatutoryRule

    total = Decimal("0")
    rules = StatutoryRule.objects.filter(
        pack=entry.statutory_pack,
        rule_type=StatutoryRule.RuleType.EMPLOYEE_CONTRIBUTION,
        is_active=True,
    ).order_by("sequence")

    for rule in rules:
        amount = rule.compute(gross, base)
        if amount <= 0:
            continue

        # Ensure a SalaryComponent exists for this rule (auto-created if missing)
        comp, _ = SalaryComponent.objects.get_or_create(
            name=rule.name,
            defaults={
                "abbr": rule.abbr or rule.name[:10],
                "component_type": SalaryComponent.ComponentType.DEDUCTION,
                "is_statutory": True,
                "is_based_on_formula": False,
                "amount": 0,
                "company_id": entry.company_id,
            },
        )
        SalarySlipComponent.objects.update_or_create(
            slip=slip, salary_component=comp,
            defaults={"amount": amount, "company_id": entry.company_id},
        )
        total += amount

    return total


def _apply_loan_deductions(slip, employee, period):
    """
    Find the next pending installment for each active loan belonging to this
    employee, apply it as a SalarySlipComponent deduction, and mark the
    installment as DEDUCTED.
    """
    from apps.payroll.models import (
        EmployeeLoan,
        LoanRepaymentSchedule,
        SalaryComponent,
        SalarySlipComponent,
    )

    total = Decimal("0")
    active_loans = EmployeeLoan.objects.filter(
        employee=employee, status=EmployeeLoan.Status.ACTIVE, is_deleted=False
    )

    # Single synthetic "Loan Repayment" component
    loan_comp, _ = SalaryComponent.objects.get_or_create(
        name="Loan Repayment",
        defaults={
            "abbr": "LOAN",
            "component_type": SalaryComponent.ComponentType.DEDUCTION,
            "is_statutory": False,
            "is_based_on_formula": False,
            "amount": 0,
            "company_id": slip.company_id,
        },
    )

    for loan in active_loans:
        installment = (
            LoanRepaymentSchedule.objects.filter(
                loan=loan,
                status=LoanRepaymentSchedule.Status.PENDING,
            )
            .order_by("installment_no")
            .first()
        )
        if not installment:
            loan.status = EmployeeLoan.Status.SETTLED
            loan.save(update_fields=["status"])
            continue

        installment.status = LoanRepaymentSchedule.Status.DEDUCTED
        installment.period = period
        installment.salary_slip_id = slip.pk
        import datetime
        installment.deducted_on = datetime.date.today()
        installment.save(update_fields=["status", "period", "salary_slip_id", "deducted_on"])

        loan.outstanding_balance = max(
            Decimal("0"), loan.outstanding_balance - installment.total_amount
        )
        remaining = LoanRepaymentSchedule.objects.filter(
            loan=loan, status=LoanRepaymentSchedule.Status.PENDING
        ).count()
        if remaining == 0:
            loan.status = EmployeeLoan.Status.SETTLED
        loan.save(update_fields=["outstanding_balance", "status"])

        total += installment.total_amount

    if total > 0:
        SalarySlipComponent.objects.update_or_create(
            slip=slip, salary_component=loan_comp,
            defaults={"amount": total, "company_id": slip.company_id},
        )

    return total


def verify_slips(entry: "PayrollEntry") -> None:
    """Ensure every slip has a non-negative net pay before marking Completed."""
    from apps.payroll.models import SalarySlip

    problem_slips = SalarySlip.objects.filter(
        payroll_entry=entry, net_pay__lt=0, is_deleted=False
    )
    if problem_slips.exists():
        raise ValueError(
            "{} salary slip(s) have negative net pay — review deductions.".format(
                problem_slips.count()
            )
        )


def post_to_gl(entry: "PayrollEntry") -> None:
    """
    Create a balanced JournalEntry for the payroll run.
    Skips gracefully if no GL accounts are configured (common in dev/demo).
    Dr  Salary Expense  (gross pay)
    Cr  Statutory Payable  (statutory deductions)
    Cr  Loan Repayment Payable  (loan deductions, if any)
    Cr  Salary Payable  (net pay)
    """
    try:
        from apps.accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
    except ImportError:
        return

    from apps.payroll.models import SalarySlip

    slips = SalarySlip.objects.filter(payroll_entry=entry, is_deleted=False)
    if not slips.exists():
        return

    # Require real GL account mappings; skip if none exist
    expense_acct = ChartOfAccount.objects.filter(
        account_type="expense", is_active=True, company_id=entry.company_id
    ).first()
    payable_acct = ChartOfAccount.objects.filter(
        account_type="liability", is_active=True, company_id=entry.company_id
    ).first()
    if not expense_acct or not payable_acct:
        return

    from core.numbering.service import get_next_number

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=entry.period.end_date,
        reference=entry.payroll_number,
        narration="Payroll run: {}".format(entry.payroll_number),
        status="submitted",
        voucher_type="PayrollEntry",
        voucher_no=entry.payroll_number,
        company_id=entry.company_id,
    )

    gross = entry.total_gross_pay
    ded = entry.total_deductions
    loans = entry.total_loan_deductions
    net = entry.total_net_pay

    JournalEntryLine.objects.create(
        entry=je,
        account=expense_acct,
        debit_amount=gross,
        credit_amount=Decimal("0"),
        description="Gross payroll: {}".format(entry.payroll_number),
        company_id=entry.company_id,
    )
    statutory_ded = ded - loans
    if statutory_ded > 0:
        JournalEntryLine.objects.create(
            entry=je,
            account=payable_acct,
            debit_amount=Decimal("0"),
            credit_amount=statutory_ded,
            description="Statutory deductions payable",
            company_id=entry.company_id,
        )
    if loans > 0:
        JournalEntryLine.objects.create(
            entry=je,
            account=payable_acct,
            debit_amount=Decimal("0"),
            credit_amount=loans,
            description="Loan repayment recovered",
            company_id=entry.company_id,
        )
    JournalEntryLine.objects.create(
        entry=je,
        account=payable_acct,
        debit_amount=Decimal("0"),
        credit_amount=net,
        description="Net salary payable",
        company_id=entry.company_id,
    )

    entry.journal_entry_id = je.id
    entry.save(update_fields=["journal_entry_id"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _q_effective_to_ok(date):
    from django.db.models import Q
    return Q(effective_to__isnull=True) | Q(effective_to__gte=date)
