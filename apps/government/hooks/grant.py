"""Government hooks — grant application lifecycle (§7)."""
from django.utils import timezone

from apps.government.models import GrantApplication
from core.numbering.service import get_next_number


def set_grant_number(grant: GrantApplication) -> None:
    if not grant.grant_number:
        grant.grant_number = get_next_number("GRT", company_id=grant.company_id)


def submit_grant(grant: GrantApplication) -> None:
    set_grant_number(grant)
    grant.status = GrantApplication.Status.SUBMITTED
    if not grant.application_date:
        grant.application_date = timezone.now().date()


def start_review(grant: GrantApplication) -> None:
    grant.status = GrantApplication.Status.UNDER_REVIEW


def approve_grant(grant: GrantApplication, approved_amount=None, award_date=None) -> None:
    grant.status = GrantApplication.Status.APPROVED
    if approved_amount is not None:
        grant.approved_amount = approved_amount
    else:
        grant.approved_amount = grant.requested_amount
    grant.award_date = award_date or timezone.now().date()


def reject_grant(grant: GrantApplication, reason: str) -> None:
    grant.status = GrantApplication.Status.REJECTED
    grant.rejection_reason = reason


def activate_grant(grant: GrantApplication, start_date=None, end_date=None) -> None:
    if grant.status not in (GrantApplication.Status.APPROVED,):
        raise ValueError("Grant must be Approved before activating.")
    grant.status = GrantApplication.Status.ACTIVE
    if start_date:
        grant.start_date = start_date
    if end_date:
        grant.end_date = end_date


def record_disbursement(grant: GrantApplication, amount) -> None:
    grant.disbursed_amount = (grant.disbursed_amount or 0) + amount
    if grant.disbursed_amount >= grant.approved_amount:
        grant.status = GrantApplication.Status.CLOSED
    grant.save(update_fields=["disbursed_amount", "status"])


def close_grant(grant: GrantApplication) -> None:
    grant.status = GrantApplication.Status.CLOSED
