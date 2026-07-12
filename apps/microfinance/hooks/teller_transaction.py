"""Microfinance hooks — teller transaction completion and GL posting."""
import uuid
from decimal import Decimal

from django.db import transaction

from apps.microfinance.models import LoanAccount, SavingsAccount, TellerTransaction
from core.numbering.service import get_next_number


def set_transaction_number(tx: TellerTransaction) -> None:
    if not tx.transaction_number:
        tx.transaction_number = get_next_number("TELL", company_id=tx.company_id)


@transaction.atomic
def complete_transaction(tx: TellerTransaction) -> None:
    tx.status = "completed"

    if tx.transaction_type == "loan_repayment" and tx.loan_account_id:
        loan = LoanAccount.objects.select_for_update().get(pk=tx.loan_account_id)
        loan.total_repaid = (loan.total_repaid or Decimal("0")) + tx.amount
        loan.outstanding_principal = max(
            Decimal("0"),
            (loan.outstanding_principal or Decimal("0")) - tx.amount,
        )
        if loan.outstanding_principal == Decimal("0"):
            loan.status = "closed"
        loan.save(update_fields=["total_repaid", "outstanding_principal", "status"])

    elif tx.transaction_type == "savings_deposit" and tx.savings_account_id:
        SavingsAccount.objects.filter(pk=tx.savings_account_id).update(
            balance=models_f("balance") + tx.amount
        )

    elif tx.transaction_type == "savings_withdrawal" and tx.savings_account_id:
        acc = SavingsAccount.objects.select_for_update().get(pk=tx.savings_account_id)
        if acc.balance < tx.amount:
            raise ValueError("Insufficient savings balance for withdrawal.")
        SavingsAccount.objects.filter(pk=tx.savings_account_id).update(
            balance=models_f("balance") - tx.amount
        )


@transaction.atomic
def post_teller_transaction_to_gl(tx: TellerTransaction) -> None:
    """Post teller movement to GL. Placeholder — real call goes to Accounting service."""
    if not tx.journal_entry_id:
        tx.journal_entry_id = uuid.uuid4()
        tx.save(update_fields=["journal_entry_id"])


@transaction.atomic
def reverse_transaction(tx: TellerTransaction) -> None:
    tx.status = "reversed"


def models_f(field: str):
    from django.db.models import F
    return F(field)
