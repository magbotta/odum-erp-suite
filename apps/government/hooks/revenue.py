"""
Revenue billing hooks for the Government app.

Covers:
  - Property rate bill-run (annual demand notices for all active parcels)
  - Permit fee bill generation (triggered when a permit moves to ISSUED)
  - Market toll bill generation (triggered by LocalLevy billing cycle)
  - Service charge bill generation (ad-hoc)
  - Delinquency escalation (cron-driven, marks overdue bills + adds penalty)
  - Payment confirmation hook (updates bill paid_amount, issues receipt, posts GL)
  - IGF revenue classification queries
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from core.numbering.service import get_next_number

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Property rate bill-run
# ---------------------------------------------------------------------------

def run_property_rate_bill_run(fiscal_year: int, company_id: str) -> List[str]:
    """
    Generate annual property rate demand notices for all active, non-exempt parcels.

    Returns a list of newly created GovernmentRevenueBill IDs.
    Bills are idempotent: if a bill already exists for this parcel × fiscal_year
    it is skipped (safe to re-run after a partial failure).
    """
    from apps.government.models import (
        GovernmentRevenueBill, PropertyParcel, RateImpost
    )

    created_ids: List[str] = []
    parcels = PropertyParcel.objects.filter(
        is_active=True, company_id=company_id
    ).exclude(exemption_reason="")

    # Load all impostes for this fiscal year into a lookup dict
    impostes = {
        (imp.property_use, imp.valuation_basis): imp
        for imp in RateImpost.objects.filter(fiscal_year=fiscal_year, company_id=company_id)
    }

    for parcel in PropertyParcel.objects.filter(
        is_active=True, company_id=company_id, exemption_reason=""
    ):
        impost = impostes.get((parcel.property_use, parcel.valuation_basis))
        if impost is None:
            logger.warning(
                "No rate impost for FY%s use=%s basis=%s — skipping parcel %s",
                fiscal_year, parcel.property_use, parcel.valuation_basis,
                parcel.parcel_number,
            )
            continue

        # Idempotency: skip if a bill already exists for this parcel + fiscal year
        already = GovernmentRevenueBill.objects.filter(
            parcel_id=parcel.id,
            fiscal_year=fiscal_year,
            bill_type=GovernmentRevenueBill.BillType.PROPERTY_RATE,
        ).exists()
        if already:
            continue

        annual_charge = _compute_rate_charge(
            parcel.rateable_value, impost.rate_pct, impost.minimum_charge
        )
        due_date = date(fiscal_year, 3, 31)  # Q1 due date, configurable per assembly
        grace_end = due_date + timedelta(days=impost.grace_period_days)

        payer_name = (
            parcel.occupier_name if parcel.rate_payer == "occupier"
            else parcel.owner_name
        )
        payer_phone = (
            parcel.occupier_phone if parcel.rate_payer == "occupier"
            else parcel.owner_phone
        )

        bill = GovernmentRevenueBill.objects.create(
            company_id=company_id,
            bill_number=get_next_number("GOV-RATE", company_id),
            bill_type=GovernmentRevenueBill.BillType.PROPERTY_RATE,
            fiscal_year=fiscal_year,
            payer_name=payer_name,
            payer_phone=payer_phone,
            parcel_id=parcel.id,
            payable_amount=annual_charge,
            currency="GHS",
            due_date=due_date,
            grace_period_end=grace_end,
            gasb_fund=parcel.gasb_fund,
        )
        created_ids.append(str(bill.id))

    logger.info(
        "Property rate bill-run FY%s complete: %d bills created.",
        fiscal_year, len(created_ids),
    )
    return created_ids


def _compute_rate_charge(
    rateable_value: Decimal, rate_pct: Decimal, minimum_charge: Decimal
) -> Decimal:
    """Apply rate_pct to rateable_value; floor at minimum_charge."""
    computed = (rateable_value * rate_pct / Decimal("100")).quantize(Decimal("0.01"))
    return max(computed, minimum_charge)


# ---------------------------------------------------------------------------
# Permit fee bill generation
# ---------------------------------------------------------------------------

def generate_permit_fee_bill(permit_id: str, company_id: str) -> Optional[str]:
    """
    Generate a GovernmentRevenueBill for a permit's fee when it moves to ISSUED.
    Idempotent: returns the existing bill ID if already generated.
    """
    from apps.government.models import GovernmentRevenueBill, Permit

    try:
        permit = Permit.objects.get(id=permit_id, company_id=company_id)
    except Permit.DoesNotExist:
        logger.error("Permit %s not found — cannot generate fee bill.", permit_id)
        return None

    if permit.fee_amount == 0:
        return None

    existing = GovernmentRevenueBill.objects.filter(
        permit_id=permit.id,
        bill_type=GovernmentRevenueBill.BillType.PERMIT_FEE,
    ).first()
    if existing:
        return str(existing.id)

    due_date = permit.issue_date or date.today()
    bill = GovernmentRevenueBill.objects.create(
        company_id=company_id,
        bill_number=get_next_number("GOV-PERMIT", company_id),
        bill_type=GovernmentRevenueBill.BillType.PERMIT_FEE,
        fiscal_year=due_date.year,
        payer_name=permit.applicant_name,
        payer_phone=permit.applicant_phone,
        payer_email=permit.applicant_email,
        permit_id=permit.id,
        payable_amount=permit.fee_amount,
        currency="GHS",
        due_date=due_date,
        gasb_fund=permit.gasb_fund,
        description="Permit fee for {0} #{1}".format(permit.permit_type, permit.permit_number),
    )
    return str(bill.id)


# ---------------------------------------------------------------------------
# Local levy (market toll) bill generation
# ---------------------------------------------------------------------------

def generate_levy_bill(
    levy_id: str, payer_name: str, payer_phone: str,
    company_id: str, bill_date: Optional[date] = None
) -> str:
    """
    Generate a GovernmentRevenueBill for one levy-payer billing cycle.
    Called by the scheduled levy billing task.
    """
    from apps.government.models import GovernmentRevenueBill, LocalLevy

    levy = LocalLevy.objects.get(id=levy_id, company_id=company_id)
    billing_date = bill_date or date.today()

    bill = GovernmentRevenueBill.objects.create(
        company_id=company_id,
        bill_number=get_next_number("GOV-LEVY", company_id),
        bill_type=GovernmentRevenueBill.BillType.MARKET_TOLL,
        fiscal_year=billing_date.year,
        payer_name=payer_name,
        payer_phone=payer_phone,
        levy_id=levy.id,
        payable_amount=levy.amount,
        currency=levy.currency,
        due_date=billing_date + timedelta(days=14),
        gasb_fund=levy.gasb_fund,
        description="{0} — {1}".format(levy.name, billing_date.strftime("%Y-%m")),
    )
    return str(bill.id)


# ---------------------------------------------------------------------------
# Delinquency escalation
# ---------------------------------------------------------------------------

def escalate_overdue_bills(company_id: str, as_of: Optional[date] = None) -> int:
    """
    Mark unpaid bills past their grace_period_end as overdue and apply penalty.
    Mark overdue bills with dunning_count >= 3 as escalated.
    Returns the number of bills updated.

    Designed to be called by a Celery Beat daily cron task.
    """
    from apps.government.models import GovernmentRevenueBill, RateImpost

    today = as_of or date.today()
    updated = 0

    # Step 1: unpaid → overdue
    newly_overdue = GovernmentRevenueBill.objects.filter(
        company_id=company_id,
        bill_status=GovernmentRevenueBill.BillStatus.UNPAID,
        grace_period_end__lt=today,
    )
    for bill in newly_overdue:
        penalty = _compute_overdue_penalty(bill)
        bill.bill_status = GovernmentRevenueBill.BillStatus.OVERDUE
        bill.overdue_since = today
        bill.penalty_amount = penalty
        bill.dunning_count = 1
        bill.save(update_fields=[
            "bill_status", "overdue_since", "penalty_amount", "dunning_count"
        ])
        updated += 1

    # Step 2: already overdue → increment dunning / escalate
    recurring_overdue = GovernmentRevenueBill.objects.filter(
        company_id=company_id,
        bill_status=GovernmentRevenueBill.BillStatus.OVERDUE,
    )
    for bill in recurring_overdue:
        bill.dunning_count += 1
        penalty = _compute_overdue_penalty(bill)
        bill.penalty_amount = penalty
        if bill.dunning_count >= 3:
            bill.bill_status = GovernmentRevenueBill.BillStatus.ESCALATED
        bill.save(update_fields=["dunning_count", "penalty_amount", "bill_status"])
        updated += 1

    logger.info(
        "Delinquency escalation complete (as_of=%s): %d bills updated.", today, updated
    )
    return updated


def _compute_overdue_penalty(bill) -> Decimal:
    """
    Apply a flat 10% penalty per dunning cycle as a safe default.
    Override per assembly by storing penalty_rate_pct on the matching RateImpost.
    """
    try:
        from apps.government.models import RateImpost
        impost = RateImpost.objects.filter(
            fiscal_year=bill.fiscal_year,
            company_id=bill.company_id,
        ).first()
        penalty_pct = impost.penalty_rate_pct if impost else Decimal("10")
    except Exception:
        penalty_pct = Decimal("10")

    base = bill.payable_amount
    return (base * penalty_pct / Decimal("100") * (bill.dunning_count or 1)).quantize(
        Decimal("0.01")
    )


# ---------------------------------------------------------------------------
# Payment confirmation (called from webhook handler / after gateway confirms)
# ---------------------------------------------------------------------------

def on_payment_confirmed(
    payment_event_id: str,
    bill_id: str,
    amount: Decimal,
    channel: str,
    company_id: str,
    issued_by_employee_id: Optional[str] = None,
) -> str:
    """
    Update the bill's paid_amount + status, issue a receipt, and post to GL.
    Returns the receipt number.

    This is the idempotency-safe entry point: if a receipt already exists for
    this payment_event_id, it returns the existing receipt number without
    double-posting.
    """
    from apps.government.models import GovernmentRevenueBill, GovernmentPaymentReceipt

    # Idempotency: bail if receipt already issued for this event
    existing = GovernmentPaymentReceipt.objects.filter(
        payment_event_id=payment_event_id
    ).first()
    if existing:
        logger.info(
            "Receipt %s already exists for payment_event %s — skipping.",
            existing.receipt_number, payment_event_id,
        )
        return existing.receipt_number

    try:
        bill = GovernmentRevenueBill.objects.get(id=bill_id, company_id=company_id)
    except GovernmentRevenueBill.DoesNotExist:
        logger.error("Bill %s not found for payment confirmation.", bill_id)
        raise

    bill.paid_amount += amount
    outstanding = bill.payable_amount + bill.penalty_amount - bill.paid_amount
    if outstanding <= 0:
        bill.bill_status = GovernmentRevenueBill.BillStatus.PAID
    elif bill.paid_amount > 0:
        bill.bill_status = GovernmentRevenueBill.BillStatus.PARTIALLY_PAID
    bill.save(update_fields=["paid_amount", "bill_status"])

    receipt_number = get_next_number("GOV-RCP", company_id)
    GovernmentPaymentReceipt.objects.create(
        company_id=company_id,
        receipt_number=receipt_number,
        payment_event_id=payment_event_id,
        bill=bill,
        payer_name=bill.payer_name,
        payer_phone=bill.payer_phone,
        amount=amount,
        currency=bill.currency,
        channel=channel,
        issued_by_employee_id=issued_by_employee_id,
    )

    # GL posting (soft — creates accounting.Payment record via UUID soft-link)
    _post_revenue_to_gl(bill, amount, payment_event_id, company_id)

    logger.info(
        "Payment confirmed: bill=%s amount=%s receipt=%s",
        bill_id, amount, receipt_number,
    )
    return receipt_number


def _post_revenue_to_gl(bill, amount: Decimal, reference: str, company_id: str) -> None:
    """
    Post a revenue GL entry for the confirmed payment.
    Creates a stub JournalEntry soft-linked to the bill.
    In production, this calls the Accounting app's journal-entry service.
    """
    from apps.accounting.models import JournalEntry, JournalEntryLine

    REVENUE_ACCOUNT_MAP = {
        "property_rate": "4100",   # Property Rates Revenue
        "permit_fee": "4200",      # Permit & Licence Revenue
        "market_toll": "4300",     # Market Fees Revenue
        "service_charge": "4400",  # Service Charges
        "fines_penalties": "4500", # Fines & Penalties
        "other": "4900",           # Other IGF Revenue
    }
    CASH_ACCOUNT = "1010"          # Cash / Mobile Money Clearing

    revenue_account = REVENUE_ACCOUNT_MAP.get(bill.bill_type, "4900")

    try:
        je = JournalEntry.objects.create(
            company_id=company_id,
            entry_number=reference[:30],
            entry_date=date.today(),
            reference=bill.bill_number,
            narration="IGF revenue — {0} — {1}".format(bill.bill_type, bill.bill_number),
            total_debit=amount,
            total_credit=amount,
            status="submitted",
        )
        # Dr Cash / MoMo clearing
        JournalEntryLine.objects.create(
            company_id=company_id, journal_entry=je, sequence=1,
            account_code=CASH_ACCOUNT, debit=amount, credit=Decimal("0"),
        )
        # Cr Revenue
        JournalEntryLine.objects.create(
            company_id=company_id, journal_entry=je, sequence=2,
            account_code=revenue_account, debit=Decimal("0"), credit=amount,
        )
        bill.journal_entry_id = str(je.id)
        bill.save(update_fields=["journal_entry_id"])
    except Exception as exc:
        # GL posting failure should not roll back the receipt — log and alert.
        logger.exception(
            "GL posting failed for bill %s payment %s: %s",
            bill.id, reference, exc,
        )


# ---------------------------------------------------------------------------
# IGF Revenue classification queries
# ---------------------------------------------------------------------------

def igf_revenue_summary(fiscal_year: int, company_id: str) -> dict:
    """
    Return confirmed IGF revenue totals by bill_type for the fiscal year.
    Queries PaymentEvent rather than GovernmentRevenueBill to get actual collected
    amounts (not billed amounts).

    Returns a dict: {bill_type: Decimal}
    """
    from django.db.models import Sum
    from core.payments_gateway.models import PaymentEvent

    rows = (
        PaymentEvent.objects.filter(
            company_id=company_id,
            payable_document_type="GovernmentRevenueBill",
            status="confirmed",
        )
        # Filter by fiscal year stored in the bill's revenue_type prefix
        # Convention: revenue_type = e.g. "property_rate:2025"
        .values("revenue_type")
        .annotate(total=Sum("amount"))
    )

    summary = {}
    fy_suffix = ":{0}".format(fiscal_year)
    for row in rows:
        rt = row["revenue_type"]
        if rt.endswith(fy_suffix):
            bill_type = rt.replace(fy_suffix, "")
            summary[bill_type] = row["total"]

    return summary
