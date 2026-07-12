"""Legal Services action endpoints."""
from typing import List
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.legal_services.models import (
    ConflictCheck,
    LegalTimeEntry,
    Matter,
    TrustLedgerEntry,
)
from core.platform_api.security import AuthBearer

router = Router(tags=["Legal Services Actions"], auth=AuthBearer())


@router.post("/matters/{matter_id}/open")
def open_matter(request, matter_id: UUID):
    matter = get_object_or_404(Matter, pk=matter_id)
    if matter.status != "intake":
        return {"error": "Only Intake matters can be opened."}
    from apps.legal_services.hooks.matter import run_conflict_check, open_matter as do_open
    try:
        run_conflict_check(matter)
    except ValueError as exc:
        return {"error": str(exc), "status": "conflict_found"}
    do_open(matter)
    matter.save()
    return {"status": matter.status}


@router.post("/matters/{matter_id}/close")
def close_matter(request, matter_id: UUID):
    matter = get_object_or_404(Matter, pk=matter_id)
    if matter.status not in ("open", "on_hold"):
        return {"error": "Matter must be Open or On Hold to close."}
    from apps.legal_services.hooks.matter import close_matter as do_close
    do_close(matter)
    matter.save()
    return {"status": matter.status}


class ConflictCheckBody(Schema):
    search_terms: List[str]


@router.post("/matters/{matter_id}/conflict-check")
def run_conflict_check(request, matter_id: UUID):
    matter = get_object_or_404(Matter, pk=matter_id)
    from apps.legal_services.hooks.matter import run_conflict_check as do_check
    try:
        do_check(matter)
        return {"result": "clear", "hits": []}
    except ValueError as exc:
        check = ConflictCheck.objects.filter(matter=matter).order_by("-ran_at").first()
        return {
            "result": "conflict_found",
            "hits": check.hits if check else [],
            "message": str(exc),
        }


class TrustDepositBody(Schema):
    amount: float
    entry_date: str
    description: str = ""


@router.post("/matters/{matter_id}/trust-deposit")
def trust_deposit(request, matter_id: UUID, body: TrustDepositBody):
    matter = get_object_or_404(Matter, pk=matter_id)
    if not matter.trust_account_id:
        return {"error": "Matter does not have an associated trust account."}
    from decimal import Decimal
    from datetime import date
    from apps.legal_services.hooks.trust_entry import (
        validate_trust_balance,
        update_trust_account_balance,
        post_trust_entry_to_gl,
    )
    entry = TrustLedgerEntry(
        trust_account_id=matter.trust_account_id,
        matter=matter,
        entry_type="deposit",
        amount=Decimal(str(body.amount)),
        currency="USD",
        balance_after=Decimal("0"),
        entry_date=date.fromisoformat(body.entry_date),
        description=body.description,
        company_id=matter.company_id,
    )
    validate_trust_balance(entry)
    entry.save()
    update_trust_account_balance(entry)
    post_trust_entry_to_gl(entry)
    return {"balance_after": str(entry.balance_after)}


@router.post("/time-entries/{entry_id}/invoice")
def mark_time_entry_invoiced(request, entry_id: UUID):
    entry = get_object_or_404(LegalTimeEntry, pk=entry_id)
    if entry.is_invoiced:
        return {"error": "Time entry is already invoiced."}
    entry.is_invoiced = True
    entry.save(update_fields=["is_invoiced"])
    return {"is_invoiced": entry.is_invoiced}
