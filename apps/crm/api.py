"""CRM action endpoints (§6.3): lead conversion, opportunity close, activity, case, quote."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError


router = Router(tags=["CRM Actions"])


# ─── Shared response schemas ─────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str
    id: Optional[uuid.UUID] = None


# ─── Lead actions ─────────────────────────────────────────────────────────────

class ConvertLeadSchema(Schema):
    pipeline_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    expected_close_date: Optional[str] = None


@router.post("/leads/{lead_id}/convert", response=ActionResponse, summary="Convert Lead to Opportunity")
def convert_lead(request, lead_id: uuid.UUID, payload: ConvertLeadSchema):
    from apps.crm.models import Lead, Opportunity, Account, Pipeline, PipelineStage

    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    if lead.status == Lead.Status.CONVERTED:
        return {"ok": False, "message": "Lead is already converted.", "id": lead.converted_to_opportunity_id}

    account = None
    if lead.company:
        account, _ = Account.objects.get_or_create(
            name=lead.company,
            defaults={"company_id": lead.company_id},
        )

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
        probability=stage.probability if stage else 0,
        assigned_to=lead.assigned_to,
        lead=lead,
        company_id=lead.company_id,
        expected_close_date=payload.expected_close_date or None,
    )

    lead.status = Lead.Status.CONVERTED
    lead.converted_to_opportunity_id = opp.id
    lead.converted_at = timezone.now()
    lead.save(update_fields=["status", "converted_to_opportunity_id", "converted_at"])

    return {"ok": True, "message": f"Lead converted to opportunity '{opp.name}'.", "id": opp.id}


@router.post("/leads/{lead_id}/disqualify", response=ActionResponse, summary="Disqualify Lead")
def disqualify_lead(request, lead_id: uuid.UUID):
    from apps.crm.models import Lead
    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    if lead.status in (Lead.Status.CONVERTED,):
        raise HttpError(400, "Cannot disqualify a converted lead.")
    lead.status = Lead.Status.DISQUALIFIED
    lead.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": "Lead disqualified.", "id": lead.id}


# ─── Opportunity actions ──────────────────────────────────────────────────────

class CloseOpportunitySchema(Schema):
    reason: Optional[str] = None


@router.post("/opportunities/{opp_id}/close-won", response=ActionResponse, summary="Close Opportunity as Won")
def close_won(request, opp_id: uuid.UUID, payload: CloseOpportunitySchema):
    from apps.crm.models import Opportunity
    opp = get_object_or_404(Opportunity, id=opp_id, is_deleted=False)
    opp.forecast_category = Opportunity.ForecastCategory.CLOSED_WON
    opp.closed_at = timezone.now()
    if payload.reason:
        opp.win_reason = payload.reason
    opp.save(update_fields=["forecast_category", "closed_at", "win_reason", "updated_at"])
    return {"ok": True, "message": "Opportunity marked as Closed Won.", "id": opp.id}


@router.post("/opportunities/{opp_id}/close-lost", response=ActionResponse, summary="Close Opportunity as Lost")
def close_lost(request, opp_id: uuid.UUID, payload: CloseOpportunitySchema):
    from apps.crm.models import Opportunity
    opp = get_object_or_404(Opportunity, id=opp_id, is_deleted=False)
    opp.forecast_category = Opportunity.ForecastCategory.CLOSED_LOST
    opp.closed_at = timezone.now()
    if payload.reason:
        opp.loss_reason = payload.reason
    opp.save(update_fields=["forecast_category", "closed_at", "loss_reason", "updated_at"])
    return {"ok": True, "message": "Opportunity marked as Closed Lost.", "id": opp.id}


class MoveStageSchema(Schema):
    stage_id: uuid.UUID


@router.post("/opportunities/{opp_id}/move-stage", response=ActionResponse, summary="Move Opportunity to Stage")
def move_stage(request, opp_id: uuid.UUID, payload: MoveStageSchema):
    from apps.crm.models import Opportunity, PipelineStage
    opp = get_object_or_404(Opportunity, id=opp_id, is_deleted=False)
    stage = get_object_or_404(PipelineStage, id=payload.stage_id, is_deleted=False)
    opp.stage = stage
    opp.probability = stage.probability
    if stage.is_won:
        opp.forecast_category = Opportunity.ForecastCategory.CLOSED_WON
        opp.closed_at = opp.closed_at or timezone.now()
    elif stage.is_lost:
        opp.forecast_category = Opportunity.ForecastCategory.CLOSED_LOST
        opp.closed_at = opp.closed_at or timezone.now()
    opp.save(update_fields=["stage", "probability", "forecast_category", "closed_at", "updated_at"])
    return {"ok": True, "message": f"Moved to stage '{stage.name}'.", "id": opp.id}


# ─── Forecast summary ─────────────────────────────────────────────────────────

class ForecastLineSchema(Schema):
    category: str
    count: int
    total_amount: float
    weighted_amount: float


class ForecastSummarySchema(Schema):
    lines: List[ForecastLineSchema]
    grand_total: float
    weighted_grand_total: float


@router.get("/forecast-summary", response=ForecastSummarySchema, summary="Pipeline Forecast Rollup")
def forecast_summary(request):
    from apps.crm.models import Opportunity
    from django.db.models import Count, Sum, F, FloatField, ExpressionWrapper

    qs = (
        Opportunity.objects.filter(is_deleted=False)
        .exclude(forecast_category__in=["closed_won", "closed_lost"])
        .values("forecast_category")
        .annotate(
            count=Count("id"),
            total_amount=Sum("amount"),
        )
    )

    lines = []
    grand_total = 0.0
    weighted_grand_total = 0.0

    for row in qs:
        total = float(row["total_amount"] or 0)
        # Compute weighted as average probability * total (approximate)
        opps = Opportunity.objects.filter(
            is_deleted=False, forecast_category=row["forecast_category"]
        )
        weighted = float(sum(
            (o.amount or Decimal("0")) * o.probability / 100 for o in opps
        ))
        lines.append({
            "category": row["forecast_category"],
            "count": row["count"],
            "total_amount": total,
            "weighted_amount": weighted,
        })
        grand_total += total
        weighted_grand_total += weighted

    return {
        "lines": lines,
        "grand_total": grand_total,
        "weighted_grand_total": weighted_grand_total,
    }


# ─── Activity actions ─────────────────────────────────────────────────────────

@router.post("/activities/{activity_id}/mark-done", response=ActionResponse, summary="Mark Activity as Done")
def mark_activity_done(request, activity_id: uuid.UUID):
    from apps.crm.models import Activity
    activity = get_object_or_404(Activity, id=activity_id, is_deleted=False)
    activity.status = Activity.Status.DONE
    activity.done_at = timezone.now()
    activity.save(update_fields=["status", "done_at", "updated_at"])
    return {"ok": True, "message": "Activity marked as done.", "id": activity.id}


@router.post("/activities/{activity_id}/cancel", response=ActionResponse, summary="Cancel Activity")
def cancel_activity(request, activity_id: uuid.UUID):
    from apps.crm.models import Activity
    activity = get_object_or_404(Activity, id=activity_id, is_deleted=False)
    if activity.status == Activity.Status.DONE:
        raise HttpError(400, "Cannot cancel a completed activity.")
    activity.status = Activity.Status.CANCELLED
    activity.save(update_fields=["status", "updated_at"])
    return {"ok": True, "message": "Activity cancelled.", "id": activity.id}


# ─── Case actions ─────────────────────────────────────────────────────────────

class ResolveSchema(Schema):
    resolution_notes: Optional[str] = None


@router.post("/cases/{case_id}/escalate", response=ActionResponse, summary="Escalate Case")
def escalate_case(request, case_id: uuid.UUID):
    from apps.crm.models import Case
    case = get_object_or_404(Case, id=case_id, is_deleted=False)
    if case.status in (Case.Status.RESOLVED, Case.Status.CLOSED):
        raise HttpError(400, "Cannot escalate a resolved or closed case.")
    case.status = Case.Status.ESCALATED
    case.escalated_at = timezone.now()
    case.save(update_fields=["status", "escalated_at", "updated_at"])
    return {"ok": True, "message": "Case escalated.", "id": case.id}


@router.post("/cases/{case_id}/resolve", response=ActionResponse, summary="Resolve Case")
def resolve_case(request, case_id: uuid.UUID, payload: ResolveSchema):
    from apps.crm.models import Case
    case = get_object_or_404(Case, id=case_id, is_deleted=False)
    case.status = Case.Status.RESOLVED
    case.resolved_at = timezone.now()
    if not case.first_response_at:
        case.first_response_at = case.resolved_at
    if payload.resolution_notes:
        case.resolution_notes = payload.resolution_notes
    case.save(update_fields=["status", "resolved_at", "first_response_at", "resolution_notes", "updated_at"])
    return {"ok": True, "message": "Case resolved.", "id": case.id}


@router.post("/cases/{case_id}/close", response=ActionResponse, summary="Close Case")
def close_case(request, case_id: uuid.UUID):
    from apps.crm.models import Case
    case = get_object_or_404(Case, id=case_id, is_deleted=False)
    if case.status != Case.Status.RESOLVED:
        raise HttpError(400, "Only resolved cases can be closed. Resolve first.")
    case.status = Case.Status.CLOSED
    case.closed_at = timezone.now()
    case.save(update_fields=["status", "closed_at", "updated_at"])
    return {"ok": True, "message": "Case closed.", "id": case.id}


# ─── Quote actions ────────────────────────────────────────────────────────────

@router.post("/quotes/{quote_id}/send-to-customer", response=ActionResponse, summary="Send Quote to Customer")
def send_quote(request, quote_id: uuid.UUID):
    from apps.crm.models import Quote
    quote = get_object_or_404(Quote, id=quote_id, is_deleted=False)
    if quote.status != Quote.Status.DRAFT:
        raise HttpError(400, "Only Draft quotes can be sent.")
    quote.status = Quote.Status.SENT
    quote.sent_at = timezone.now()
    quote.save(update_fields=["status", "sent_at", "updated_at"])
    return {"ok": True, "message": "Quote sent to customer.", "id": quote.id}


@router.post("/quotes/{quote_id}/accept", response=ActionResponse, summary="Mark Quote as Accepted")
def accept_quote(request, quote_id: uuid.UUID):
    from apps.crm.models import Quote
    quote = get_object_or_404(Quote, id=quote_id, is_deleted=False)
    if quote.status != Quote.Status.SENT:
        raise HttpError(400, "Only Sent quotes can be accepted.")
    quote.status = Quote.Status.ACCEPTED
    quote.accepted_at = timezone.now()
    quote.save(update_fields=["status", "accepted_at", "updated_at"])
    return {"ok": True, "message": "Quote accepted.", "id": quote.id}


@router.post("/quotes/{quote_id}/reject", response=ActionResponse, summary="Mark Quote as Rejected")
def reject_quote(request, quote_id: uuid.UUID):
    from apps.crm.models import Quote
    quote = get_object_or_404(Quote, id=quote_id, is_deleted=False)
    if quote.status != Quote.Status.SENT:
        raise HttpError(400, "Only Sent quotes can be rejected.")
    quote.status = Quote.Status.REJECTED
    quote.rejected_at = timezone.now()
    quote.save(update_fields=["status", "rejected_at", "updated_at"])
    return {"ok": True, "message": "Quote rejected.", "id": quote.id}


class AddQuoteItemSchema(Schema):
    description: str
    quantity: float = 1.0
    unit_price: float
    discount_pct: float = 0.0


class QuoteItemResponse(Schema):
    ok: bool
    message: str
    item_id: Optional[uuid.UUID] = None
    grand_total: float


@router.post("/quotes/{quote_id}/add-item", response=QuoteItemResponse, summary="Add Line Item to Quote")
def add_quote_item(request, quote_id: uuid.UUID, payload: AddQuoteItemSchema):
    from apps.crm.models import Quote, QuoteItem
    quote = get_object_or_404(Quote, id=quote_id, is_deleted=False)
    if quote.status not in (Quote.Status.DRAFT,):
        raise HttpError(400, "Line items can only be added to Draft quotes.")
    item = QuoteItem.objects.create(
        quote=quote,
        description=payload.description,
        quantity=Decimal(str(payload.quantity)),
        unit_price=Decimal(str(payload.unit_price)),
        discount_pct=Decimal(str(payload.discount_pct)),
        company_id=quote.company_id,
    )
    quote.recalculate_totals()
    quote.save(update_fields=["subtotal", "grand_total", "updated_at"])
    return {
        "ok": True,
        "message": "Item added.",
        "item_id": item.id,
        "grand_total": float(quote.grand_total),
    }
