"""Microfinance hooks — loan lifecycle, amortization schedule, GL posting."""
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from dateutil.relativedelta import relativedelta

from django.db import transaction

from apps.microfinance.models import (
    LoanAccount,
    LoanProduct,
    LoanRepaymentSchedule,
)
from core.numbering.service import get_next_number


def approve_loan(loan: LoanAccount) -> None:
    loan.status = "approved"


def disburse_loan(loan: LoanAccount) -> None:
    loan.status = "active"
    loan.outstanding_principal = loan.principal_amount


@transaction.atomic
def generate_repayment_schedule(loan: LoanAccount) -> None:
    """
    Build amortization schedule rows for the loan based on product interest type.
    Supports flat-rate and declining-balance methods.
    """
    if LoanRepaymentSchedule.objects.filter(loan=loan).exists():
        return  # already generated

    product: LoanProduct = loan.product
    n = loan.term_periods
    p = loan.principal_amount
    annual_rate = product.annual_interest_rate

    # Derive periodic rate based on repayment frequency
    frequency_divisors = {
        "weekly": Decimal("52"),
        "biweekly": Decimal("26"),
        "monthly": Decimal("12"),
        "quarterly": Decimal("4"),
        "bullet": Decimal("1"),
    }
    divisor = frequency_divisors.get(product.repayment_frequency, Decimal("12"))
    periodic_rate = annual_rate / Decimal("100") / divisor

    frequency_deltas = {
        "weekly": relativedelta(weeks=1),
        "biweekly": relativedelta(weeks=2),
        "monthly": relativedelta(months=1),
        "quarterly": relativedelta(months=3),
        "bullet": relativedelta(months=n),
    }
    delta = frequency_deltas.get(product.repayment_frequency, relativedelta(months=1))

    base_date: date = loan.disbursement_date or date.today()
    outstanding = p
    rows = []

    for i in range(1, n + 1):
        due = base_date + (delta * i)

        if product.interest_type == "flat":
            interest_due = (p * annual_rate / Decimal("100") / divisor).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
            principal_due = (p / Decimal(n)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        else:
            # Declining / reducing balance
            interest_due = (outstanding * periodic_rate).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
            if product.repayment_frequency == "bullet":
                principal_due = outstanding
            else:
                if periodic_rate:
                    total_payment = (
                        p * periodic_rate / (1 - (1 + periodic_rate) ** (-n))
                    ).quantize(Decimal("0.0001"), ROUND_HALF_UP)
                    principal_due = total_payment - interest_due
                else:
                    principal_due = (p / Decimal(n)).quantize(
                        Decimal("0.0001"), ROUND_HALF_UP
                    )

        outstanding -= principal_due
        rows.append(
            LoanRepaymentSchedule(
                loan=loan,
                period_number=i,
                due_date=due,
                principal_due=principal_due,
                interest_due=interest_due,
                total_due=principal_due + interest_due,
                company_id=loan.company_id,
            )
        )

    LoanRepaymentSchedule.objects.bulk_create(rows)

    # Set maturity date from last schedule row
    if rows:
        LoanAccount.objects.filter(pk=loan.pk).update(maturity_date=rows[-1].due_date)


@transaction.atomic
def post_disbursement_to_gl(loan: LoanAccount) -> None:
    """Post loan disbursement to GL: Dr Loan Receivable, Cr Cash/Bank."""
    if not loan.loan_account_gl_id:
        loan.loan_account_gl_id = uuid.uuid4()  # placeholder
        loan.save(update_fields=["loan_account_gl_id"])


def mark_delinquent(loan: LoanAccount) -> None:
    loan.status = "delinquent"


def cure_delinquency(loan: LoanAccount) -> None:
    loan.status = "active"


def close_loan(loan: LoanAccount) -> None:
    loan.status = "closed"
    loan.outstanding_principal = Decimal("0")


def write_off_loan(loan: LoanAccount) -> None:
    loan.status = "written_off"
