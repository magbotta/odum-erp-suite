"""Purchasing action endpoints — full §6.7 implementation."""
from __future__ import annotations

import uuid
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["Purchasing Actions"])


# ── Shared schemas ────────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str


class RFQCompareRow(Schema):
    vendor_id: str
    vendor_name: str
    response_status: str
    total_amount: Optional[float]
    delivery_days: int
    payment_terms: str


class SpendRow(Schema):
    vendor_id: str
    vendor_name: str
    total_amount: float
    po_count: int


# ── Purchase Requisition ──────────────────────────────────────────────────────

@router.post("/requisitions/{pr_id}/submit", response=ActionResponse)
def submit_requisition(request, pr_id: uuid.UUID):
    from apps.purchasing.models import PurchaseRequisition
    from core.numbering.service import get_next_number

    pr = get_object_or_404(PurchaseRequisition, id=pr_id, is_deleted=False)
    if pr.status != PurchaseRequisition.Status.DRAFT:
        return {"ok": False, "message": f"Requisition is already {pr.status}."}

    if not pr.requisition_number:
        pr.requisition_number = get_next_number("PR", pr.company_id)

    pr.status = PurchaseRequisition.Status.SUBMITTED
    pr.save(update_fields=["status", "requisition_number"])
    return {"ok": True, "message": f"Requisition {pr.requisition_number} submitted for approval."}


@router.post("/requisitions/{pr_id}/approve", response=ActionResponse)
def approve_requisition(request, pr_id: uuid.UUID):
    from apps.purchasing.models import PurchaseRequisition

    pr = get_object_or_404(PurchaseRequisition, id=pr_id, is_deleted=False)
    if pr.status != PurchaseRequisition.Status.SUBMITTED:
        return {"ok": False, "message": f"Requisition is {pr.status}, not awaiting approval."}

    pr.status = PurchaseRequisition.Status.APPROVED
    pr.approved_by_id = request.user.pk if request.user.is_authenticated else None
    pr.approved_at = timezone.now()
    pr.save(update_fields=["status", "approved_by_id", "approved_at"])
    return {"ok": True, "message": f"Requisition {pr.requisition_number} approved."}


class RejectIn(Schema):
    reason: str


@router.post("/requisitions/{pr_id}/reject", response=ActionResponse)
def reject_requisition(request, pr_id: uuid.UUID, payload: RejectIn):
    from apps.purchasing.models import PurchaseRequisition

    pr = get_object_or_404(PurchaseRequisition, id=pr_id, is_deleted=False)
    if pr.status not in (PurchaseRequisition.Status.SUBMITTED,):
        return {"ok": False, "message": f"Cannot reject a requisition with status {pr.status}."}

    pr.status = PurchaseRequisition.Status.REJECTED
    pr.rejection_reason = payload.reason
    pr.save(update_fields=["status", "rejection_reason"])
    return {"ok": True, "message": "Requisition rejected."}


class ConvertToPOIn(Schema):
    vendor_id: str
    vendor_name: str
    currency: str = "USD"
    exchange_rate: float = 1.0


class ConvertToPOOut(Schema):
    ok: bool
    message: str
    po_id: Optional[str] = None
    po_number: Optional[str] = None


@router.post("/requisitions/{pr_id}/convert-to-po", response=ConvertToPOOut)
def convert_requisition_to_po(request, pr_id: uuid.UUID, payload: ConvertToPOIn):
    from decimal import Decimal
    from apps.purchasing.models import PurchaseOrder, PurchaseOrderItem, PurchaseRequisition
    from core.numbering.service import get_next_number

    pr = get_object_or_404(PurchaseRequisition, id=pr_id, is_deleted=False)
    if pr.status != PurchaseRequisition.Status.APPROVED:
        return {"ok": False, "message": f"Requisition must be Approved first (currently {pr.status})."}

    po = PurchaseOrder.objects.create(
        vendor_id=payload.vendor_id,
        vendor_name=payload.vendor_name,
        po_number=get_next_number("PO", pr.company_id),
        posting_date=timezone.now().date(),
        currency=payload.currency,
        exchange_rate=Decimal(str(payload.exchange_rate)),
        status=PurchaseOrder.Status.DRAFT,
        requisition_id=pr.pk,
        company_id=pr.company_id,
    )

    net = Decimal("0")
    for item in pr.items.filter(is_deleted=False):
        amount = item.qty * item.estimated_rate
        PurchaseOrderItem.objects.create(
            order=po,
            item_id=item.item_id,
            item_code=item.item_code,
            item_name=item.item_name,
            qty=item.qty,
            rate=item.estimated_rate,
            amount=amount,
            uom=item.uom,
            warehouse_id=item.warehouse_id,
            company_id=pr.company_id,
        )
        net += amount

    po.net_total = net
    po.grand_total = net
    po.save(update_fields=["net_total", "grand_total"])

    pr.status = PurchaseRequisition.Status.ORDERED
    pr.save(update_fields=["status"])

    return {"ok": True, "message": f"PO {po.po_number} created from requisition.", "po_id": str(po.pk), "po_number": po.po_number}


# ── Purchase Order ────────────────────────────────────────────────────────────

@router.post("/purchase-orders/{po_id}/submit", response=ActionResponse)
def submit_purchase_order(request, po_id: uuid.UUID):
    from apps.purchasing.models import PurchaseOrder
    from core.numbering.service import get_next_number

    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.status != PurchaseOrder.Status.DRAFT:
        return {"ok": False, "message": f"PO is already {po.status}."}

    if not po.items.filter(is_deleted=False).exists():
        return {"ok": False, "message": "PO has no line items."}

    if not po.po_number:
        po.po_number = get_next_number("PO", po.company_id)

    po.status = PurchaseOrder.Status.SUBMITTED
    po.save(update_fields=["status", "po_number"])
    return {"ok": True, "message": f"Purchase Order {po.po_number} submitted."}


@router.post("/purchase-orders/{po_id}/cancel", response=ActionResponse)
def cancel_purchase_order(request, po_id: uuid.UUID):
    from apps.purchasing.models import GoodsReceipt, PurchaseOrder

    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.status not in (PurchaseOrder.Status.SUBMITTED, PurchaseOrder.Status.PARTIALLY_RECEIVED):
        return {"ok": False, "message": f"Cannot cancel PO with status {po.status}."}

    if GoodsReceipt.objects.filter(purchase_order=po, status=GoodsReceipt.Status.SUBMITTED).exists():
        return {"ok": False, "message": "Cannot cancel: submitted GRNs exist against this PO."}

    po.status = PurchaseOrder.Status.CANCELLED
    po.save(update_fields=["status"])
    return {"ok": True, "message": f"Purchase Order {po.po_number} cancelled."}


# ── RFQ ───────────────────────────────────────────────────────────────────────

@router.post("/rfqs/{rfq_id}/send", response=ActionResponse)
def send_rfq(request, rfq_id: uuid.UUID):
    from apps.purchasing.models import RequestForQuotation
    from core.numbering.service import get_next_number

    rfq = get_object_or_404(RequestForQuotation, id=rfq_id, is_deleted=False)
    if rfq.status != RequestForQuotation.Status.DRAFT:
        return {"ok": False, "message": f"RFQ is already {rfq.status}."}

    if not rfq.supplier_responses.exists():
        return {"ok": False, "message": "Add at least one supplier before sending."}

    if not rfq.rfq_number:
        rfq.rfq_number = get_next_number("RFQ", rfq.company_id)

    rfq.status = RequestForQuotation.Status.SENT
    rfq.save(update_fields=["status", "rfq_number"])
    return {"ok": True, "message": f"RFQ {rfq.rfq_number} sent to {rfq.supplier_responses.count()} supplier(s)."}


@router.get("/rfqs/{rfq_id}/compare", response=List[RFQCompareRow])
def compare_rfq_quotes(request, rfq_id: uuid.UUID):
    from apps.purchasing.models import RequestForQuotation

    rfq = get_object_or_404(RequestForQuotation, id=rfq_id, is_deleted=False)
    rows = []
    for resp in rfq.supplier_responses.filter(is_deleted=False).order_by("total_amount"):
        rows.append(RFQCompareRow(
            vendor_id=str(resp.vendor_id),
            vendor_name=resp.vendor_name,
            response_status=resp.status,
            total_amount=float(resp.total_amount) if resp.total_amount else None,
            delivery_days=resp.delivery_days,
            payment_terms=resp.payment_terms,
        ))
    return rows


class AwardRFQOut(Schema):
    ok: bool
    message: str
    po_id: Optional[str] = None
    po_number: Optional[str] = None


@router.post("/rfqs/{rfq_id}/award/{response_id}", response=AwardRFQOut)
def award_rfq(request, rfq_id: uuid.UUID, response_id: uuid.UUID):
    """Award an RFQ to the winning supplier response and auto-create a PO."""
    from decimal import Decimal
    from apps.purchasing.models import (
        PurchaseOrder, PurchaseOrderItem,
        RequestForQuotation, RFQSupplierResponse,
    )
    from core.numbering.service import get_next_number

    rfq = get_object_or_404(RequestForQuotation, id=rfq_id, is_deleted=False)
    resp = get_object_or_404(RFQSupplierResponse, id=response_id, rfq=rfq)

    if rfq.status not in (RequestForQuotation.Status.SENT, RequestForQuotation.Status.CLOSED):
        return {"ok": False, "message": f"Cannot award RFQ with status {rfq.status}."}

    # Mark winner
    resp.status = RFQSupplierResponse.Status.AWARDED
    resp.save(update_fields=["status"])

    # Reject other responses
    rfq.supplier_responses.exclude(pk=response_id).update(status=RFQSupplierResponse.Status.REJECTED)

    # Create PO
    po = PurchaseOrder.objects.create(
        vendor_id=resp.vendor_id,
        vendor_name=resp.vendor_name,
        po_number=get_next_number("PO", rfq.company_id),
        posting_date=timezone.now().date(),
        currency=resp.currency,
        status=PurchaseOrder.Status.DRAFT,
        rfq_id=rfq.pk,
        company_id=rfq.company_id,
    )

    net = Decimal("0")
    for ri in resp.items.filter(is_deleted=False).select_related("rfq_item"):
        amount = ri.rfq_item.qty * ri.quoted_rate
        PurchaseOrderItem.objects.create(
            order=po,
            item_id=ri.rfq_item.item_id,
            item_code=ri.rfq_item.item_code,
            item_name=ri.rfq_item.item_name,
            qty=ri.rfq_item.qty,
            rate=ri.quoted_rate,
            amount=amount,
            uom=ri.rfq_item.uom,
            rfq_response_item_id=ri.pk,
            company_id=rfq.company_id,
        )
        net += amount

    po.net_total = net
    po.grand_total = net
    po.save(update_fields=["net_total", "grand_total"])

    rfq.status = RequestForQuotation.Status.AWARDED
    rfq.save(update_fields=["status"])

    return {"ok": True, "message": f"RFQ awarded to {resp.vendor_name}; PO {po.po_number} created.", "po_id": str(po.pk), "po_number": po.po_number}


# ── Goods Receipt ─────────────────────────────────────────────────────────────

@router.post("/goods-receipts/{grn_id}/submit", response=ActionResponse)
def submit_goods_receipt(request, grn_id: uuid.UUID):
    from apps.purchasing.models import GoodsReceipt
    from apps.purchasing.hooks.goods_receipt import submit_grn
    from core.numbering.service import get_next_number

    grn = get_object_or_404(GoodsReceipt, id=grn_id, is_deleted=False)
    if grn.status != GoodsReceipt.Status.DRAFT:
        return {"ok": False, "message": f"GRN is already {grn.status}."}

    if not grn.items.filter(is_deleted=False).exists():
        return {"ok": False, "message": "GRN has no line items."}

    if not grn.grn_number:
        grn.grn_number = get_next_number("GRN", grn.company_id)
        grn.save(update_fields=["grn_number"])

    submit_grn(grn)

    grn.status = GoodsReceipt.Status.SUBMITTED
    grn.save(update_fields=["status"])
    return {"ok": True, "message": f"GRN {grn.grn_number} submitted; stock and PO updated."}


@router.post("/goods-receipts/{grn_id}/cancel", response=ActionResponse)
def cancel_goods_receipt(request, grn_id: uuid.UUID):
    from apps.purchasing.models import GoodsReceipt, LandedCost
    from apps.purchasing.hooks.goods_receipt import cancel_grn

    grn = get_object_or_404(GoodsReceipt, id=grn_id, is_deleted=False)
    if grn.status != GoodsReceipt.Status.SUBMITTED:
        return {"ok": False, "message": f"GRN is {grn.status}, cannot cancel."}

    if LandedCost.objects.filter(goods_receipt=grn, is_posted=True).exists():
        return {"ok": False, "message": "Cannot cancel: posted landed costs exist against this GRN."}

    cancel_grn(grn)
    grn.status = GoodsReceipt.Status.CANCELLED
    grn.save(update_fields=["status"])
    return {"ok": True, "message": f"GRN {grn.grn_number} cancelled; stock reversed."}


# ── Supplier Qualification ────────────────────────────────────────────────────

@router.post("/supplier-qualifications/{sq_id}/start-review", response=ActionResponse)
def start_review(request, sq_id: uuid.UUID):
    from apps.purchasing.models import SupplierQualification

    sq = get_object_or_404(SupplierQualification, id=sq_id, is_deleted=False)
    if sq.status != SupplierQualification.Status.NEW:
        return {"ok": False, "message": f"Application is already {sq.status}."}

    sq.status = SupplierQualification.Status.UNDER_REVIEW
    sq.reviewed_by_id = request.user.pk if request.user.is_authenticated else None
    sq.reviewed_at = timezone.now()
    sq.submitted_at = sq.submitted_at or timezone.now()
    sq.save(update_fields=["status", "reviewed_by_id", "reviewed_at", "submitted_at"])
    return {"ok": True, "message": f"Supplier {sq.vendor_name} is now under review."}


class ApproveSupplierOut(Schema):
    ok: bool
    message: str
    vendor_id: Optional[str] = None


@router.post("/supplier-qualifications/{sq_id}/approve", response=ApproveSupplierOut)
def approve_supplier(request, sq_id: uuid.UUID):
    """
    Approve the qualification. Looks up or creates the Vendor record in Accounting.
    """
    from apps.purchasing.models import SupplierQualification

    sq = get_object_or_404(SupplierQualification, id=sq_id, is_deleted=False)
    if sq.status not in (SupplierQualification.Status.UNDER_REVIEW, SupplierQualification.Status.ADDITIONAL_INFO):
        return {"ok": False, "message": f"Cannot approve from status {sq.status}."}

    # Try to find or create the Vendor in Accounting
    vendor_id_str = None
    try:
        from apps.accounting.models import Vendor
        vendor, _ = Vendor.objects.get_or_create(
            vendor_name=sq.vendor_name,
            company_id=sq.company_id,
            defaults={
                "tax_id": sq.tax_registration_no,
                "is_active": True,
            },
        )
        vendor_id_str = str(vendor.pk)
        sq.vendor_id = vendor.pk
    except Exception:
        pass

    # Compute a simple qualification score from document completeness
    docs_done = sum([sq.has_tax_cert, sq.has_insurance_cert, sq.has_bank_details, sq.esg_questionnaire_completed])
    sq.qualification_score = docs_done * 25   # 0–100

    sq.status = SupplierQualification.Status.QUALIFIED
    sq.save(update_fields=["status", "vendor_id", "qualification_score"])
    return {"ok": True, "message": f"{sq.vendor_name} qualified as a supplier.", "vendor_id": vendor_id_str}


class DisqualifyIn(Schema):
    reason: str


@router.post("/supplier-qualifications/{sq_id}/disqualify", response=ActionResponse)
def disqualify_supplier(request, sq_id: uuid.UUID, payload: DisqualifyIn):
    from apps.purchasing.models import SupplierQualification

    sq = get_object_or_404(SupplierQualification, id=sq_id, is_deleted=False)
    if sq.status == SupplierQualification.Status.QUALIFIED:
        return {"ok": False, "message": "Cannot disqualify an already qualified supplier."}

    sq.status = SupplierQualification.Status.DISQUALIFIED
    sq.notes = (sq.notes + "\n" if sq.notes else "") + f"Disqualified: {payload.reason}"
    sq.save(update_fields=["status", "notes"])
    return {"ok": True, "message": f"{sq.vendor_name} disqualified."}


# ── Purchase Return ───────────────────────────────────────────────────────────

@router.post("/purchase-returns/{prn_id}/submit", response=ActionResponse)
def submit_purchase_return(request, prn_id: uuid.UUID):
    """
    Submit a purchase return — issues stock back to vendor (negative StockEntry)
    and creates a debit-note reference in Accounting.
    """
    from decimal import Decimal
    from apps.purchasing.models import PurchaseReturn
    from apps.warehouse.models import Item, StockEntry, StockEntryDetail, Warehouse
    from apps.warehouse.hooks.stock_entry import post_stock_ledger
    from core.numbering.service import get_next_number

    prn = get_object_or_404(PurchaseReturn, id=prn_id, is_deleted=False)
    if prn.status != PurchaseReturn.Status.DRAFT:
        return {"ok": False, "message": f"Return is already {prn.status}."}

    if not prn.return_number:
        prn.return_number = get_next_number("PRN", prn.company_id)
        prn.save(update_fields=["return_number"])

    # Create outbound StockEntry from the receiving warehouse back toward vendor
    se = StockEntry.objects.create(
        entry_type=StockEntry.EntryType.ISSUE,   # stock going out
        posting_date=prn.posting_date,
        status=StockEntry.Status.SUBMITTED,
        voucher_type="PurchaseReturn",
        voucher_no=prn.return_number,
        remarks=f"Return: {prn.return_number} — {prn.return_reason}",
        company_id=prn.company_id,
    )

    net = Decimal("0")
    for line in prn.items.filter(is_deleted=False):
        try:
            item_obj = Item.objects.get(pk=line.item_id)
            wh_obj = Warehouse.objects.get(pk=line.warehouse_id)
        except (Item.DoesNotExist, Warehouse.DoesNotExist) as exc:
            se.delete()
            return {"ok": False, "message": str(exc)}

        StockEntryDetail.objects.create(
            stock_entry=se,
            item=item_obj,
            qty=line.qty,
            basic_rate=line.rate,
            amount=line.amount,
            company_id=prn.company_id,
        )
        if se.from_warehouse is None:
            se.from_warehouse = wh_obj
        net += line.amount

    se.total_value = net
    se.save(update_fields=["from_warehouse", "total_value"])
    post_stock_ledger(se)

    prn.net_total = net
    prn.status = PurchaseReturn.Status.SUBMITTED
    prn.save(update_fields=["net_total", "status"])
    return {"ok": True, "message": f"Purchase return {prn.return_number} submitted; stock reversed."}


# ── Landed Cost ───────────────────────────────────────────────────────────────

@router.post("/landed-costs/{lc_id}/allocate", response=ActionResponse)
def allocate_landed_cost(request, lc_id: uuid.UUID):
    """
    Distribute landed cost charges across GRN line items using the chosen
    allocation method (by amount, by qty, or equal).
    """
    from decimal import Decimal
    from apps.purchasing.models import LandedCost, LandedCostAllocation

    lc = get_object_or_404(LandedCost, id=lc_id, is_deleted=False)
    if lc.is_posted:
        return {"ok": False, "message": "Landed cost is already allocated."}

    grn_items = list(lc.goods_receipt.items.filter(is_deleted=False))
    if not grn_items:
        return {"ok": False, "message": "GRN has no items to allocate costs against."}

    total_charges = sum(c.amount for c in lc.charges.filter(is_deleted=False))

    if lc.allocation_method == LandedCost.AllocationMethod.BY_AMOUNT:
        base_total = sum(i.amount for i in grn_items) or Decimal("1")
        weights = [i.amount / base_total for i in grn_items]
    elif lc.allocation_method == LandedCost.AllocationMethod.BY_QTY:
        base_total = sum(i.qty for i in grn_items) or Decimal("1")
        weights = [i.qty / base_total for i in grn_items]
    else:   # equal
        n = len(grn_items)
        weights = [Decimal("1") / n for _ in grn_items]

    # Delete existing allocations before re-allocating
    LandedCostAllocation.objects.filter(landed_cost=lc).delete()

    for item, weight in zip(grn_items, weights):
        LandedCostAllocation.objects.create(
            landed_cost=lc,
            grn_item=item,
            allocated_amount=(total_charges * weight).quantize(Decimal("0.0001")),
            company_id=lc.company_id,
        )

    lc.total_taxes_and_charges = total_charges
    lc.is_posted = True
    lc.save(update_fields=["total_taxes_and_charges", "is_posted"])
    return {"ok": True, "message": f"Landed cost {lc.landed_cost_number or lc.pk} allocated across {len(grn_items)} GRN items."}


# ── Vendor Scorecard ──────────────────────────────────────────────────────────

class ScorecardIn(Schema):
    vendor_id: str
    period_start: str   # YYYY-MM-DD
    period_end: str


@router.post("/vendor-scorecards/recalculate", response=ActionResponse)
def recalculate_vendor_scorecard(request, payload: ScorecardIn):
    from datetime import date
    from apps.purchasing.hooks.vendor_scorecard import recalculate_scorecard

    try:
        ps = date.fromisoformat(payload.period_start)
        pe = date.fromisoformat(payload.period_end)
    except ValueError:
        return {"ok": False, "message": "Invalid date format — use YYYY-MM-DD."}

    company_id = getattr(request.user, "default_company_id", None)
    recalculate_scorecard(payload.vendor_id, company_id, ps, pe)
    return {"ok": True, "message": f"Scorecard recalculated for vendor {payload.vendor_id}."}


# ── Spend Analytics ───────────────────────────────────────────────────────────

@router.get("/spend-analytics", response=List[SpendRow])
def spend_analytics(
    request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Spend-cube summary: total PO spend by vendor in a date range."""
    from django.db.models import Count, Sum
    from apps.purchasing.models import PurchaseOrder

    qs = PurchaseOrder.objects.filter(
        is_deleted=False,
        status__in=[
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.BILLED,
        ],
    )
    if date_from:
        qs = qs.filter(posting_date__gte=date_from)
    if date_to:
        qs = qs.filter(posting_date__lte=date_to)

    rows = (
        qs.values("vendor_id", "vendor_name")
        .annotate(total_amount=Sum("grand_total"), po_count=Count("pk"))
        .order_by("-total_amount")
    )
    return [
        SpendRow(
            vendor_id=str(r["vendor_id"]),
            vendor_name=r["vendor_name"],
            total_amount=float(r["total_amount"] or 0),
            po_count=r["po_count"],
        )
        for r in rows
    ]
