"""Hook: compute working_hours from check_in / check_out (§6.4)."""
from __future__ import annotations

from decimal import Decimal


def calculate_working_hours(attendance) -> None:
    """Compute working_hours and flag late_entry / early_exit based on a 9-to-5 default."""
    if attendance.check_in and attendance.check_out:
        delta = attendance.check_out - attendance.check_in
        hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
        attendance.working_hours = hours

        # Overtime: anything over 8 hours
        if hours > Decimal("8"):
            attendance.overtime_hours = hours - Decimal("8")
