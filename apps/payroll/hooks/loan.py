"""Hooks for EmployeeLoan: schedule generation and disbursement posting."""
from __future__ import annotations

from decimal import Decimal


def generate_repayment_schedule(loan) -> None:
    """
    Build LoanRepaymentSchedule installment rows using a reducing-balance
    (EMI) method when interest_rate > 0, or simple equal-principal splitting
    for interest-free advances.
    """
    from apps.payroll.models import LoanRepaymentSchedule

    # Clear any existing pending schedule (allow re-generation on edit)
    LoanRepaymentSchedule.objects.filter(
        loan=loan, status=LoanRepaymentSchedule.Status.PENDING
    ).delete()

    n = loan.repayment_periods
    principal = loan.principal_amount
    annual_rate = loan.interest_rate or Decimal("0")

    if annual_rate > 0:
        # Monthly EMI = P * r * (1+r)^n / ((1+r)^n - 1)
        monthly_rate = annual_rate / Decimal("100") / Decimal("12")
        factor = (1 + monthly_rate) ** n
        emi = (principal * monthly_rate * factor / (factor - 1)).quantize(Decimal("0.01"))
        total_repayable = (emi * n).quantize(Decimal("0.01"))
    else:
        emi = (principal / n).quantize(Decimal("0.01"))
        total_repayable = principal

    loan.monthly_installment = emi
    loan.total_repayable = total_repayable
    loan.outstanding_balance = total_repayable
    loan.save(update_fields=["monthly_installment", "total_repayable", "outstanding_balance"])

    balance = principal
    for i in range(1, n + 1):
        if annual_rate > 0:
            monthly_rate = annual_rate / Decimal("100") / Decimal("12")
            interest = (balance * monthly_rate).quantize(Decimal("0.01"))
            princ = (emi - interest).quantize(Decimal("0.01"))
        else:
            interest = Decimal("0")
            princ = emi

        # Last installment absorbs rounding
        if i == n:
            princ = balance
            interest = emi - princ if annual_rate > 0 else Decimal("0")

        LoanRepaymentSchedule.objects.create(
            loan=loan,
            installment_no=i,
            principal_component=princ,
            interest_component=interest,
            total_amount=princ + interest,
            status=LoanRepaymentSchedule.Status.PENDING,
            company_id=loan.company_id,
        )
        balance = max(Decimal("0"), balance - princ)
