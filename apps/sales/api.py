"""Sales action endpoints — full §6.8 implementation."""
from __future__ import annotations

import uuid
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

router = Router(tags=["Sales Actions"])


# ── Shared schemas ────────────────────────────────────────────────────────────

class ActionResponse(Schema):
    ok: bool
    message: str


class ConvertOut(Schema):
    ok: bool
    message: str
    order_id: Optional[str] = None
    so_number: Optional[str] = None


class CreditCheckOut(Schema):
    customer_name: str
    credit_limit: float
    outstanding_amount: float
    this_order_total: float
    available_credit: float
    exceeds_limit: bool


class CommissionRow(Schema):
    rep_name: str
    so_number: str
    base_amount: float
    rate_pct: float
    commission_amount: float
    status: str


class BillSubscriptionOut(Schema):
    ok: bool
    message: str
    so_id: Optional[str] = None
    so_number: Optional[str] = None


class RevenueRow(Schema):
    customer_name: str
    so_count: int
    total_revenue: float
    delivered_count: int


# ── Quotation ─────────────────────────────────────────────────────────────────

@router.post("/quotations/{qt_id}/send", response=ActionResponse)
def send_quotation(request, qt_id: uuid.UUID):
    from apps.sales.models import Quotation
    from core.numbering.service import get_next_number

    qt = get_object_or_404(Quotation, id=qt_id, is_deleted=False)
    if qt.status != Quotation.Status.DRAFT:
        return {"ok": False, "message": "Quotation is already {}.".format(qt.status)}

    if not qt.quotation_number:
        qt.quotation_number = get_next_number("QT", qt.company_id)

    qt.status = Quotation.Status.SENT
    qt.save(update_fields=["status", "quotation_number"])
    return {"ok": True, "message": "Quotation {} sent to {}.".format(qt.quotation_number, qt.customer.customer_name)}


@router.post("/quotations/{qt_id}/convert", response=ConvertOut)
def convert_quotation(request, qt_id: uuid.UUID):
    """Convert a quotation to a Sales Order, copying all line items."""
    from decimal import Decimal
    from apps.sales.models import Quotation, SalesOrder, SalesOrderItem
    from core.numbering.service import get_next_number

    qt = get_object_or_404(Quotation, id=qt_id, is_deleted=False)
    if qt.status == Quotation.Status.CONVERTED:
        return {"ok": False, "message": "Quotation already converted."}
    if qt.status not in (Quotation.Status.DRAFT, Quotation.Status.SENT, Quotation.Status.ACCEPTED):
        return {"ok": False, "message": "Cannot convert quotation with status {}.".format(qt.status)}

    so = SalesOrder.objects.create(
        customer=qt.customer,
        so_number=get_next_number("SO", qt.company_id),
        quotation=qt,
        posting_date=timezone.now().date(),
        delivery_date=qt.valid_till,
        currency=qt.currency,
        exchange_rate=qt.exchange_rate,
        discount_amount=qt.discount_amount,
        net_total=qt.net_total,
        tax_total=qt.tax_total,
        grand_total=qt.grand_total,
        status=SalesOrder.Status.DRAFT,
        opportunity_id=qt.opportunity_id,
        price_list_id=qt.price_list_id,
        terms=qt.terms,
        notes=qt.notes,
        company_id=qt.company_id,
    )

    for qi in qt.items.filter(is_deleted=False):
        SalesOrderItem.objects.create(
            order=so,
            item=qi.item,
            description=qi.description,
            qty=qi.qty,
            rate=qi.rate,
            discount_pct=qi.discount_pct,
            amount=qi.amount,
            company_id=qt.company_id,
        )

    qt.status = Quotation.Status.CONVERTED
    qt.save(update_fields=["status"])
    return {"ok": True, "message": "Quotation converted to {}.".format(so.so_number), "order_id": str(so.pk), "so_number": so.so_number}


# ── Sales Order ───────────────────────────────────────────────────────────────

@router.post("/orders/{so_id}/submit", response=ActionResponse)
def submit_sales_order(request, so_id: uuid.UUID):
    from apps.sales.models import SalesOrder
    from apps.sales.hooks.sales_order import before_submit_so
    from core.numbering.service import get_next_number

    so = get_object_or_404(SalesOrder, id=so_id, is_deleted=False)
    if so.status != SalesOrder.Status.DRAFT:
        return {"ok": False, "message": "Order is already {}.".format(so.status)}

    if not so.items.filter(is_deleted=False).exists():
        return {"ok": False, "message": "Sales order has no line items."}

    if not so.so_number:
        so.so_number = get_next_number("SO", so.company_id)

    before_submit_so(so)

    so.status = SalesOrder.Status.SUBMITTED
    so.save(update_fields=["status", "so_number"])

    msg = "Sales Order {} submitted.".format(so.so_number)
    if so.credit_limit_exceeded:
        msg += " Warning: customer credit limit exceeded."
    return {"ok": True, "message": msg}


@router.post("/orders/{so_id}/cancel", response=ActionResponse)
def cancel_sales_order(request, so_id: uuid.UUID):
    from apps.sales.models import DeliveryNote, SalesOrder

    so = get_object_or_404(SalesOrder, id=so_id, is_deleted=False)
    if so.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.SUBMITTED):
        return {"ok": False, "message": "Cannot cancel order with status {}.".format(so.status)}

    if DeliveryNote.objects.filter(sales_order=so, status=DeliveryNote.Status.SUBMITTED).exists():
        return {"ok": False, "message": "Cannot cancel: submitted delivery notes exist."}

    so.status = SalesOrder.Status.CANCELLED
    so.save(update_fields=["status"])
    return {"ok": True, "message": "Sales Order {} cancelled.".format(so.so_number)}


@router.get("/orders/{so_id}/credit-check", response=CreditCheckOut)
def check_credit(request, so_id: uuid.UUID):
    """Return credit-limit vs. outstanding + this order total for the customer."""
    from decimal import Decimal
    from django.db.models import Sum
    from apps.accounting.models import SalesInvoice
    from apps.sales.models import SalesOrder

    so = get_object_or_404(SalesOrder, id=so_id, is_deleted=False)
    customer = so.customer
    limit = customer.credit_limit or Decimal("0")

    outstanding = (
        SalesInvoice.objects.filter(
            customer=customer,
            company_id=so.company_id,
            is_deleted=False,
        )
        .exclude(status="cancelled")
        .aggregate(total=Sum("outstanding_amount"))
    )["total"] or Decimal("0")

    available = max(Decimal("0"), limit - outstanding) if limit > 0 else Decimal("0")
    exceeds = limit > 0 and (outstanding + so.grand_total) > limit

    return CreditCheckOut(
        customer_name=customer.customer_name,
        credit_limit=float(limit),
        outstanding_amount=float(outstanding),
        this_order_total=float(so.grand_total),
        available_credit=float(available),
        exceeds_limit=exceeds,
    )


# ── Delivery Note ─────────────────────────────────────────────────────────────

@router.post("/delivery-notes/{dn_id}/submit", response=ActionResponse)
def submit_delivery_note(request, dn_id: uuid.UUID):
    from apps.sales.models import DeliveryNote, SalesOrder
    from apps.sales.hooks.delivery_note import submit_delivery
    from apps.sales.hooks.sales_order import calculate_commission
    from core.numbering.service import get_next_number

    dn = get_object_or_404(DeliveryNote, id=dn_id, is_deleted=False)
    if dn.status != DeliveryNote.Status.DRAFT:
        return {"ok": False, "message": "Delivery note is already {}.".format(dn.status)}

    if not dn.items.filter(is_deleted=False).exists():
        return {"ok": False, "message": "Delivery note has no line items."}

    if not dn.dn_number:
        dn.dn_number = get_next_number("DN", dn.company_id)
        dn.save(update_fields=["dn_number"])

    submit_delivery(dn)

    dn.status = DeliveryNote.Status.SUBMITTED
    dn.save(update_fields=["status"])

    # Calculate commission when SO reaches Delivered status
    if dn.sales_order_id:
        try:
            so = SalesOrder.objects.get(pk=dn.sales_order_id)
            if so.status == SalesOrder.Status.DELIVERED:
                calculate_commission(so)
        except SalesOrder.DoesNotExist:
            pass

    return {"ok": True, "message": "Delivery note {} submitted; stock reduced.".format(dn.dn_number)}


@router.post("/delivery-notes/{dn_id}/cancel", response=ActionResponse)
def cancel_delivery_note(request, dn_id: uuid.UUID):
    from apps.sales.models import DeliveryNote
    from apps.sales.hooks.delivery_note import cancel_delivery

    dn = get_object_or_404(DeliveryNote, id=dn_id, is_deleted=False)
    if dn.status != DeliveryNote.Status.SUBMITTED:
        return {"ok": False, "message": "Delivery note is {}, cannot cancel.".format(dn.status)}

    cancel_delivery(dn)
    dn.status = DeliveryNote.Status.CANCELLED
    dn.save(update_fields=["status"])
    return {"ok": True, "message": "Delivery note {} cancelled; stock restored.".format(dn.dn_number)}


# ── Sales Return (RMA) ────────────────────────────────────────────────────────

@router.post("/sales-returns/{srn_id}/submit", response=ActionResponse)
def submit_sales_return(request, srn_id: uuid.UUID):
    """Submit RMA — creates an inbound StockEntry to bring returned goods back in."""
    from decimal import Decimal
    from apps.sales.models import SalesReturn
    from apps.warehouse.models import StockEntry, StockEntryDetail
    from apps.warehouse.hooks.stock_entry import post_stock_ledger
    from core.numbering.service import get_next_number

    srn = get_object_or_404(SalesReturn, id=srn_id, is_deleted=False)
    if srn.status != SalesReturn.Status.DRAFT:
        return {"ok": False, "message": "Return is already {}.".format(srn.status)}

    if not srn.return_number:
        srn.return_number = get_next_number("SRN", srn.company_id)
        srn.save(update_fields=["return_number"])

    se = StockEntry.objects.create(
        entry_type=StockEntry.EntryType.RECEIPT,
        posting_date=srn.posting_date,
        status=StockEntry.Status.SUBMITTED,
        voucher_type="SalesReturn",
        voucher_no=srn.return_number,
        remarks="RMA: {}".format(srn.return_number),
        company_id=srn.company_id,
    )

    net = Decimal("0")
    for line in srn.items.select_related("item", "warehouse").filter(is_deleted=False):
        StockEntryDetail.objects.create(
            stock_entry=se,
            item=line.item,
            qty=line.qty,
            basic_rate=line.rate,
            amount=line.amount,
            company_id=srn.company_id,
        )
        if se.to_warehouse is None:
            se.to_warehouse = line.warehouse
        net += line.amount

    se.total_value = net
    se.save(update_fields=["to_warehouse", "total_value"])
    post_stock_ledger(se)

    srn.net_total = net
    srn.status = SalesReturn.Status.SUBMITTED
    srn.save(update_fields=["net_total", "status"])
    return {"ok": True, "message": "Sales return {} submitted; stock restored.".format(srn.return_number)}


# ── Commission ────────────────────────────────────────────────────────────────

@router.get("/commission-entries", response=List[CommissionRow])
def list_commission_entries(
    request,
    rep_id: Optional[str] = None,
    status: Optional[str] = None,
):
    from apps.sales.models import CommissionEntry

    qs = CommissionEntry.objects.filter(is_deleted=False).select_related("sales_order")
    if rep_id:
        qs = qs.filter(rep_id=rep_id)
    if status:
        qs = qs.filter(status=status)

    return [
        CommissionRow(
            rep_name=e.rep_name,
            so_number=e.sales_order.so_number or str(e.sales_order_id),
            base_amount=float(e.base_amount),
            rate_pct=float(e.rate_pct),
            commission_amount=float(e.commission_amount),
            status=e.status,
        )
        for e in qs.order_by("-created_at")
    ]


@router.post("/commission-entries/{entry_id}/approve", response=ActionResponse)
def approve_commission(request, entry_id: uuid.UUID):
    from apps.sales.models import CommissionEntry

    entry = get_object_or_404(CommissionEntry, id=entry_id, is_deleted=False)
    if entry.status != CommissionEntry.Status.PENDING:
        return {"ok": False, "message": "Commission entry is {}.".format(entry.status)}
    entry.status = CommissionEntry.Status.APPROVED
    entry.save(update_fields=["status"])
    return {"ok": True, "message": "Commission for {} approved.".format(entry.rep_name)}


# ── Subscription ──────────────────────────────────────────────────────────────

@router.post("/subscriptions/{sub_id}/bill", response=BillSubscriptionOut)
def bill_subscription(request, sub_id: uuid.UUID):
    """Manually trigger a billing run for a subscription contract."""
    from datetime import timedelta
    from decimal import Decimal
    from apps.sales.models import (
        SalesOrder, SalesOrderItem,
        SubscriptionBillingRun, SubscriptionContract,
    )
    from core.numbering.service import get_next_number

    sub = get_object_or_404(SubscriptionContract, id=sub_id, is_deleted=False)
    if sub.status != SubscriptionContract.Status.ACTIVE:
        return {"ok": False, "message": "Subscription is {}.".format(sub.status)}

    today = timezone.now().date()
    period_start = sub.next_billing_date or sub.start_date

    if sub.frequency == SubscriptionContract.Frequency.MONTHLY:
        # Advance one month
        m = period_start.month
        y = period_start.year
        if m == 12:
            next_month_first = period_start.replace(year=y + 1, month=1, day=1)
        else:
            next_month_first = period_start.replace(month=m + 1, day=1)
        period_end = next_month_first - timedelta(days=1)
        next_date = next_month_first
    elif sub.frequency == SubscriptionContract.Frequency.QUARTERLY:
        period_end = period_start + timedelta(days=91)
        next_date = period_end + timedelta(days=1)
    elif sub.frequency == SubscriptionContract.Frequency.ANNUAL:
        period_end = period_start.replace(year=period_start.year + 1) - timedelta(days=1)
        next_date = period_end + timedelta(days=1)
    else:  # weekly
        period_end = period_start + timedelta(days=6)
        next_date = period_end + timedelta(days=1)

    if SubscriptionBillingRun.objects.filter(contract=sub, billing_date=today).exists():
        return {"ok": False, "message": "Already billed today for this subscription."}

    so = SalesOrder.objects.create(
        customer=sub.customer,
        so_number=get_next_number("SO", sub.company_id),
        posting_date=today,
        currency=sub.currency,
        status=SalesOrder.Status.DRAFT,
        notes="Subscription billing: {} ({} to {})".format(
            sub.contract_number, period_start, period_end
        ),
        price_list_id=sub.price_list_id,
        company_id=sub.company_id,
    )

    net = Decimal("0")
    for si in sub.items.filter(is_deleted=False):
        SalesOrderItem.objects.create(
            order=so,
            item=si.item,
            description="{} ({} to {})".format(si.description or si.item.item_name, period_start, period_end),
            qty=si.qty,
            rate=si.rate,
            amount=si.amount,
            company_id=sub.company_id,
        )
        net += si.amount

    so.net_total = net
    so.grand_total = net
    so.save(update_fields=["net_total", "grand_total"])

    SubscriptionBillingRun.objects.create(
        contract=sub,
        billing_date=today,
        period_start=period_start,
        period_end=period_end,
        sales_order_id=so.pk,
        status="generated",
        company_id=sub.company_id,
    )

    sub.next_billing_date = next_date
    if sub.end_date and next_date > sub.end_date:
        sub.status = SubscriptionContract.Status.EXPIRED
    sub.save(update_fields=["next_billing_date", "status"])

    return {
        "ok": True,
        "message": "Subscription billed — {} created.".format(so.so_number),
        "so_id": str(so.pk),
        "so_number": so.so_number,
    }


# ── Revenue analytics ─────────────────────────────────────────────────────────

@router.get("/revenue-summary", response=List[RevenueRow])
def revenue_summary(
    request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Summarise revenue by customer for a date range."""
    from django.db.models import Count, Q, Sum
    from apps.sales.models import SalesOrder

    qs = SalesOrder.objects.filter(
        is_deleted=False,
        status__in=[
            SalesOrder.Status.SUBMITTED,
            SalesOrder.Status.PROCESSING,
            SalesOrder.Status.PARTIALLY_DELIVERED,
            SalesOrder.Status.DELIVERED,
            SalesOrder.Status.BILLED,
        ],
    )
    if date_from:
        qs = qs.filter(posting_date__gte=date_from)
    if date_to:
        qs = qs.filter(posting_date__lte=date_to)

    rows = (
        qs.values("customer__customer_name")
        .annotate(
            so_count=Count("pk"),
            total_revenue=Sum("grand_total"),
            delivered_count=Count("pk", filter=Q(status__in=["delivered", "billed"])),
        )
        .order_by("-total_revenue")
    )

    return [
        RevenueRow(
            customer_name=r["customer__customer_name"],
            so_count=r["so_count"],
            total_revenue=float(r["total_revenue"] or 0),
            delivered_count=r["delivered_count"],
        )
        for r in rows
    ]
