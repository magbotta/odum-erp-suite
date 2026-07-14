"""Financial aid / scholarship lifecycle hooks (§7)."""
import datetime
from decimal import Decimal


def activate_award(award) -> None:
    award.status = "active"
    if not award.award_date:
        award.award_date = datetime.date.today()
    award.save()


def revoke_award(award, reason="") -> None:
    award.status = "revoked"
    award.revocation_reason = reason
    award.save()


def apply_award_to_invoice(award, invoice) -> None:
    """
    Apply a ScholarshipAward as a discount on the linked StudentFeeInvoice.
    If scholarship.is_percentage, treats awarded_amount as a percentage of invoice.amount.
    Updates invoice.discount_amount and recalculates status.
    """
    scholarship = award.scholarship
    if scholarship.is_percentage:
        discount = (Decimal(str(award.awarded_amount)) / Decimal("100")) * invoice.amount
    else:
        discount = Decimal(str(award.awarded_amount))

    # Cap the discount at the invoice gross amount
    invoice.discount_amount = min(discount, invoice.amount)

    net_due = invoice.amount - invoice.discount_amount - invoice.paid_amount
    if net_due <= Decimal("0"):
        invoice.status = "paid"
    elif invoice.paid_amount > Decimal("0"):
        invoice.status = "partially_paid"

    invoice.save()
