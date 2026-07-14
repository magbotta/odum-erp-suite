"""Expense & Travel action endpoints (§6.11)."""
from __future__ import annotations

import uuid
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["Expense & Travel"])


# ── Shared schemas ─────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str


# ── Expense Claim ──────────────────────────────────────────────────────────

@router.post("/claims/{claim_id}/submit", response=ActionResponse)
def submit_claim(request, claim_id: uuid.UUID):
    from apps.expense.hooks.expense_claim import submit_claim as _submit
    from apps.expense.models import ExpenseClaim

    claim = get_object_or_404(ExpenseClaim, id=claim_id, is_deleted=False)
    if claim.status != ExpenseClaim.Status.DRAFT:
        return {"ok": False, "message": "Claim is already {}.".format(claim.status)}
    if not claim.lines.exists():
        return {"ok": False, "message": "Claim has no line items."}

    _submit(claim)
    claim.status = ExpenseClaim.Status.SUBMITTED
    claim.save(update_fields=["status"])
    return {"ok": True, "message": "Claim {} submitted.".format(claim.claim_number)}


class RejectIn(Schema):
    reason: str


@router.post("/claims/{claim_id}/approve", response=ActionResponse)
def approve_claim(request, claim_id: uuid.UUID):
    from apps.expense.hooks.expense_claim import approve_claim as _approve
    from apps.expense.models import ExpenseClaim

    claim = get_object_or_404(ExpenseClaim, id=claim_id, is_deleted=False)
    if claim.status != ExpenseClaim.Status.SUBMITTED:
        return {"ok": False, "message": "Claim is {}, not awaiting approval.".format(claim.status)}

    approver_id = request.user.pk if request.user.is_authenticated else None
    _approve(claim, approver_id=approver_id)
    return {"ok": True, "message": "Claim {} approved.".format(claim.claim_number)}


@router.post("/claims/{claim_id}/reject", response=ActionResponse)
def reject_claim(request, claim_id: uuid.UUID, payload: RejectIn):
    from apps.expense.hooks.expense_claim import reject_claim as _reject
    from apps.expense.models import ExpenseClaim

    claim = get_object_or_404(ExpenseClaim, id=claim_id, is_deleted=False)
    if claim.status != ExpenseClaim.Status.SUBMITTED:
        return {"ok": False, "message": "Claim is {}, not awaiting approval.".format(claim.status)}

    approver_id = request.user.pk if request.user.is_authenticated else None
    _reject(claim, reason=payload.reason, approver_id=approver_id)
    return {"ok": True, "message": "Claim {} rejected.".format(claim.claim_number)}


class ReimburseIn(Schema):
    payment_reference: Optional[str] = ""
    reimbursed_at: Optional[str] = None


@router.post("/claims/{claim_id}/reimburse", response=ActionResponse)
def reimburse_claim(request, claim_id: uuid.UUID, payload: ReimburseIn):
    import datetime
    from apps.expense.hooks.expense_claim import reimburse_claim as _reimburse
    from apps.expense.models import ExpenseClaim

    claim = get_object_or_404(ExpenseClaim, id=claim_id, is_deleted=False)
    if claim.status != ExpenseClaim.Status.APPROVED:
        return {"ok": False, "message": "Claim is {}, not yet approved.".format(claim.status)}

    paid_date = None
    if payload.reimbursed_at:
        try:
            paid_date = datetime.date.fromisoformat(payload.reimbursed_at)
        except ValueError:
            return {"ok": False, "message": "Invalid date format for reimbursed_at."}

    _reimburse(claim, payment_reference=payload.payment_reference or "", reimbursed_at=paid_date)
    return {"ok": True, "message": "Claim {} reimbursed. Ref: {}.".format(
        claim.claim_number, claim.payment_reference
    )}


class PolicyViolationRow(Schema):
    claim_id: str
    claim_number: str
    employee_name: str
    line_id: str
    category: str
    amount: float
    violation_reason: str


@router.get("/claims/policy-violations", response=List[PolicyViolationRow])
def list_policy_violations(request, company_id: Optional[str] = None):
    from apps.expense.models import ExpenseClaimLine

    qs = ExpenseClaimLine.objects.filter(
        policy_violation=True, is_deleted=False
    ).exclude(claim__status="cancelled").select_related("claim", "category")

    if company_id:
        qs = qs.filter(claim__company_id=company_id)

    return [
        PolicyViolationRow(
            claim_id=str(line.claim_id),
            claim_number=line.claim.claim_number,
            employee_name=line.claim.employee_name,
            line_id=str(line.pk),
            category=line.category.name,
            amount=float(line.amount),
            violation_reason=line.violation_reason,
        )
        for line in qs
    ]


# ── Travel Request ─────────────────────────────────────────────────────────

@router.post("/travel-requests/{tr_id}/submit", response=ActionResponse)
def submit_travel_request(request, tr_id: uuid.UUID):
    from apps.expense.models import TravelRequest
    from core.numbering.service import get_next_number

    tr = get_object_or_404(TravelRequest, id=tr_id, is_deleted=False)
    if tr.status != TravelRequest.Status.DRAFT:
        return {"ok": False, "message": "Travel request is already {}.".format(tr.status)}

    if not tr.request_number:
        tr.request_number = get_next_number("TR", tr.company_id)

    tr.status = TravelRequest.Status.SUBMITTED
    tr.save(update_fields=["status", "request_number"])
    return {"ok": True, "message": "Travel request {} submitted.".format(tr.request_number)}


@router.post("/travel-requests/{tr_id}/approve", response=ActionResponse)
def approve_travel_request(request, tr_id: uuid.UUID):
    from apps.expense.models import TravelRequest

    tr = get_object_or_404(TravelRequest, id=tr_id, is_deleted=False)
    if tr.status != TravelRequest.Status.SUBMITTED:
        return {"ok": False, "message": "Travel request is {}, not awaiting approval.".format(tr.status)}

    tr.status = TravelRequest.Status.APPROVED
    tr.approved_by_id = request.user.pk if request.user.is_authenticated else None
    tr.approved_at = timezone.now()
    tr.save(update_fields=["status", "approved_by_id", "approved_at"])
    return {"ok": True, "message": "Travel request {} approved.".format(tr.request_number)}


@router.post("/travel-requests/{tr_id}/reject", response=ActionResponse)
def reject_travel_request(request, tr_id: uuid.UUID, payload: RejectIn):
    from apps.expense.models import TravelRequest

    tr = get_object_or_404(TravelRequest, id=tr_id, is_deleted=False)
    if tr.status != TravelRequest.Status.SUBMITTED:
        return {"ok": False, "message": "Travel request is {}, not awaiting approval.".format(tr.status)}

    tr.status = TravelRequest.Status.REJECTED
    tr.rejection_reason = payload.reason
    tr.approved_at = timezone.now()
    tr.save(update_fields=["status", "rejection_reason", "approved_at"])
    return {"ok": True, "message": "Travel request {} rejected.".format(tr.request_number)}


# ── Corporate Card ─────────────────────────────────────────────────────────

class CardChargeIn(Schema):
    date: str
    merchant_name: str
    merchant_category: Optional[str] = ""
    amount: float
    currency: Optional[str] = "USD"


class ImportStatementIn(Schema):
    statement_period: str
    from_date: str
    to_date: str
    charges: List[CardChargeIn]


@router.post("/corporate-cards/{card_id}/import-statement", response=ActionResponse)
def import_statement(request, card_id: uuid.UUID, payload: ImportStatementIn):
    import datetime
    from apps.expense.hooks.corporate_card import import_statement as _import
    from apps.expense.models import CorporateCard

    card = get_object_or_404(CorporateCard, id=card_id, is_deleted=False)

    try:
        from_date = datetime.date.fromisoformat(payload.from_date)
        to_date = datetime.date.fromisoformat(payload.to_date)
    except ValueError:
        return {"ok": False, "message": "Invalid date format. Use YYYY-MM-DD."}

    charges = [
        {
            "date": datetime.date.fromisoformat(c.date),
            "merchant_name": c.merchant_name,
            "merchant_category": c.merchant_category or "",
            "amount": c.amount,
            "currency": c.currency or "USD",
        }
        for c in payload.charges
    ]

    stmt = _import(card, payload.statement_period, from_date, to_date, charges)
    return {"ok": True, "message": "Imported {} charges for {}.".format(
        len(charges), payload.statement_period
    )}


class AutoMatchResponse(Schema):
    ok: bool
    matched: int
    unmatched: int
    message: str


@router.post("/corporate-cards/statements/{stmt_id}/auto-match", response=AutoMatchResponse)
def auto_match_statement(request, stmt_id: uuid.UUID):
    from apps.expense.hooks.corporate_card import auto_match_statement as _match
    from apps.expense.models import CorporateCardStatement

    stmt = get_object_or_404(CorporateCardStatement, id=stmt_id)
    result = _match(stmt)
    return AutoMatchResponse(
        ok=True,
        matched=result["matched"],
        unmatched=result["unmatched"],
        message="Matched {} of {} charges.".format(
            result["matched"], result["matched"] + result["unmatched"]
        ),
    )


# ── Analytics ─────────────────────────────────────────────────────────────

class SpendRow(Schema):
    employee_name: str
    employee_id: str
    total_claimed: float
    total_sanctioned: float
    claim_count: int


class CategorySpendRow(Schema):
    category: str
    total_amount: float
    line_count: int


class SpendSummary(Schema):
    by_employee: List[SpendRow]
    by_category: List[CategorySpendRow]
    total_claimed: float
    total_sanctioned: float
    violation_count: int


@router.get("/analytics/spend", response=SpendSummary)
def spend_analytics(request, company_id: Optional[str] = None):
    from django.db.models import Count, Sum
    from apps.expense.models import ExpenseClaim, ExpenseClaimLine

    claim_qs = ExpenseClaim.objects.filter(is_deleted=False).exclude(status="cancelled")
    line_qs = ExpenseClaimLine.objects.filter(is_deleted=False).exclude(claim__status="cancelled")

    if company_id:
        claim_qs = claim_qs.filter(company_id=company_id)
        line_qs = line_qs.filter(claim__company_id=company_id)

    # By employee
    by_emp = (
        claim_qs.values("employee_id", "employee_name")
        .annotate(
            total_claimed=Sum("total_claimed_amount"),
            total_sanctioned=Sum("total_sanctioned_amount"),
            claim_count=Count("id"),
        )
        .order_by("-total_claimed")
    )

    # By category
    by_cat = (
        line_qs.select_related("category")
        .values("category__name")
        .annotate(total_amount=Sum("amount"), line_count=Count("id"))
        .order_by("-total_amount")
    )

    totals = claim_qs.aggregate(
        tc=Sum("total_claimed_amount"),
        ts=Sum("total_sanctioned_amount"),
    )
    violation_count = line_qs.filter(policy_violation=True).count()

    return SpendSummary(
        by_employee=[
            SpendRow(
                employee_name=r["employee_name"],
                employee_id=str(r["employee_id"]),
                total_claimed=float(r["total_claimed"] or 0),
                total_sanctioned=float(r["total_sanctioned"] or 0),
                claim_count=r["claim_count"],
            )
            for r in by_emp
        ],
        by_category=[
            CategorySpendRow(
                category=r["category__name"],
                total_amount=float(r["total_amount"] or 0),
                line_count=r["line_count"],
            )
            for r in by_cat
        ],
        total_claimed=float(totals["tc"] or 0),
        total_sanctioned=float(totals["ts"] or 0),
        violation_count=violation_count,
    )
