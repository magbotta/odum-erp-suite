"""Hook: keep LeaveBalance in sync when a LeaveApplication is saved (§6.4)."""
from decimal import Decimal


def update_leave_balance(leave_application) -> None:
    """Increment/decrement pending days on the employee's LeaveBalance when status changes."""
    from apps.hrm.models import LeaveBalance

    year = leave_application.from_date.year
    balance, _ = LeaveBalance.objects.get_or_create(
        employee=leave_application.employee,
        leave_type=leave_application.leave_type,
        year=year,
        defaults={
            "total_allocated": leave_application.leave_type.days_allowed_per_year,
            "carried_forward": Decimal("0"),
            "total_taken": Decimal("0"),
            "total_pending": Decimal("0"),
        },
    )

    status = leave_application.status
    days = leave_application.total_days

    if status == "pending":
        balance.total_pending = (balance.total_pending or Decimal("0")) + days
    elif status == "approved":
        balance.total_taken = (balance.total_taken or Decimal("0")) + days
        balance.total_pending = max(Decimal("0"), (balance.total_pending or Decimal("0")) - days)
    elif status in ("rejected", "cancelled"):
        balance.total_pending = max(Decimal("0"), (balance.total_pending or Decimal("0")) - days)

    balance.save(update_fields=["total_allocated", "carried_forward", "total_taken", "total_pending"])
