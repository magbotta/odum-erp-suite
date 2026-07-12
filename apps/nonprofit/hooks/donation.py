"""Nonprofit hooks — donation receipt and donor aggregate updates."""
import uuid
from decimal import Decimal

from django.db import transaction

from apps.nonprofit.models import Donation, Donor
from core.numbering.service import get_next_number


def set_donor_number(donor: Donor) -> None:
    if not donor.donor_number:
        donor.donor_number = get_next_number("DONOR", company_id=donor.company_id)


def receive_donation(donation: Donation) -> None:
    donation.status = "received"


def issue_receipt(donation: Donation) -> None:
    if not donation.receipt_number:
        donation.receipt_number = get_next_number("RCP", company_id=donation.company_id)
    donation.status = "receipted"


@transaction.atomic
def post_donation_to_accounting(donation: Donation) -> None:
    """Post a received donation to Accounting as a payment against a GL revenue account."""
    if not donation.accounting_payment_id:
        donation.accounting_payment_id = uuid.uuid4()  # placeholder
        donation.save(update_fields=["accounting_payment_id"])


@transaction.atomic
def update_donor_totals(donation: Donation) -> None:
    """Refresh donor total_giving and last_gift_date after a donation is receipted."""
    if donation.status in ("received", "receipted"):
        donor = donation.donor
        Donor.objects.filter(pk=donor.pk).update(
            last_gift_date=donation.donation_date,
            total_giving=Donation.objects.filter(
                donor=donor, status__in=("received", "receipted")
            ).values_list("amount", flat=True)
            .__class__(
                Donation.objects.filter(
                    donor=donor, status__in=("received", "receipted")
                ).aggregate(total=models_sum("amount"))["total"]
                or Decimal("0")
            ),
        )


# pull aggregate sum lazily to avoid circular import at module level
def models_sum(field: str):
    from django.db.models import Sum
    return Sum(field)
