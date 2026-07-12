"""Business logic hooks for JournalEntry (§6.1)."""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone


def validate_balanced_entry(entry) -> None:
    """Raise if the journal entry lines don't balance (debits != credits)."""
    from apps.accounting.models import JournalEntryLine

    lines = JournalEntryLine.objects.filter(entry=entry)
    total_debit = sum(line.debit_amount for line in lines)
    total_credit = sum(line.credit_amount for line in lines)

    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(
            f"Journal entry is not balanced: "
            f"debit {total_debit} ≠ credit {total_credit}"
        )

    entry.total_debit = total_debit
    entry.total_credit = total_credit


def submit_journal_entry(entry) -> None:
    """Finalize and submit a journal entry."""
    validate_balanced_entry(entry)
    from apps.accounting.models import JournalEntry

    entry.status = JournalEntry.Status.SUBMITTED
    entry.submitted_at = timezone.now()
    entry.save(update_fields=["status", "total_debit", "total_credit", "submitted_at"])
