"""CRM action endpoints: lead-to-opportunity conversion (§6.3)."""
from __future__ import annotations

import uuid
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from typing import Optional


router = Router(tags=["CRM Actions"])


class ConvertLeadSchema(Schema):
    pipeline_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    expected_close_date: Optional[str] = None


class ActionResponse(Schema):
    ok: bool
    message: str
    opportunity_id: Optional[uuid.UUID] = None


@router.post("/leads/{lead_id}/convert", response=ActionResponse)
def convert_lead(request, lead_id: uuid.UUID, payload: ConvertLeadSchema):
    from apps.crm.models import Lead, Opportunity, Account, Pipeline, PipelineStage

    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    if lead.status == Lead.Status.CONVERTED:
        return {"ok": False, "message": "Lead is already converted.", "opportunity_id": lead.converted_to_opportunity_id}

    # Find or create an Account for the lead's company
    account = None
    if lead.company:
        account, _ = Account.objects.get_or_create(
            name=lead.company,
            defaults={"company_id": lead.company_id},
        )

    # Resolve pipeline / stage
    pipeline = None
    stage = None
    if payload.pipeline_id:
        pipeline = Pipeline.objects.filter(id=payload.pipeline_id).first()
    if not pipeline:
        pipeline = Pipeline.objects.filter(is_default=True, is_deleted=False).first()
    if pipeline and payload.stage_id:
        stage = PipelineStage.objects.filter(id=payload.stage_id, pipeline=pipeline).first()
    if pipeline and not stage:
        stage = pipeline.stages.order_by("sequence").first()

    opp = Opportunity.objects.create(
        name=lead.title,
        account=account,
        pipeline=pipeline,
        stage=stage,
        assigned_to=lead.assigned_to,
        lead=lead,
        company_id=lead.company_id,
    )

    lead.status = Lead.Status.CONVERTED
    lead.converted_to_opportunity_id = opp.id
    lead.converted_at = timezone.now()
    lead.save(update_fields=["status", "converted_to_opportunity_id", "converted_at"])

    return {
        "ok": True,
        "message": f"Lead converted to opportunity '{opp.name}'.",
        "opportunity_id": opp.id,
    }
