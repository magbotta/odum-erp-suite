"""Microfinance / Financial Services action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.microfinance.models import LoanAccount, TellerTransaction
from core.platform_api.security import AuthBearer

router = Router(tags=["Microfinance Actions"], auth=AuthBearer())


@router.post("/loans/{loan_id}/approve")
def approve_loan(request, loan_id: UUID):
    loan = get_object_or_404(LoanAccount, pk=loan_id)
    if loan.status != "pending":
        return {"error": "Only Pending loans can be approved."}
    from apps.microfinance.hooks.loan_account import approve_loan as do_approve
    do_approve(loan)
    loan.save()
    return {"status": loan.status}


@router.post("/loans/{loan_id}/disburse")
def disburse_loan(request, loan_id: UUID):
    loan = get_object_or_404(LoanAccount, pk=loan_id)
    if loan.status != "approved":
        return {"error": "Only Approved loans can be disbursed."}
    from apps.microfinance.hooks.loan_account import (
        disburse_loan as do_disburse,
        generate_repayment_schedule,
        post_disbursement_to_gl,
    )
    do_disburse(loan)
    loan.save()
    generate_repayment_schedule(loan)
    post_disbursement_to_gl(loan)
    return {
        "status": loan.status,
        "loan_number": loan.loan_number,
        "outstanding_principal": str(loan.outstanding_principal),
    }


@router.post("/loans/{loan_id}/write-off")
def write_off_loan(request, loan_id: UUID):
    loan = get_object_or_404(LoanAccount, pk=loan_id)
    if loan.status not in ("delinquent", "active"):
        return {"error": "Only Delinquent or Active loans can be written off."}
    from apps.microfinance.hooks.loan_account import write_off_loan as do_write_off
    do_write_off(loan)
    loan.save()
    return {"status": loan.status}


@router.post("/teller-transactions/{tx_id}/complete")
def complete_teller_transaction(request, tx_id: UUID):
    tx = get_object_or_404(TellerTransaction, pk=tx_id)
    if tx.status != "pending":
        return {"error": "Only Pending transactions can be completed."}
    from apps.microfinance.hooks.teller_transaction import (
        complete_transaction,
        post_teller_transaction_to_gl,
    )
    complete_transaction(tx)
    tx.save()
    post_teller_transaction_to_gl(tx)
    return {"status": tx.status, "transaction_number": tx.transaction_number}


@router.post("/teller-transactions/{tx_id}/reverse")
def reverse_teller_transaction(request, tx_id: UUID):
    tx = get_object_or_404(TellerTransaction, pk=tx_id)
    if tx.status != "completed":
        return {"error": "Only Completed transactions can be reversed."}
    from apps.microfinance.hooks.teller_transaction import reverse_transaction
    reverse_transaction(tx)
    tx.save()
    return {"status": tx.status}
