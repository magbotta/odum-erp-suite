"""Hook: compute working_hours, late_entry, early_exit from check_in/check_out (§6.4)."""
from decimal import Decimal
from datetime import time


def calculate_working_hours(attendance) -> None:
    if attendance.check_in and attendance.check_out:
        delta = attendance.check_out - attendance.check_in
        hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
        attendance.working_hours = hours

        # Use shift thresholds if available, otherwise default 9am/5pm
        if attendance.shift_id:
            try:
                shift = attendance.shift
                threshold = shift.overtime_threshold_hours
                grace_late = shift.late_entry_grace_minutes
                grace_early = shift.early_exit_grace_minutes
                shift_start = shift.start_time
                shift_end = shift.end_time
            except Exception:
                threshold = Decimal("8")
                grace_late = grace_early = 15
                shift_start = time(9, 0)
                shift_end = time(17, 0)
        else:
            threshold = Decimal("8")
            grace_late = grace_early = 15
            shift_start = time(9, 0)
            shift_end = time(17, 0)

        if hours > threshold:
            attendance.overtime_hours = hours - threshold

        # Late entry flag
        check_in_time = attendance.check_in.time()
        late_cutoff = (
            shift_start.replace(minute=shift_start.minute + grace_late)
            if shift_start.minute + grace_late < 60
            else shift_start.replace(hour=shift_start.hour + 1, minute=(shift_start.minute + grace_late) % 60)
        )
        attendance.late_entry = check_in_time > late_cutoff

        # Early exit flag
        check_out_time = attendance.check_out.time()
        early_cutoff = (
            shift_end.replace(minute=max(0, shift_end.minute - grace_early))
            if shift_end.minute >= grace_early
            else shift_end.replace(hour=shift_end.hour - 1, minute=60 - (grace_early - shift_end.minute))
        )
        attendance.early_exit = check_out_time < early_cutoff
