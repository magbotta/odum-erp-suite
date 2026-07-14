"""Government action endpoints (§7 / §7.9)."""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import List, Optional

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from core.platform_api.security import AuthBearer

router = Router(tags=["Government Actions"], auth=AuthBearer())


class ActionResponse(Schema):
    ok: bool
    message: str


# ── Tender lifecycle ──────────────────────────────────────────────────────────

class AwardTenderIn(Schema):
    vendor_id: str
    vendor_name: Optional[str] = None
    awarded_amount: float


@router.post("/tenders/{tender_id}/publish", response=ActionResponse)
def publish_tender(request, tender_id: uuid.UUID):
    from apps.government.models import Tender
    from apps.government.hooks.tender import publish_tender as do_publish, set_tender_number
    tender = get_object_or_404(Tender, id=tender_id, is_deleted=False)
    if tender.status != "draft":
        return {"ok": False, "message": "Only Draft tenders can be published."}
    set_tender_number(tender)
    do_publish(tender)
    tender.save()
    return {"ok": True, "message": "Tender {} published. OCDS ID: {}".format(
        tender.tender_number, tender.ocds_ocid)}


@router.post("/tenders/{tender_id}/open-submissions", response=ActionResponse)
def open_submissions(request, tender_id: uuid.UUID):
    from apps.government.models import Tender
    from apps.government.hooks.tender import open_submissions as do_open
    tender = get_object_or_404(Tender, id=tender_id, is_deleted=False)
    if tender.status != "published":
        return {"ok": False, "message": "Tender must be Published to open submissions."}
    do_open(tender)
    tender.save()
    return {"ok": True, "message": "Submissions now open for {}.".format(tender.tender_number)}


@router.post("/tenders/{tender_id}/close-submissions", response=ActionResponse)
def close_submissions(request, tender_id: uuid.UUID):
    from apps.government.models import Tender
    from apps.government.hooks.tender import close_submissions as do_close
    tender = get_object_or_404(Tender, id=tender_id, is_deleted=False)
    if tender.status != "submissions_open":
        return {"ok": False, "message": "Tender must be in Submissions Open status."}
    do_close(tender)
    tender.save()
    return {"ok": True, "message": "Submissions closed for {}. Evaluation in progress.".format(
        tender.tender_number)}


@router.post("/tenders/{tender_id}/award", response=ActionResponse)
def award_tender(request, tender_id: uuid.UUID, payload: AwardTenderIn):
    from apps.government.models import Tender
    from apps.government.hooks.tender import award_tender as do_award
    tender = get_object_or_404(Tender, id=tender_id, is_deleted=False)
    if tender.status != "evaluation":
        return {"ok": False, "message": "Tender must be Under Evaluation to award."}
    vendor_id = uuid.UUID(payload.vendor_id)
    do_award(tender, vendor_id=vendor_id, awarded_amount=Decimal(str(payload.awarded_amount)))
    if payload.vendor_name:
        tender.awarded_vendor_name = payload.vendor_name
    tender.save()
    return {"ok": True, "message": "Tender {} awarded to {} for {:.2f}.".format(
        tender.tender_number, payload.vendor_name or str(vendor_id),
        float(tender.awarded_amount))}


@router.post("/tenders/{tender_id}/cancel", response=ActionResponse)
def cancel_tender(request, tender_id: uuid.UUID):
    from apps.government.models import Tender
    from apps.government.hooks.tender import cancel_tender as do_cancel
    tender = get_object_or_404(Tender, id=tender_id, is_deleted=False)
    if tender.status in ("awarded", "cancelled"):
        return {"ok": False, "message": "Cannot cancel a {} tender.".format(tender.status)}
    do_cancel(tender)
    tender.save()
    return {"ok": True, "message": "Tender {} cancelled.".format(tender.tender_number)}


# ── Permit lifecycle ──────────────────────────────────────────────────────────

class RejectIn(Schema):
    reason: str


class IssuePermitIn(Schema):
    expiry_date: Optional[str] = None
    conditions: Optional[str] = None


@router.post("/permits/{permit_id}/submit", response=ActionResponse)
def submit_permit(request, permit_id: uuid.UUID):
    from apps.government.models import Permit
    from apps.government.hooks.permit import submit_permit as do_submit
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    if permit.status != "draft":
        return {"ok": False, "message": "Only Draft permits can be submitted."}
    do_submit(permit)
    permit.save()
    return {"ok": True, "message": "Permit {} submitted for review.".format(permit.permit_number)}


@router.post("/permits/{permit_id}/approve", response=ActionResponse)
def approve_permit(request, permit_id: uuid.UUID, payload: Optional[IssuePermitIn] = None):
    from apps.government.models import Permit
    from apps.government.hooks.permit import approve_permit as do_approve
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    if permit.status not in ("submitted", "under_review"):
        return {"ok": False, "message": "Permit must be Submitted or Under Review to approve."}
    conditions = payload.conditions if payload else ""
    do_approve(permit, conditions=conditions or "")
    permit.save()
    return {"ok": True, "message": "Permit {} approved.".format(permit.permit_number)}


@router.post("/permits/{permit_id}/reject", response=ActionResponse)
def reject_permit(request, permit_id: uuid.UUID, payload: RejectIn):
    from apps.government.models import Permit
    from apps.government.hooks.permit import reject_permit as do_reject
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    if permit.status in ("issued", "rejected", "revoked"):
        return {"ok": False, "message": "Cannot reject a permit in {} status.".format(permit.status)}
    do_reject(permit, reason=payload.reason)
    permit.save()
    return {"ok": True, "message": "Permit {} rejected.".format(permit.permit_number)}


@router.post("/permits/{permit_id}/issue", response=ActionResponse)
def issue_permit(request, permit_id: uuid.UUID, payload: Optional[IssuePermitIn] = None):
    from apps.government.models import Permit
    from apps.government.hooks.permit import issue_permit as do_issue
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    expiry_date = None
    if payload and payload.expiry_date:
        try:
            expiry_date = datetime.date.fromisoformat(payload.expiry_date)
        except ValueError:
            return {"ok": False, "message": "Invalid expiry_date format. Use YYYY-MM-DD."}
    try:
        do_issue(permit, expiry_date=expiry_date)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    permit.save()
    return {"ok": True, "message": "Permit {} issued (expires {}).".format(
        permit.permit_number, permit.expiry_date)}


@router.post("/permits/{permit_id}/revoke", response=ActionResponse)
def revoke_permit(request, permit_id: uuid.UUID, payload: RejectIn):
    from apps.government.models import Permit
    from apps.government.hooks.permit import revoke_permit as do_revoke
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    if permit.status != "issued":
        return {"ok": False, "message": "Only Issued permits can be revoked."}
    do_revoke(permit, reason=payload.reason)
    permit.save()
    return {"ok": True, "message": "Permit {} revoked.".format(permit.permit_number)}


# ── Citizen Service Requests (311) ────────────────────────────────────────────

class AssignRequestIn(Schema):
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    department: Optional[str] = None


@router.post("/service-requests/{request_id}/assign", response=ActionResponse)
def assign_service_request(request, request_id: uuid.UUID, payload: Optional[AssignRequestIn] = None):
    from apps.government.models import CitizenServiceRequest
    from apps.government.hooks.service_request import assign_request
    req = get_object_or_404(CitizenServiceRequest, id=request_id, is_deleted=False)
    if req.status != "open":
        return {"ok": False, "message": "Only Open requests can be assigned."}
    assign_request(req)
    if payload:
        if payload.employee_id:
            try:
                req.assigned_to_employee_id = uuid.UUID(payload.employee_id)
            except ValueError:
                pass
        if payload.employee_name:
            req.assigned_to_name = payload.employee_name
        if payload.department:
            req.assigned_department = payload.department
    req.save()
    return {"ok": True, "message": "Request {} assigned to {}.".format(
        req.request_number, req.assigned_to_name or req.assigned_department or "department")}


@router.post("/service-requests/{request_id}/start", response=ActionResponse)
def start_service_request(request, request_id: uuid.UUID):
    from apps.government.models import CitizenServiceRequest
    from apps.government.hooks.service_request import start_work
    req = get_object_or_404(CitizenServiceRequest, id=request_id, is_deleted=False)
    if req.status != "assigned":
        return {"ok": False, "message": "Request must be Assigned to start work."}
    start_work(req)
    req.save()
    return {"ok": True, "message": "Request {} is now In Progress.".format(req.request_number)}


@router.post("/service-requests/{request_id}/resolve", response=ActionResponse)
def resolve_service_request(request, request_id: uuid.UUID, payload: Optional[RejectIn] = None):
    from apps.government.models import CitizenServiceRequest
    from apps.government.hooks.service_request import resolve_request
    req = get_object_or_404(CitizenServiceRequest, id=request_id, is_deleted=False)
    if req.status not in ("assigned", "in_progress"):
        return {"ok": False, "message": "Request must be Assigned or In Progress to resolve."}
    resolve_request(req)
    if payload:
        req.resolution_notes = payload.reason
    req.save()
    return {"ok": True, "message": "Request {} resolved.".format(req.request_number)}


@router.post("/service-requests/{request_id}/close", response=ActionResponse)
def close_service_request(request, request_id: uuid.UUID):
    from apps.government.models import CitizenServiceRequest
    from apps.government.hooks.service_request import close_request
    req = get_object_or_404(CitizenServiceRequest, id=request_id, is_deleted=False)
    if req.status != "resolved":
        return {"ok": False, "message": "Request must be Resolved before closing."}
    close_request(req)
    req.save()
    return {"ok": True, "message": "Request {} closed.".format(req.request_number)}


# ── FOIA Requests ─────────────────────────────────────────────────────────────

class FulfillFOIAIn(Schema):
    response_notes: Optional[str] = None


class DenyFOIAIn(Schema):
    denial_reason: str
    denial_exemption: Optional[str] = None


@router.post("/foia/{foia_id}/acknowledge", response=ActionResponse)
def acknowledge_foia(request, foia_id: uuid.UUID):
    from apps.government.models import FOIARequest
    req = get_object_or_404(FOIARequest, id=foia_id, is_deleted=False)
    if req.status != "received":
        return {"ok": False, "message": "FOIA request is already past Received status."}
    req.status = "in_review"
    req.acknowledged_date = datetime.date.today()
    req.save()
    return {"ok": True, "message": "FOIA {} acknowledged and moved to In Review.".format(
        req.request_number)}


@router.post("/foia/{foia_id}/fulfill", response=ActionResponse)
def fulfill_foia(request, foia_id: uuid.UUID, payload: Optional[FulfillFOIAIn] = None):
    from apps.government.models import FOIARequest
    req = get_object_or_404(FOIARequest, id=foia_id, is_deleted=False)
    if req.status in ("fulfilled", "denied"):
        return {"ok": False, "message": "FOIA request is already {}.".format(req.status)}
    req.status = "fulfilled"
    req.fulfilled_date = datetime.date.today()
    if payload and payload.response_notes:
        req.response_notes = payload.response_notes
    req.save()
    return {"ok": True, "message": "FOIA {} fulfilled.".format(req.request_number)}


@router.post("/foia/{foia_id}/deny", response=ActionResponse)
def deny_foia(request, foia_id: uuid.UUID, payload: DenyFOIAIn):
    from apps.government.models import FOIARequest
    req = get_object_or_404(FOIARequest, id=foia_id, is_deleted=False)
    if req.status in ("fulfilled", "denied"):
        return {"ok": False, "message": "FOIA request is already {}.".format(req.status)}
    req.status = "denied"
    req.denial_reason = payload.denial_reason
    if payload.denial_exemption:
        req.denial_exemption = payload.denial_exemption
    req.save()
    return {"ok": True, "message": "FOIA {} denied.".format(req.request_number)}


@router.post("/foia/{foia_id}/appeal", response=ActionResponse)
def appeal_foia(request, foia_id: uuid.UUID):
    from apps.government.models import FOIARequest
    req = get_object_or_404(FOIARequest, id=foia_id, is_deleted=False)
    if req.status != "denied":
        return {"ok": False, "message": "Only denied FOIA requests can be appealed."}
    req.status = "appealed"
    req.save()
    return {"ok": True, "message": "FOIA {} under appeal.".format(req.request_number)}


# ── Grant applications ────────────────────────────────────────────────────────

class ApproveGrantIn(Schema):
    approved_amount: Optional[float] = None
    award_date: Optional[str] = None


@router.post("/grants/{grant_id}/submit", response=ActionResponse)
def submit_grant(request, grant_id: uuid.UUID):
    from apps.government.models import GrantApplication
    from apps.government.hooks.grant import submit_grant as do_submit
    grant = get_object_or_404(GrantApplication, id=grant_id, is_deleted=False)
    if grant.status != "draft":
        return {"ok": False, "message": "Only Draft grants can be submitted."}
    do_submit(grant)
    grant.save()
    return {"ok": True, "message": "Grant {} submitted.".format(grant.grant_number)}


@router.post("/grants/{grant_id}/approve", response=ActionResponse)
def approve_grant(request, grant_id: uuid.UUID, payload: Optional[ApproveGrantIn] = None):
    from apps.government.models import GrantApplication
    from apps.government.hooks.grant import approve_grant as do_approve
    grant = get_object_or_404(GrantApplication, id=grant_id, is_deleted=False)
    if grant.status not in ("submitted", "under_review"):
        return {"ok": False, "message": "Grant must be Submitted or Under Review to approve."}
    amt = Decimal(str(payload.approved_amount)) if payload and payload.approved_amount else None
    award_date = None
    if payload and payload.award_date:
        try:
            award_date = datetime.date.fromisoformat(payload.award_date)
        except ValueError:
            return {"ok": False, "message": "Invalid award_date. Use YYYY-MM-DD."}
    do_approve(grant, approved_amount=amt, award_date=award_date)
    grant.save()
    return {"ok": True, "message": "Grant {} approved for {:.2f}.".format(
        grant.grant_number, float(grant.approved_amount))}


@router.post("/grants/{grant_id}/reject", response=ActionResponse)
def reject_grant(request, grant_id: uuid.UUID, payload: RejectIn):
    from apps.government.models import GrantApplication
    from apps.government.hooks.grant import reject_grant as do_reject
    grant = get_object_or_404(GrantApplication, id=grant_id, is_deleted=False)
    if grant.status in ("rejected", "closed"):
        return {"ok": False, "message": "Grant is already {}.".format(grant.status)}
    do_reject(grant, reason=payload.reason)
    grant.save()
    return {"ok": True, "message": "Grant {} rejected.".format(grant.grant_number)}


# ── Analytics ─────────────────────────────────────────────────────────────────

class GovernmentAnalytics(Schema):
    total_tenders: int
    tenders_open: int
    tenders_awarded: int
    total_permits: int
    permits_pending: int
    permits_issued: int
    total_service_requests: int
    requests_open: int
    requests_resolved: int
    total_foia_requests: int
    foia_pending: int
    total_grant_applications: int
    grants_active: int
    total_gasb_funds: int
    total_appropriated_budget: float
    total_encumbered: float
    total_expended: float


# ── Revenue Collection ────────────────────────────────────────────────────────

class CollectPaymentIn(Schema):
    provider: str  # mtn_momo, airteltigo, vodafone_cash, cash, bank_transfer
    payer_phone: str
    amount: float
    company_id: Optional[str] = None


class CollectPaymentOut(Schema):
    ok: bool
    payment_event_id: Optional[str] = None
    status: str
    message: str


class WebhookIn(Schema):
    provider: str


class WebhookOut(Schema):
    processed: bool
    idempotent_duplicate: bool
    message: str
    receipt_number: Optional[str] = None


class BillRunIn(Schema):
    fiscal_year: int
    company_id: str


class BillRunOut(Schema):
    bills_created: int
    bill_ids: List[str]


class IGFSummaryOut(Schema):
    fiscal_year: int
    by_type: dict


@router.post("/revenue/bills/{bill_id}/collect-payment", response=CollectPaymentOut)
def collect_payment(request, bill_id: uuid.UUID, payload: CollectPaymentIn):
    """
    Initiate a mobile money or cash payment against a GovernmentRevenueBill.
    For cash payments, the bill is confirmed immediately.
    For mobile money, a USSD prompt is sent and confirmation arrives via webhook.
    """
    from apps.government.models import GovernmentRevenueBill
    from core.payments_gateway.gateway import (
        default_gateway, PaymentRequest, CashPaymentRequest
    )

    try:
        bill = GovernmentRevenueBill.objects.get(id=bill_id, is_deleted=False)
    except GovernmentRevenueBill.DoesNotExist:
        return CollectPaymentOut(ok=False, payment_event_id=None,
                                 status="error", message="Bill not found.")

    if bill.bill_status in ("paid", "cancelled", "written_off"):
        return CollectPaymentOut(
            ok=False, payment_event_id=None,
            status="error",
            message="Bill is already {0}.".format(bill.bill_status),
        )

    amount = Decimal(str(payload.amount))
    company_id = payload.company_id or str(bill.company_id or "")
    revenue_type = "{0}:{1}".format(bill.bill_type, bill.fiscal_year)

    if payload.provider == "cash":
        result = default_gateway.record_cash(CashPaymentRequest(
            amount=amount,
            currency=bill.currency,
            payable_document_id=str(bill.id),
            payable_document_type="GovernmentRevenueBill",
            revenue_type=revenue_type,
            collector_id=str(getattr(request, "user_id", "system")),
        ))
        if result.success:
            from apps.government.hooks.revenue import on_payment_confirmed
            receipt_no = on_payment_confirmed(
                payment_event_id=result.gateway_reference,
                bill_id=str(bill.id),
                amount=amount,
                channel="cash",
                company_id=company_id,
            )
            return CollectPaymentOut(
                ok=True, payment_event_id=result.gateway_reference,
                status="confirmed", message="Cash receipt: {0}".format(receipt_no),
            )
    else:
        result = default_gateway.initiate(PaymentRequest(
            provider=payload.provider,
            amount=amount,
            currency=bill.currency,
            payer_phone=payload.payer_phone,
            payable_document_id=str(bill.id),
            payable_document_type="GovernmentRevenueBill",
            revenue_type=revenue_type,
            description="Payment for {0} {1}".format(bill.bill_type, bill.bill_number),
        ))
        return CollectPaymentOut(
            ok=result.success,
            payment_event_id=result.gateway_reference or None,
            status=result.status,
            message=result.message,
        )

    return CollectPaymentOut(ok=False, payment_event_id=None,
                              status="error", message="Payment failed.")


@router.post("/revenue/webhook/{provider}", response=WebhookOut)
def payment_webhook(request, provider: str):
    """
    Inbound payment provider webhook endpoint.
    Handles mobile money confirmations idempotently — duplicate callbacks are ignored.
    """
    from core.payments_gateway.gateway import default_gateway

    raw_body = getattr(request, "body", b"{}")
    headers = dict(getattr(request, "headers", {}))
    result = default_gateway.handle_webhook(provider, raw_body, headers)

    receipt_number = None
    if result.processed and result.payment_result and result.payment_result.success:
        # The webhook doesn't carry bill_id unless the driver extracts it from payload.
        # Real deployments encode bill_id in externalId / external_reference; the driver
        # populates payable_document_id from that field.  We attempt receipt generation here.
        pr = result.payment_result
        if pr.provider_tx_id:
            from core.payments_gateway.models import PaymentEvent
            event = PaymentEvent.objects.filter(
                provider_tx_id=pr.provider_tx_id, status="confirmed"
            ).first()
            if event and event.payable_document_id:
                try:
                    from apps.government.hooks.revenue import on_payment_confirmed
                    receipt_number = on_payment_confirmed(
                        payment_event_id=str(event.id),
                        bill_id=event.payable_document_id,
                        amount=event.amount,
                        channel=event.provider,
                        company_id=str(event.company_id or ""),
                    )
                except Exception:
                    pass  # GL posting failure logged inside hook; webhook still acks

    return WebhookOut(
        processed=result.processed,
        idempotent_duplicate=result.idempotent_duplicate,
        message=result.message,
        receipt_number=receipt_number,
    )


@router.post("/revenue/property-rate-bill-run", response=BillRunOut)
def property_rate_bill_run(request, payload: BillRunIn):
    """
    Run the annual property rate billing for all active parcels.
    Idempotent: safe to re-run; parcels already billed for the fiscal year are skipped.
    """
    from apps.government.hooks.revenue import run_property_rate_bill_run
    ids = run_property_rate_bill_run(
        fiscal_year=payload.fiscal_year,
        company_id=payload.company_id,
    )
    return BillRunOut(bills_created=len(ids), bill_ids=ids)


@router.post("/permits/{permit_id}/generate-fee-bill", response=ActionResponse)
def generate_permit_fee_bill_endpoint(request, permit_id: uuid.UUID):
    """Generate a GovernmentRevenueBill for this permit's fee (idempotent)."""
    from apps.government.models import Permit
    from apps.government.hooks.revenue import generate_permit_fee_bill
    permit = get_object_or_404(Permit, id=permit_id, is_deleted=False)
    company_id = str(permit.company_id or "")
    bill_id = generate_permit_fee_bill(str(permit_id), company_id)
    if bill_id is None:
        return {"ok": False, "message": "No fee configured on this permit."}
    return {"ok": True, "message": "Fee bill {0} created/exists.".format(bill_id)}


@router.get("/revenue/igf-summary", response=IGFSummaryOut)
def igf_summary(request, fiscal_year: int, company_id: str):
    """
    Return confirmed IGF revenue collected by type for the given fiscal year.
    Queries PaymentEvent (not billed amounts) for actual collected figures.
    """
    from apps.government.hooks.revenue import igf_revenue_summary
    summary = igf_revenue_summary(fiscal_year=fiscal_year, company_id=company_id)
    return IGFSummaryOut(
        fiscal_year=fiscal_year,
        by_type={k: float(v) for k, v in summary.items()},
    )


@router.get("/analytics/summary", response=GovernmentAnalytics)
def analytics_summary(request, company_id: Optional[str] = None):
    from django.db.models import Sum
    from apps.government.models import (
        Tender, Permit, CitizenServiceRequest, FOIARequest, GrantApplication, GASBFund
    )

    def qs(model):
        q = model.objects.filter(is_deleted=False)
        if company_id:
            q = q.filter(company_id=company_id)
        return q

    funds = qs(GASBFund)
    fund_totals = funds.aggregate(
        ta=Sum("appropriated_budget"),
        te=Sum("encumbered_amount"),
        tx=Sum("expended_amount"),
    )

    return GovernmentAnalytics(
        total_tenders=qs(Tender).count(),
        tenders_open=qs(Tender).filter(status__in=["published", "submissions_open", "evaluation"]).count(),
        tenders_awarded=qs(Tender).filter(status="awarded").count(),
        total_permits=qs(Permit).count(),
        permits_pending=qs(Permit).filter(status__in=["submitted", "under_review"]).count(),
        permits_issued=qs(Permit).filter(status="issued").count(),
        total_service_requests=qs(CitizenServiceRequest).count(),
        requests_open=qs(CitizenServiceRequest).filter(
            status__in=["open", "assigned", "in_progress"]
        ).count(),
        requests_resolved=qs(CitizenServiceRequest).filter(
            status__in=["resolved", "closed"]
        ).count(),
        total_foia_requests=qs(FOIARequest).count(),
        foia_pending=qs(FOIARequest).filter(
            status__in=["received", "in_review", "awaiting_info"]
        ).count(),
        total_grant_applications=qs(GrantApplication).count(),
        grants_active=qs(GrantApplication).filter(status="active").count(),
        total_gasb_funds=funds.count(),
        total_appropriated_budget=float(fund_totals["ta"] or 0),
        total_encumbered=float(fund_totals["te"] or 0),
        total_expended=float(fund_totals["tx"] or 0),
    )
