"""Government hooks — permit lifecycle (§7)."""
import datetime

from django.utils import timezone

from apps.government.models import Permit, PermitInspection
from core.numbering.service import get_next_number


def set_permit_number(permit: Permit) -> None:
    if not permit.permit_number:
        permit.permit_number = get_next_number("PERM", company_id=permit.company_id)


def submit_permit(permit: Permit) -> None:
    set_permit_number(permit)
    permit.status = Permit.Status.SUBMITTED
    if not permit.application_date:
        permit.application_date = timezone.now().date()
    if not permit.review_deadline:
        # Default 30-day review window
        permit.review_deadline = permit.application_date + datetime.timedelta(days=30)


def start_review(permit: Permit) -> None:
    permit.status = Permit.Status.UNDER_REVIEW


def approve_permit(permit: Permit, conditions: str = "") -> None:
    permit.status = Permit.Status.APPROVED
    if conditions:
        permit.conditions = conditions


def reject_permit(permit: Permit, reason: str) -> None:
    permit.status = Permit.Status.REJECTED
    permit.rejection_reason = reason


def issue_permit(permit: Permit, expiry_date: datetime.date = None) -> None:
    """Issue an approved permit and set its expiry date."""
    if permit.status != Permit.Status.APPROVED:
        raise ValueError("Only Approved permits can be issued.")
    permit.status = Permit.Status.ISSUED
    permit.issue_date = timezone.now().date()
    if expiry_date:
        permit.expiry_date = expiry_date
    elif not permit.expiry_date and permit.issue_date:
        # Default 1-year validity
        permit.expiry_date = permit.issue_date.replace(year=permit.issue_date.year + 1)


def revoke_permit(permit: Permit, reason: str) -> None:
    permit.status = Permit.Status.REVOKED
    permit.rejection_reason = reason


def schedule_inspection(permit: Permit, inspection_type: str, scheduled_date: datetime.date,
                        inspector_name: str = "") -> PermitInspection:
    return PermitInspection.objects.create(
        permit=permit,
        inspection_type=inspection_type,
        scheduled_date=scheduled_date,
        inspector_name=inspector_name,
        outcome=PermitInspection.Outcome.PENDING,
        company_id=permit.company_id,
    )


def record_inspection_result(inspection: PermitInspection, passed: bool, notes: str = "",
                             corrections: str = "") -> None:
    inspection.outcome = PermitInspection.Outcome.PASSED if passed else PermitInspection.Outcome.FAILED
    inspection.completed_date = timezone.now().date()
    inspection.notes = notes
    if corrections:
        inspection.corrections_required = corrections
        inspection.reinspection_required = True
    inspection.save()

    # Update permit inspection_passed flag
    permit = inspection.permit
    permit.inspection_passed = passed
    permit.save(update_fields=["inspection_passed"])
