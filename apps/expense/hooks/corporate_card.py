"""Hooks for corporate card statement import and auto-match."""
from __future__ import annotations

from decimal import Decimal


def import_statement(card, statement_period: str, from_date, to_date, charges: list) -> "CorporateCardStatement":
    """
    Import a list of charge dicts into a new CorporateCardStatement.
    Each charge: {date, merchant_name, merchant_category, amount, currency}
    """
    from apps.expense.models import CorporateCardCharge, CorporateCardStatement

    total = sum(Decimal(str(c["amount"])) for c in charges)
    stmt = CorporateCardStatement.objects.create(
        card=card,
        statement_period=statement_period,
        from_date=from_date,
        to_date=to_date,
        total_charges=total,
        currency=card.currency,
        status=CorporateCardStatement.Status.IMPORTED,
        company_id=card.company_id,
    )

    for c in charges:
        CorporateCardCharge.objects.create(
            statement=stmt,
            charge_date=c["date"],
            merchant_name=c["merchant_name"],
            merchant_category=c.get("merchant_category", ""),
            amount=Decimal(str(c["amount"])),
            currency=c.get("currency", card.currency),
            status=CorporateCardCharge.Status.UNMATCHED,
            company_id=card.company_id,
        )

    return stmt


def auto_match_statement(statement) -> dict:
    """
    Match unmatched card charges to approved/submitted expense claim lines
    belonging to the same employee.

    Matching heuristic:
    - Same company
    - Same amount (within 0.01 tolerance)
    - Charge date within ±3 days of expense line date
    - Expense line not already matched
    - Expense claim belongs to the card's employee

    Returns a summary dict: {matched: int, unmatched: int}.
    """
    from datetime import timedelta

    from apps.expense.models import CorporateCardCharge, CorporateCardStatement, ExpenseClaimLine

    card = statement.card
    unmatched_charges = statement.charges.filter(
        status=CorporateCardCharge.Status.UNMATCHED
    )

    matched = 0

    for charge in unmatched_charges:
        window_start = charge.charge_date - timedelta(days=3)
        window_end = charge.charge_date + timedelta(days=3)

        # Exclude lines already matched to another card charge
        already_matched_ids = (
            CorporateCardCharge.objects.filter(
                matched_claim_line_id__isnull=False
            ).values_list("matched_claim_line_id", flat=True)
        )

        candidate = (
            ExpenseClaimLine.objects.filter(
                claim__employee_id=card.employee_id,
                claim__company_id=card.company_id,
                expense_date__range=(window_start, window_end),
                amount__gte=charge.amount - Decimal("0.01"),
                amount__lte=charge.amount + Decimal("0.01"),
            )
            .exclude(claim__status="cancelled")
            .exclude(pk__in=already_matched_ids)
            .first()
        )

        if candidate:
            charge.status = CorporateCardCharge.Status.MATCHED
            charge.matched_claim_line_id = candidate.pk
            charge.auto_matched = True
            charge.save(update_fields=["status", "matched_claim_line_id", "auto_matched"])
            matched += 1

    total = statement.charges.count()
    unmatched_count = total - matched

    # Flip statement status if fully reconciled
    if unmatched_count == 0 and total > 0:
        statement.status = CorporateCardStatement.Status.RECONCILED
        statement.save(update_fields=["status"])

    return {"matched": matched, "unmatched": unmatched_count}
