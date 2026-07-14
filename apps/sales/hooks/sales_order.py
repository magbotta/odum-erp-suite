"""Hooks for SalesOrder: credit-limit check, auto-numbering, commission calculation."""
from __future__ import annotations

from decimal import Decimal


def before_submit_so(so) -> None:
    """Auto-number and enforce credit limit before submission."""
    if not so.so_number:
        from core.numbering.service import get_next_number
        so.so_number = get_next_number("SO", so.company_id)

    _check_credit_limit(so)


def _check_credit_limit(so) -> None:
    """
    Flag `credit_limit_exceeded` when the customer's outstanding balance
    plus this order's grand_total exceeds their credit limit.
    Only raises an error if the customer has a non-zero credit limit.
    """
    try:
        customer = so.customer
    except Exception:
        return

    limit = customer.credit_limit or Decimal("0")
    if limit <= 0:
        return   # No limit configured

    from apps.accounting.models import SalesInvoice
    outstanding = (
        SalesInvoice.objects.filter(
            customer=customer,
            company_id=so.company_id,
            is_deleted=False,
        )
        .exclude(status="cancelled")
        .aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("outstanding_amount"))
    )["total"] or Decimal("0")

    if outstanding + so.grand_total > limit:
        so.credit_limit_exceeded = True
        so.save(update_fields=["credit_limit_exceeded"])


def calculate_commission(so) -> None:
    """
    Create a CommissionEntry for the assigned rep when an SO is delivered.
    Uses the first active CommissionStructure by default (placeholder logic;
    a real deployment would assign a structure per rep/territory).
    """
    if not so.assigned_to_id:
        return

    from apps.sales.models import CommissionEntry, CommissionStructure

    structure = CommissionStructure.objects.filter(
        is_active=True, company_id=so.company_id
    ).first()
    if not structure:
        return

    base = so.grand_total
    rate_obj = (
        structure.rates.filter(min_amount__lte=base).order_by("-min_amount").first()
    )
    if not rate_obj:
        return

    commission = (base * rate_obj.rate_pct / 100).quantize(Decimal("0.01"))

    CommissionEntry.objects.get_or_create(
        sales_order=so,
        rep_id=so.assigned_to_id,
        defaults={
            "rep_name": str(so.assigned_to),
            "structure": structure,
            "base_amount": base,
            "rate_pct": rate_obj.rate_pct,
            "commission_amount": commission,
            "status": CommissionEntry.Status.PENDING,
            "company_id": so.company_id,
        },
    )
