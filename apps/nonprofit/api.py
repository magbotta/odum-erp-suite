"""Nonprofit action endpoints."""
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router

from apps.nonprofit.models import Donation, FundraisingCampaign
from core.platform_api.security import AuthBearer

router = Router(tags=["Nonprofit Actions"], auth=AuthBearer())


@router.post("/donations/{donation_id}/receive")
def receive_donation(request, donation_id: UUID):
    donation = get_object_or_404(Donation, pk=donation_id)
    if donation.status != "pledged":
        return {"error": "Only Pledged donations can be received."}
    from apps.nonprofit.hooks.donation import (
        receive_donation as do_receive,
        post_donation_to_accounting,
        update_donor_totals,
    )
    do_receive(donation)
    donation.save()
    post_donation_to_accounting(donation)
    update_donor_totals(donation)
    return {"status": donation.status}


@router.post("/donations/{donation_id}/receipt")
def issue_receipt(request, donation_id: UUID):
    donation = get_object_or_404(Donation, pk=donation_id)
    if donation.status != "received":
        return {"error": "Only Received donations can be receipted."}
    from apps.nonprofit.hooks.donation import (
        issue_receipt as do_receipt,
        update_donor_totals,
    )
    do_receipt(donation)
    donation.save()
    update_donor_totals(donation)
    return {"status": donation.status, "receipt_number": donation.receipt_number}


@router.post("/campaigns/{campaign_id}/activate")
def activate_campaign(request, campaign_id: UUID):
    campaign = get_object_or_404(FundraisingCampaign, pk=campaign_id)
    if campaign.status != "planning":
        return {"error": "Only Planning campaigns can be activated."}
    campaign.status = "active"
    campaign.save()
    return {"status": campaign.status}


@router.post("/campaigns/{campaign_id}/complete")
def complete_campaign(request, campaign_id: UUID):
    campaign = get_object_or_404(FundraisingCampaign, pk=campaign_id)
    if campaign.status != "active":
        return {"error": "Only Active campaigns can be completed."}
    campaign.status = "completed"
    campaign.save()
    return {"status": campaign.status}
