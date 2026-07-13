"""CRM case hooks — SLA tracking (§6.3)."""
from __future__ import annotations

from datetime import timedelta
from django.utils import timezone


def set_sla_due(case) -> None:
    """Calculate sla_due_at when sla_hours is set for the first time."""
    if case.sla_hours and not case.sla_due_at:
        case.sla_due_at = case.created_at + timedelta(hours=case.sla_hours) if case.created_at else timezone.now() + timedelta(hours=case.sla_hours)
        case.save(update_fields=["sla_due_at"])


def check_sla_breach(case) -> None:
    """Flag sla_breached when the SLA deadline has passed and case is not yet resolved."""
    if case.sla_due_at and case.status not in ("resolved", "closed"):
        case.sla_breached = timezone.now() > case.sla_due_at
