"""Legal Services hooks — IOLTA trust ledger posting and balance enforcement."""
import uuid
from decimal import Decimal

from django.db import transaction

from apps.legal_services.models import TrustAccount, TrustLedgerEntry


@transaction.atomic
def validate_trust_balance(entry: TrustLedgerEntry) -> None:
    """
    Hard rule (§7.3): a disbursement or fee-transfer may not bring the per-matter
    trust balance below zero, even if the pooled account has sufficient funds.
    """
    if entry.entry_type in ("disbursement", "fee_transfer"):
        # Per-matter balance before this entry
        prior_balance = (
            TrustLedgerEntry.objects.filter(
                trust_account=entry.trust_account,
                matter=entry.matter,
            )
            .exclude(pk=entry.pk)
            .order_by("-created_at")
            .values_list("balance_after", flat=True)
            .first()
        ) or Decimal("0")

        if prior_balance - entry.amount < Decimal("0"):
            raise ValueError(
                f"Trust disbursement of {entry.amount} would overdraw client trust balance "
                f"({prior_balance} available for matter {entry.matter.matter_number}). "
                "Commingle of trust and operating funds is prohibited."
            )


@transaction.atomic
def update_trust_account_balance(entry: TrustLedgerEntry) -> None:
    """Update the running balance_after on the entry and the TrustAccount total."""
    # Get prior per-matter balance
    prior_balance = (
        TrustLedgerEntry.objects.filter(
            trust_account=entry.trust_account,
            matter=entry.matter,
        )
        .exclude(pk=entry.pk)
        .order_by("-created_at")
        .values_list("balance_after", flat=True)
        .first()
    ) or Decimal("0")

    if entry.entry_type == "deposit":
        entry.balance_after = prior_balance + entry.amount
    else:
        entry.balance_after = prior_balance - entry.amount

    entry.save(update_fields=["balance_after"])

    # Refresh pooled trust account current_balance
    from django.db.models import Sum
    total = (
        TrustLedgerEntry.objects.filter(trust_account=entry.trust_account)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    TrustAccount.objects.filter(pk=entry.trust_account_id).update(current_balance=total)


@transaction.atomic
def post_trust_entry_to_gl(entry: TrustLedgerEntry) -> None:
    """Post trust fund movement to Accounting GL. Placeholder."""
    if not entry.journal_entry_id:
        entry.journal_entry_id = uuid.uuid4()
        entry.save(update_fields=["journal_entry_id"])
