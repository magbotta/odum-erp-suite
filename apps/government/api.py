"""Government action endpoints."""
from typing import Optional
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.government.models import CitizenServiceRequest, FOIARequest, Permit, Tender
from core.platform_api.security import AuthBearer

router = Router(tags=["Government Actions"], auth=AuthBearer())


class AwardTenderBody(Schema):
    vendor_id: UUID
    awarded_amount: float


@router.post("/tenders/{tender_id}/publish")
def publish_tender(request, tender_id: UUID):
    tender = get_object_or_404(Tender, pk=tender_id)
    if tender.status != "draft":
        return {"error": "Only Draft tenders can be published."}
    from apps.government.hooks.tender import publish_tender as do_publish
    do_publish(tender)
    tender.save()
    return {"status": tender.status, "ocds_ocid": tender.ocds_ocid}


@router.post("/tenders/{tender_id}/open-submissions")
def open_submissions(request, tender_id: UUID):
    tender = get_object_or_404(Tender, pk=tender_id)
    if tender.status != "published":
        return {"error": "Tender must be Published to open submissions."}
    from apps.government.hooks.tender import open_submissions as do_open
    do_open(tender)
    tender.save()
    return {"status": tender.status}


@router.post("/tenders/{tender_id}/award")
def award_tender(request, tender_id: UUID, body: AwardTenderBody):
    tender = get_object_or_404(Tender, pk=tender_id)
    if tender.status != "evaluation":
        return {"error": "Tender must be Under Evaluation to award."}
    from decimal import Decimal
    from apps.government.hooks.tender import award_tender as do_award
    do_award(tender, vendor_id=body.vendor_id, awarded_amount=Decimal(str(body.awarded_amount)))
    tender.save()
    return {"status": tender.status, "awarded_amount": str(tender.awarded_amount)}


@router.post("/tenders/{tender_id}/cancel")
def cancel_tender(request, tender_id: UUID):
    tender = get_object_or_404(Tender, pk=tender_id)
    if tender.status in ("awarded", "cancelled"):
        return {"error": f"Cannot cancel a {tender.status} tender."}
    from apps.government.hooks.tender import cancel_tender as do_cancel
    do_cancel(tender)
    tender.save()
    return {"status": tender.status}


@router.post("/service-requests/{request_id}/assign")
def assign_service_request(request, request_id: UUID):
    req = get_object_or_404(CitizenServiceRequest, pk=request_id)
    if req.status != "open":
        return {"error": "Only Open requests can be assigned."}
    from apps.government.hooks.service_request import assign_request
    assign_request(req)
    req.save()
    return {"status": req.status}


@router.post("/service-requests/{request_id}/resolve")
def resolve_service_request(request, request_id: UUID):
    req = get_object_or_404(CitizenServiceRequest, pk=request_id)
    if req.status not in ("assigned", "in_progress"):
        return {"error": "Request must be Assigned or In Progress to resolve."}
    from apps.government.hooks.service_request import resolve_request
    resolve_request(req)
    req.save()
    return {"status": req.status}
