"""Payroll entry hooks: compute salary slips and post to GL (§6.5)."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.payroll.models import PayrollEntry


def set_payroll_number(entry: "PayrollEntry") -> None:
    if not entry.payroll_number:
        from core.numbering.service import get_next_number
        entry.payroll_number = get_next_number("PAYROLL", company_id=entry.company_id)


def compute_salary_slips(entry: "PayrollEntry") -> None:
    """
    For each employee in the period's scope, find their active SalaryStructureAssignment,
    evaluate every SalaryComponent (fixed or formula-based), and produce a SalarySlip
    with one SalarySlipComponent row per component.
    """
    from apps.payroll.models import (
        SalarySlip,
        SalarySlipComponent,
        SalaryStructureAssignment,
    )
    from core.numbering.service import get_next_number

    # Resolve all active assignments valid during this payroll period
    assignments = SalaryStructureAssignment.objects.filter(
        effective_from__lte=entry.period.end_date,
        is_deleted=False,
    ).filter(
        models_q_effective_to_null_or_gte(entry.period.start_date)
    ).select_related("employee", "structure")

    total_gross = Decimal("0")
    total_ded = Decimal("0")
    total_net = Decimal("0")

    for assignment in assignments:
        structure = assignment.structure
        base = assignment.base_salary

        slip, _ = SalarySlip.objects.get_or_create(
            payroll_entry=entry,
            employee=assignment.employee,
            defaults={
                "period": entry.period,
                "structure": structure,
                "base_salary": base,
                "slip_number": get_next_number("SLIP", company_id=entry.company_id),
                "company_id": entry.company_id,
            },
        )

        gross = Decimal("0")
        deductions = Decimal("0")
        context = {"base": base}

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

        net = gross - deductions
        slip.gross_pay = gross
        slip.total_deduction = deductions
        slip.net_pay = net
        slip.save(update_fields=["gross_pay", "total_deduction", "net_pay", "slip_number"])

        total_gross += gross
        total_ded += deductions
        total_net += net

    entry.total_gross_pay = total_gross
    entry.total_deductions = total_ded
    entry.total_net_pay = total_net
    entry.save(update_fields=["total_gross_pay", "total_deductions", "total_net_pay"])


def verify_slips(entry: "PayrollEntry") -> None:
    """Ensure every slip has a positive net pay before marking Completed."""
    from apps.payroll.models import SalarySlip

    problem_slips = SalarySlip.objects.filter(
        payroll_entry=entry, net_pay__lt=0, is_deleted=False
    )
    if problem_slips.exists():
        raise ValueError(
            f"{problem_slips.count()} salary slip(s) have negative net pay — review deductions."
        )


def post_to_gl(entry: "PayrollEntry") -> None:
    """
    Create a balanced JournalEntry for the payroll run:
    Dr  Salary Expense (per component earning totals)
    Cr  Salary Payable / Statutory Payable
    """
    from apps.accounting.models import JournalEntry, JournalEntryLine
    from apps.payroll.models import SalarySlip, SalarySlipComponent

    slips = SalarySlip.objects.filter(payroll_entry=entry, is_deleted=False)
    if not slips.exists():
        return

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=entry.period.end_date,
        reference=entry.payroll_number,
        narration=f"Payroll run: {entry.payroll_number}",
        status="Draft",
        currency=entry.currency,
        company_id=entry.company_id,
    )

    total_earnings = Decimal("0")
    total_deductions = Decimal("0")

    for slip in slips:
        for sc in SalarySlipComponent.objects.filter(slip=slip, is_deleted=False).select_related(
            "salary_component"
        ):
            comp = sc.salary_component
            if comp.component_type == "earning":
                total_earnings += sc.amount
            else:
                total_deductions += sc.amount

    net_payable = total_earnings - total_deductions

    # Debit: salary expense
    JournalEntryLine.objects.create(
        journal_entry=je,
        account_id=_default_account_id("salary_expense"),
        debit_amount=total_earnings,
        credit_amount=Decimal("0"),
        currency=entry.currency,
        company_id=entry.company_id,
    )
    # Credit: statutory deductions payable
    if total_deductions:
        JournalEntryLine.objects.create(
            journal_entry=je,
            account_id=_default_account_id("statutory_payable"),
            debit_amount=Decimal("0"),
            credit_amount=total_deductions,
            currency=entry.currency,
            company_id=entry.company_id,
        )
    # Credit: salary payable (net)
    JournalEntryLine.objects.create(
        journal_entry=je,
        account_id=_default_account_id("salary_payable"),
        debit_amount=Decimal("0"),
        credit_amount=net_payable,
        currency=entry.currency,
        company_id=entry.company_id,
    )

    je.status = "Submitted"
    je.save(update_fields=["status"])

    entry.journal_entry_id = je.id
    entry.save(update_fields=["journal_entry_id"])


def _default_account_id(account_type: str):
    """Return a sentinel UUID when no specific account is configured (placeholder)."""
    import uuid
    _SENTINELS = {
        "salary_expense": "00000000-0000-0000-0000-000000000010",
        "statutory_payable": "00000000-0000-0000-0000-000000000011",
        "salary_payable": "00000000-0000-0000-0000-000000000012",
    }
    return uuid.UUID(_SENTINELS.get(account_type, "00000000-0000-0000-0000-000000000099"))


def models_q_effective_to_null_or_gte(date):
    """Q object: effective_to is null OR >= date."""
    from django.db.models import Q
    return Q(effective_to__isnull=True) | Q(effective_to__gte=date)
