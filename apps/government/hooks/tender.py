"""Government hooks — tender lifecycle and OCDS publication."""
import uuid
from django.utils import timezone

from apps.government.models import Tender
from core.numbering.service import get_next_number


def set_tender_number(tender: Tender) -> None:
    if not tender.tender_number:
        tender.tender_number = get_next_number("TEND", company_id=tender.company_id)
    if not tender.ocds_ocid:
        tender.ocds_ocid = f"ocds-odum-{tender.company_id}-{tender.tender_number}"


def publish_tender(tender: Tender) -> None:
    tender.status = "published"
    if not tender.publication_date:
        tender.publication_date = timezone.now().date()


def open_submissions(tender: Tender) -> None:
    tender.status = "submissions_open"


def close_submissions(tender: Tender) -> None:
    tender.status = "evaluation"


def award_tender(tender: Tender, vendor_id: uuid.UUID, awarded_amount) -> None:
    tender.status = "awarded"
    tender.awarded_vendor_id = vendor_id
    tender.awarded_amount = awarded_amount
    tender.award_date = timezone.now().date()


def cancel_tender(tender: Tender) -> None:
    tender.status = "cancelled"


def publish_ocds_notice(tender: Tender) -> None:
    """
    Placeholder: publish OCDS-compliant JSON notice to an external portal or
    an n8n webhook (§9) for downstream e-procurement integrations.
    """
    pass
