"""Timesheet hooks: aggregate hours and billing amounts (§6.6)."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.project.models import Timesheet


def calculate_totals(timesheet: "Timesheet") -> None:
    """Sum hours and billable amounts across all TimesheetEntry rows."""
    total_hours = Decimal("0")
    total_billable = Decimal("0")

    for entry in timesheet.entries.filter(is_deleted=False):
        total_hours += entry.hours
        if entry.is_billable:
            total_billable += entry.hours
            # Recompute billing amount from rate × hours
            if entry.billing_rate and entry.billing_rate > 0:
                entry.billing_amount = entry.hours * entry.billing_rate
                entry.save(update_fields=["billing_amount"])

    timesheet.total_hours = total_hours
    timesheet.total_billable_hours = total_billable
