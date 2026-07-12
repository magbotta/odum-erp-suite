"""Legal Services hooks — matter lifecycle, conflict checks, trust accounting."""
import uuid
from django.db import transaction

from apps.legal_services.models import (
    AdverseParty,
    ConflictCheck,
    Matter,
    TrustAccount,
    TrustLedgerEntry,
)
from core.numbering.service import get_next_number


def set_matter_number(matter: Matter) -> None:
    if not matter.matter_number:
        matter.matter_number = get_next_number("MTR", company_id=matter.company_id)


def open_matter(matter: Matter) -> None:
    matter.status = "open"


def put_on_hold(matter: Matter) -> None:
    matter.status = "on_hold"


def reopen_matter(matter: Matter) -> None:
    matter.status = "open"


def close_matter(matter: Matter) -> None:
    matter.status = "closed"


def archive_matter(matter: Matter) -> None:
    matter.status = "archived"


@transaction.atomic
def run_conflict_check(matter: Matter) -> None:
    """
    Run a conflict-of-interest check before opening a matter.
    Searches existing matters and adverse parties for name matches.
    In production this delegates to the AI layer for fuzzy matching (§7.3, §8.2).
    """
    search_terms = [matter.client_name]
    # Add adverse parties if they were saved before conflict check runs
    adverse_names = list(
        AdverseParty.objects.filter(matter=matter).values_list("name", flat=True)
    )
    search_terms.extend(adverse_names)

    # Simple exact/icontains match — production uses AI fuzzy matching
    hits = []
    for term in search_terms:
        matched_matters = Matter.objects.filter(
            client_name__icontains=term
        ).exclude(pk=matter.pk).values("id", "matter_number", "client_name")
        hits.extend(list(matched_matters))

        matched_adverse = AdverseParty.objects.filter(
            name__icontains=term
        ).exclude(matter=matter).values("matter__matter_number", "name", "role")
        hits.extend(list(matched_adverse))

    check = ConflictCheck.objects.create(
        matter=matter,
        search_terms=search_terms,
        status="conflict_found" if hits else "clear",
        hits=hits,
        company_id=matter.company_id,
    )

    if hits:
        raise ValueError(
            f"Conflict check found {len(hits)} potential conflict(s). "
            f"Review ConflictCheck {check.pk} before opening this matter."
        )
