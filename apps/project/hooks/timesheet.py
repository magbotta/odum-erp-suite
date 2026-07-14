"""Timesheet hooks: aggregate hours, billing amounts, approval, invoice creation (§6.6)."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.project.models import Timesheet


def calculate_totals(timesheet: "Timesheet") -> None:
    """Sum hours and billable amounts across all TimesheetEntry rows."""
    total_hours = Decimal("0")
    total_billable = Decimal("0")
    total_billing_amount = Decimal("0")

    for entry in timesheet.entries.filter(is_deleted=False):
        total_hours += entry.hours
        if entry.is_billable:
            total_billable += entry.hours
            if entry.billing_rate and entry.billing_rate > 0:
                entry.billing_amount = entry.hours * entry.billing_rate
                entry.save(update_fields=["billing_amount"])
            total_billing_amount += entry.billing_amount

    timesheet.total_hours = total_hours
    timesheet.total_billable_hours = total_billable
    timesheet.total_billing_amount = total_billing_amount
    timesheet.save(update_fields=["total_hours", "total_billable_hours", "total_billing_amount"])


def submit_timesheet(timesheet: "Timesheet") -> None:
    """Auto-number and move timesheet to Submitted."""
    from apps.project.models import Timesheet as TS
    from core.numbering.service import get_next_number

    if timesheet.status != TS.Status.DRAFT:
        raise ValueError("Only draft timesheets can be submitted.")

    if not timesheet.timesheet_number:
        timesheet.timesheet_number = get_next_number("TS", company_id=timesheet.company_id)

    calculate_totals(timesheet)
    timesheet.status = TS.Status.SUBMITTED
    timesheet.save(update_fields=["timesheet_number", "status"])


def approve_timesheet(timesheet: "Timesheet", approver_id) -> None:
    """Approve a submitted timesheet and update project task actual hours."""
    from django.utils import timezone
    from apps.project.models import Timesheet as TS
    from apps.project.hooks.project import update_task_hours, update_project_progress

    if timesheet.status != TS.Status.SUBMITTED:
        raise ValueError("Only submitted timesheets can be approved.")

    timesheet.status = TS.Status.APPROVED
    timesheet.approved_by_id = approver_id
    timesheet.approved_at = timezone.now()
    timesheet.save(update_fields=["status", "approved_by_id", "approved_at"])

    # Rollup task hours
    tasks_seen = set()
    for entry in timesheet.entries.filter(is_deleted=False, task__isnull=False).select_related("task"):
        if entry.task_id not in tasks_seen:
            update_task_hours(entry.task)
            tasks_seen.add(entry.task_id)

    # Rollup project progress for each unique project on this timesheet
    projects_seen = set()
    for entry in timesheet.entries.filter(is_deleted=False).select_related("project"):
        if entry.project_id not in projects_seen:
            update_project_progress(entry.project)
            projects_seen.add(entry.project_id)


def reject_timesheet(timesheet: "Timesheet", reason: str) -> None:
    """Reject a submitted timesheet."""
    from apps.project.models import Timesheet as TS

    if timesheet.status != TS.Status.SUBMITTED:
        raise ValueError("Only submitted timesheets can be rejected.")

    timesheet.status = TS.Status.REJECTED
    timesheet.rejection_reason = reason
    timesheet.save(update_fields=["status", "rejection_reason"])


def create_invoice_from_timesheet(timesheet: "Timesheet") -> str:
    """
    Create a Sales Invoice from approved timesheet billable hours.
    Uses cross-app soft reference — creates the invoice via accounting models.
    Returns the invoice number.
    """
    from apps.project.models import Timesheet as TS

    if timesheet.status != TS.Status.APPROVED:
        raise ValueError("Only approved timesheets can be invoiced.")

    if timesheet.invoice_id:
        raise ValueError("Timesheet {} already has invoice {}.".format(
            timesheet.timesheet_number, timesheet.invoice_id
        ))

    if timesheet.total_billable_hours == 0:
        raise ValueError("No billable hours on this timesheet.")

    try:
        from apps.accounting.models import SalesInvoice, SalesInvoiceLine
    except ImportError:
        raise ValueError("Accounting app not available.")

    from core.numbering.service import get_next_number
    import datetime

    invoice_number = get_next_number("SINV", company_id=timesheet.company_id)

    invoice = SalesInvoice.objects.create(
        invoice_number=invoice_number,
        customer_id=_get_project_customer(timesheet),
        invoice_date=datetime.date.today(),
        status="draft",
        currency=_get_project_currency(timesheet),
        total_amount=timesheet.total_billing_amount,
        source_type="Timesheet",
        source_id=str(timesheet.pk),
        company_id=timesheet.company_id,
    )

    # One line per project/activity bucket
    from django.db.models import Sum
    from apps.project.models import TimesheetEntry

    buckets = (
        TimesheetEntry.objects
        .filter(timesheet=timesheet, is_billable=True, is_deleted=False)
        .values("project__project_name", "activity_type", "billing_rate")
        .annotate(total_hours=Sum("hours"), total_amount=Sum("billing_amount"))
    )

    for bucket in buckets:
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            description="{} — {} ({} hrs @ {}/hr)".format(
                bucket["project__project_name"],
                bucket["activity_type"],
                bucket["total_hours"],
                bucket["billing_rate"],
            ),
            quantity=bucket["total_hours"],
            unit_price=bucket["billing_rate"],
            amount=bucket["total_amount"],
            company_id=timesheet.company_id,
        )

    timesheet.invoice_id = invoice.pk
    timesheet.save(update_fields=["invoice_id"])

    return invoice_number


def _get_project_customer(timesheet):
    """Return the customer_id from the first project on this timesheet."""
    entry = timesheet.entries.filter(is_deleted=False).select_related("project").first()
    if entry and entry.project.customer_id:
        return entry.project.customer_id
    return None


def _get_project_currency(timesheet):
    entry = timesheet.entries.filter(is_deleted=False).select_related("project").first()
    if entry:
        return entry.project.currency
    return "USD"
