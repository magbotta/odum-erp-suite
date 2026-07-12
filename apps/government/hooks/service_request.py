"""Government hooks — citizen service request (311) lifecycle."""
from django.utils import timezone

from apps.government.models import CitizenServiceRequest
from core.numbering.service import get_next_number


def set_request_number(req: CitizenServiceRequest) -> None:
    if not req.request_number:
        req.request_number = get_next_number("CSR", company_id=req.company_id)


def assign_request(req: CitizenServiceRequest) -> None:
    req.status = "assigned"


def start_work(req: CitizenServiceRequest) -> None:
    req.status = "in_progress"


def resolve_request(req: CitizenServiceRequest) -> None:
    req.status = "resolved"
    if not req.resolved_at:
        req.resolved_at = timezone.now()


def close_request(req: CitizenServiceRequest) -> None:
    req.status = "closed"
