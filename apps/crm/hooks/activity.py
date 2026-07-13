"""CRM activity hooks (§6.3)."""
from __future__ import annotations

from django.utils import timezone


def stamp_done_at(activity) -> None:
    """Set done_at when status transitions to Done."""
    if activity.status == "done" and not activity.done_at:
        activity.done_at = timezone.now()
    elif activity.status != "done":
        activity.done_at = None
