"""
Seed command: populate the Sales module with realistic demo data.

Covers: Price Lists (with tiered pricing), Promotion Rules, Quotations
(draft/sent/accepted/converted/declined), Sales Orders across all statuses,
Delivery Notes (submitted → stock out), Commission Structures & Entries,
Subscription Contracts (monthly SaaS-style), and one Sales Return (RMA).

Run:  python manage.py seed_sales
Re-runnable: all creates use get_or_create guards.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


def _d(days: int) -> date:
    return date.today() + timedelta(days=days)


class Command(BaseCommand):
    help = "Seed realistic Sales demo data."

    def handle(self, *args, **options):
        self.stdout.write("=== Sales seed ===")

        from apps.accounting.models import Customer
        from apps.warehouse.models import Item, Warehouse

        customers = list(Customer.objects.filter(is_active=True).order_by("customer_name")[:8])
        items = list(Item.objects.filter(is_sales_item=True, is_active=True).order_by("item_code")[:10])
        stores_wh = Warehouse.objects.filter(
            warehouse_type=Warehouse.WarehouseType.STORES, is_active=True
        ).first()

        if not customers:
            self.stdout.write(self.style.ERROR("No customers — run seed_accounting first."))
            return
        if not items:
            self.stdout.write(self.style.ERROR("No items — run seed_warehouse first."))
            return
        if not stores_wh:
            self.stdout.write(self.style.ERROR("No warehouse — run seed_warehouse first."))
            return

        company_id = customers[0].company_id

        while len(customers) < 5:
            customers = customers + customers
        while len(items) < 8:
            items = items + items

        price_lists = self._seed_price_lists(items, company_id)
        self._seed_promotion_rules(items, customers, company_id)
        commission_structure = self._seed_commission_structures(company_id)
        quotations = self._seed_quotations(customers, items, price_lists, company_id)
        sos = self._seed_sales_orders(customers, items, stores_wh, price_lists, company_id)
        self._seed_delivery_notes(sos, items, stores_wh, company_id)
        self._seed_commissions(sos, commission_structure, company_id)
        self._seed_subscriptions(customers, items, price_lists, company_id)
        self._seed_sales_return(company_id)

        self.stdout.write(self.style.SUCCESS("Sales seed complete."))

    # ── Price Lists ───────────────────────────────────────────────────────────

    def _seed_price_lists(self, items, company_id):
        from apps.product_catalogue.models import PriceList

        specs = [
            {"name": "Standard Retail", "currency": "USD"},
            {"name": "Wholesale / Volume", "currency": "USD"},
            {"name": "VIP Customer", "currency": "USD"},
        ]
        result = []
        for spec in specs:
            pl, created = PriceList.objects.get_or_create(
                name=spec["name"],
                company_id=company_id,
                defaults={"currency": spec["currency"], "is_selling": True, "is_active": True},
            )
            if created:
                self.stdout.write("  Created PriceList: {}".format(pl.name))
            result.append(pl)

        # ProductPrice rows (product_catalogue.ProductPrice) are seeded by seed_product_catalogue,
        # which runs after seed_sales and has access to both Product and PriceList records.

        return result

    # ── Promotion Rules ───────────────────────────────────────────────────────

    def _seed_promotion_rules(self, items, customers, company_id):
        from apps.sales.models import PromotionRule

        rules = [
            {
                "name": "Summer Sale 10% Off",
                "discount_type": PromotionRule.DiscountType.PERCENTAGE,
                "discount_value": Decimal("10.00"),
                "min_order_amount": Decimal("500.00"),
                "valid_from": _d(-30),
                "valid_to": _d(60),
                "priority": 5,
            },
            {
                "name": "New Customer Welcome 5%",
                "discount_type": PromotionRule.DiscountType.PERCENTAGE,
                "discount_value": Decimal("5.00"),
                "min_order_amount": Decimal("0"),
                "priority": 10,
            },
            {
                "name": "Bulk Order Fixed Discount",
                "discount_type": PromotionRule.DiscountType.FIXED_AMOUNT,
                "discount_value": Decimal("200.00"),
                "min_order_amount": Decimal("2000.00"),
                "priority": 3,
                "approval_required_above": Decimal("15.00"),
            },
        ]
        for spec in rules:
            obj, created = PromotionRule.objects.get_or_create(
                name=spec["name"],
                company_id=company_id,
                defaults={**spec, "company_id": company_id},
            )
            if created:
                self.stdout.write("  Created PromotionRule: {}".format(obj.name))

    # ── Commission Structures ─────────────────────────────────────────────────

    def _seed_commission_structures(self, company_id):
        from apps.sales.models import CommissionRate, CommissionStructure

        struct, created = CommissionStructure.objects.get_or_create(
            name="Standard Sales Commission",
            company_id=company_id,
            defaults={
                "basis": CommissionStructure.BasisType.REVENUE,
                "is_active": True,
                "notes": "Tiered: 3% base, 5% on orders over $5k, 7% on orders over $15k.",
            },
        )
        if created:
            CommissionRate.objects.get_or_create(
                structure=struct, min_amount=Decimal("0"),
                defaults={"rate_pct": Decimal("3.0000"), "company_id": company_id},
            )
            CommissionRate.objects.get_or_create(
                structure=struct, min_amount=Decimal("5000"),
                defaults={"rate_pct": Decimal("5.0000"), "company_id": company_id},
            )
            CommissionRate.objects.get_or_create(
                structure=struct, min_amount=Decimal("15000"),
                defaults={"rate_pct": Decimal("7.0000"), "company_id": company_id},
            )
            self.stdout.write("  Created CommissionStructure: {} (3 tiers)".format(struct.name))

        return struct

    # ── Quotations ────────────────────────────────────────────────────────────

    def _seed_quotations(self, customers, items, price_lists, company_id):
        from apps.sales.models import Quotation, QuotationItem

        qt_specs = [
            # Converted → spawns SO
            {
                "number": "QT-00001",
                "customer": customers[0],
                "posting_date": _d(-40),
                "valid_till": _d(-10),
                "status": Quotation.Status.CONVERTED,
                "pl": price_lists[0],
                "items": [(items[0], 20, Decimal("0")), (items[1], 15, Decimal("5"))],
            },
            # Accepted
            {
                "number": "QT-00002",
                "customer": customers[1],
                "posting_date": _d(-20),
                "valid_till": _d(10),
                "status": Quotation.Status.ACCEPTED,
                "pl": price_lists[1],
                "items": [(items[2], 50, Decimal("0")), (items[3], 30, Decimal("10"))],
            },
            # Sent — awaiting response
            {
                "number": "QT-00003",
                "customer": customers[2],
                "posting_date": _d(-7),
                "valid_till": _d(21),
                "status": Quotation.Status.SENT,
                "pl": price_lists[2],
                "items": [(items[4], 100, Decimal("0")), (items[5], 80, Decimal("8"))],
            },
            # Declined
            {
                "number": "QT-00004",
                "customer": customers[3],
                "posting_date": _d(-60),
                "valid_till": _d(-30),
                "status": Quotation.Status.DECLINED,
                "pl": price_lists[0],
                "items": [(items[0], 5, Decimal("0"))],
            },
            # Draft
            {
                "number": "QT-00005",
                "customer": customers[4],
                "posting_date": _d(-2),
                "valid_till": _d(28),
                "status": Quotation.Status.DRAFT,
                "pl": price_lists[0],
                "items": [(items[6], 10, Decimal("0")), (items[7], 25, Decimal("0"))],
            },
        ]

        result = []
        for spec in qt_specs:
            qt, created = Quotation.objects.get_or_create(
                quotation_number=spec["number"],
                defaults={
                    "customer": spec["customer"],
                    "posting_date": spec["posting_date"],
                    "valid_till": spec["valid_till"],
                    "status": spec["status"],
                    "price_list_id": spec["pl"].id,
                    "company_id": company_id,
                },
            )
            if created:
                net = Decimal("0")
                for item, qty, disc in spec["items"]:
                    base = item.standard_selling_price or Decimal("50.00")
                    rate = base * (1 - disc / 100)
                    amount = Decimal(str(qty)) * rate
                    QuotationItem.objects.create(
                        quotation=qt,
                        item=item,
                        qty=Decimal(str(qty)),
                        rate=rate.quantize(Decimal("0.01")),
                        discount_pct=disc,
                        amount=amount.quantize(Decimal("0.01")),
                        company_id=company_id,
                    )
                    net += amount
                qt.net_total = net.quantize(Decimal("0.01"))
                qt.grand_total = net.quantize(Decimal("0.01"))
                qt.save(update_fields=["net_total", "grand_total"])
                self.stdout.write("  Created Quotation: {} [{}]".format(qt.quotation_number, qt.status))
            result.append(qt)

        return result

    # ── Sales Orders ──────────────────────────────────────────────────────────

    def _seed_sales_orders(self, customers, items, stores_wh, price_lists, company_id):
        from apps.sales.models import SalesOrder, SalesOrderItem

        so_specs = [
            # SO-00001: delivered + billed (oldest)
            {
                "number": "SO-00001",
                "customer": customers[0],
                "posting_date": _d(-60),
                "delivery_date": _d(-45),
                "status": SalesOrder.Status.BILLED,
                "grand_total": Decimal("3480.00"),
                "items": [(items[0], 40, Decimal("52.00"), Decimal("0"))],
            },
            # SO-00002: delivered
            {
                "number": "SO-00002",
                "customer": customers[1],
                "posting_date": _d(-30),
                "delivery_date": _d(-15),
                "status": SalesOrder.Status.DELIVERED,
                "grand_total": Decimal("5625.00"),
                "items": [
                    (items[1], 50, Decimal("45.00"), Decimal("5")),
                    (items[2], 30, Decimal("80.00"), Decimal("0")),
                ],
            },
            # SO-00003: partially delivered
            {
                "number": "SO-00003",
                "customer": customers[2],
                "posting_date": _d(-20),
                "delivery_date": _d(-5),
                "status": SalesOrder.Status.PARTIALLY_DELIVERED,
                "grand_total": Decimal("8400.00"),
                "items": [
                    (items[3], 80, Decimal("60.00"), Decimal("0")),
                    (items[4], 60, Decimal("75.00"), Decimal("0")),
                ],
            },
            # SO-00004: submitted / processing
            {
                "number": "SO-00004",
                "customer": customers[3],
                "posting_date": _d(-10),
                "delivery_date": _d(10),
                "status": SalesOrder.Status.SUBMITTED,
                "grand_total": Decimal("2250.00"),
                "items": [(items[5], 30, Decimal("75.00"), Decimal("0"))],
            },
            # SO-00005: submitted (high value — credit check flag)
            {
                "number": "SO-00005",
                "customer": customers[0],
                "posting_date": _d(-5),
                "delivery_date": _d(20),
                "status": SalesOrder.Status.SUBMITTED,
                "grand_total": Decimal("18750.00"),
                "credit_limit_exceeded": True,
                "items": [
                    (items[6], 150, Decimal("75.00"), Decimal("0")),
                    (items[7], 100, Decimal("60.00"), Decimal("0")),
                ],
            },
            # SO-00006: draft
            {
                "number": "SO-00006",
                "customer": customers[4],
                "posting_date": _d(-1),
                "delivery_date": _d(30),
                "status": SalesOrder.Status.DRAFT,
                "grand_total": Decimal("1200.00"),
                "items": [(items[0], 20, Decimal("60.00"), Decimal("0"))],
            },
            # SO-00007: cancelled
            {
                "number": "SO-00007",
                "customer": customers[1],
                "posting_date": _d(-50),
                "delivery_date": _d(-35),
                "status": SalesOrder.Status.CANCELLED,
                "grand_total": Decimal("975.00"),
                "items": [(items[2], 15, Decimal("65.00"), Decimal("0"))],
            },
        ]

        result = []
        for spec in so_specs:
            customer = spec["customer"]
            so, created = SalesOrder.objects.get_or_create(
                so_number=spec["number"],
                defaults={
                    "customer": customer,
                    "posting_date": spec["posting_date"],
                    "delivery_date": spec.get("delivery_date"),
                    "currency": customer.default_currency or "USD",
                    "status": spec["status"],
                    "credit_limit_exceeded": spec.get("credit_limit_exceeded", False),
                    "net_total": spec["grand_total"],
                    "grand_total": spec["grand_total"],
                    "company_id": company_id,
                },
            )
            if created:
                for item, qty, rate, disc in spec["items"]:
                    amount = Decimal(str(qty)) * rate * (1 - disc / 100)
                    soi = SalesOrderItem.objects.create(
                        order=so,
                        item=item,
                        qty=Decimal(str(qty)),
                        rate=rate,
                        discount_pct=disc,
                        amount=amount.quantize(Decimal("0.01")),
                        warehouse=stores_wh,
                        company_id=company_id,
                    )
                    # Mark delivered qty for finished orders
                    if spec["status"] in (SalesOrder.Status.DELIVERED, SalesOrder.Status.BILLED):
                        soi.delivered_qty = soi.qty
                        soi.billed_qty = soi.qty if spec["status"] == SalesOrder.Status.BILLED else Decimal("0")
                        soi.save(update_fields=["delivered_qty", "billed_qty"])
                    elif spec["status"] == SalesOrder.Status.PARTIALLY_DELIVERED:
                        soi.delivered_qty = (soi.qty / 2).quantize(Decimal("0.0001"))
                        soi.save(update_fields=["delivered_qty"])

                self.stdout.write("  Created SO: {} [{}] — {} / ${:,.2f}".format(
                    so.so_number, so.status, customer.customer_name, so.grand_total
                ))
            result.append(so)

        return result

    # ── Delivery Notes ────────────────────────────────────────────────────────

    def _seed_delivery_notes(self, sos, items, stores_wh, company_id):
        from apps.sales.models import DeliveryNote, DeliveryNoteItem, SalesOrder
        from apps.sales.hooks.delivery_note import submit_delivery

        # DN for SO-00001 (billed) — full delivery, submitted
        so1 = next((s for s in sos if s.so_number == "SO-00001"), None)
        if so1:
            dn1, c1 = DeliveryNote.objects.get_or_create(
                dn_number="DN-00001",
                defaults={
                    "sales_order": so1,
                    "customer": so1.customer,
                    "posting_date": _d(-44),
                    "status": DeliveryNote.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c1:
                for soi in so1.items.all():
                    DeliveryNoteItem.objects.create(
                        delivery_note=dn1,
                        so_item=soi,
                        item=soi.item,
                        qty=soi.qty,
                        rate=soi.rate,
                        amount=soi.amount,
                        warehouse=stores_wh,
                        company_id=company_id,
                    )
                submit_delivery(dn1)
                self.stdout.write("  Created + submitted DN: {} (full delivery for {})".format(
                    dn1.dn_number, so1.so_number
                ))

        # DN for SO-00002 (delivered) — full delivery
        so2 = next((s for s in sos if s.so_number == "SO-00002"), None)
        if so2:
            dn2, c2 = DeliveryNote.objects.get_or_create(
                dn_number="DN-00002",
                defaults={
                    "sales_order": so2,
                    "customer": so2.customer,
                    "posting_date": _d(-14),
                    "status": DeliveryNote.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c2:
                for soi in so2.items.all():
                    DeliveryNoteItem.objects.create(
                        delivery_note=dn2,
                        so_item=soi,
                        item=soi.item,
                        qty=soi.qty,
                        rate=soi.rate,
                        amount=soi.amount,
                        warehouse=stores_wh,
                        company_id=company_id,
                    )
                submit_delivery(dn2)
                self.stdout.write("  Created + submitted DN: {} (full delivery for {})".format(
                    dn2.dn_number, so2.so_number
                ))

        # DN for SO-00003 (partially delivered) — 50% shipped
        so3 = next((s for s in sos if s.so_number == "SO-00003"), None)
        if so3:
            dn3, c3 = DeliveryNote.objects.get_or_create(
                dn_number="DN-00003",
                defaults={
                    "sales_order": so3,
                    "customer": so3.customer,
                    "posting_date": _d(-4),
                    "status": DeliveryNote.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c3:
                for soi in so3.items.all():
                    partial = (soi.qty / 2).quantize(Decimal("0.0001"))
                    DeliveryNoteItem.objects.create(
                        delivery_note=dn3,
                        so_item=soi,
                        item=soi.item,
                        qty=partial,
                        rate=soi.rate,
                        amount=(partial * soi.rate).quantize(Decimal("0.01")),
                        warehouse=stores_wh,
                        company_id=company_id,
                    )
                submit_delivery(dn3)
                self.stdout.write("  Created + submitted DN: {} (50% delivery for {})".format(
                    dn3.dn_number, so3.so_number
                ))

        # Draft DN for SO-00004 (to be submitted later)
        so4 = next((s for s in sos if s.so_number == "SO-00004"), None)
        if so4:
            dn4, c4 = DeliveryNote.objects.get_or_create(
                dn_number="DN-00004",
                defaults={
                    "sales_order": so4,
                    "customer": so4.customer,
                    "posting_date": date.today(),
                    "status": DeliveryNote.Status.DRAFT,
                    "company_id": company_id,
                },
            )
            if c4:
                for soi in so4.items.all():
                    DeliveryNoteItem.objects.create(
                        delivery_note=dn4,
                        so_item=soi,
                        item=soi.item,
                        qty=soi.qty,
                        rate=soi.rate,
                        amount=soi.amount,
                        warehouse=stores_wh,
                        company_id=company_id,
                    )
                self.stdout.write("  Created DRAFT DN: {} (ready to ship for {})".format(
                    dn4.dn_number, so4.so_number
                ))

    # ── Commission Entries ────────────────────────────────────────────────────

    def _seed_commissions(self, sos, structure, company_id):
        import uuid as _uuid
        from apps.sales.models import CommissionEntry, SalesOrder

        # Stable placeholder UUIDs — would be HRM Employee PKs in a real deployment
        REP_ALEX = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
        REP_EFUA = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002")

        # Commission on SO-00001 (billed, $3480) → 3% = $104.40
        so1 = next((s for s in sos if s.so_number == "SO-00001"), None)
        if so1:
            CommissionEntry.objects.get_or_create(
                sales_order=so1,
                rep_id=REP_ALEX,
                defaults={
                    "rep_name": "Alex Mensah",
                    "structure": structure,
                    "base_amount": so1.grand_total,
                    "rate_pct": Decimal("3.0000"),
                    "commission_amount": (so1.grand_total * Decimal("0.03")).quantize(Decimal("0.01")),
                    "status": CommissionEntry.Status.PAID,
                    "payout_date": _d(-30),
                    "company_id": company_id,
                },
            )

        # Commission on SO-00002 (delivered, $5625) → 5% = $281.25
        so2 = next((s for s in sos if s.so_number == "SO-00002"), None)
        if so2:
            CommissionEntry.objects.get_or_create(
                sales_order=so2,
                rep_id=REP_EFUA,
                defaults={
                    "rep_name": "Efua Boateng",
                    "structure": structure,
                    "base_amount": so2.grand_total,
                    "rate_pct": Decimal("5.0000"),
                    "commission_amount": (so2.grand_total * Decimal("0.05")).quantize(Decimal("0.01")),
                    "status": CommissionEntry.Status.APPROVED,
                    "company_id": company_id,
                },
            )
            self.stdout.write("  Created CommissionEntries for SO-00001 and SO-00002")

    # ── Subscription Contracts ────────────────────────────────────────────────

    def _seed_subscriptions(self, customers, items, price_lists, company_id):
        from apps.sales.models import SubscriptionContract, SubscriptionItem

        svc_item = next((i for i in items if i.is_service_item), None)
        if not svc_item:
            svc_item = items[0]

        sub_specs = [
            {
                "number": "SUB-00001",
                "customer": customers[0],
                "frequency": SubscriptionContract.Frequency.MONTHLY,
                "start_date": _d(-90),
                "monthly_value": Decimal("1200.00"),
                "status": SubscriptionContract.Status.ACTIVE,
                "next_billing": _d(1),
                "pl": price_lists[2],
                "qty": Decimal("1"),
                "rate": Decimal("1200.00"),
            },
            {
                "number": "SUB-00002",
                "customer": customers[1],
                "frequency": SubscriptionContract.Frequency.ANNUAL,
                "start_date": _d(-180),
                "end_date": _d(185),
                "monthly_value": Decimal("9600.00"),
                "status": SubscriptionContract.Status.ACTIVE,
                "next_billing": _d(185),
                "pl": price_lists[1],
                "qty": Decimal("1"),
                "rate": Decimal("9600.00"),
            },
            {
                "number": "SUB-00003",
                "customer": customers[2],
                "frequency": SubscriptionContract.Frequency.MONTHLY,
                "start_date": _d(-200),
                "end_date": _d(-10),
                "monthly_value": Decimal("500.00"),
                "status": SubscriptionContract.Status.EXPIRED,
                "next_billing": None,
                "pl": price_lists[0],
                "qty": Decimal("1"),
                "rate": Decimal("500.00"),
            },
        ]

        for spec in sub_specs:
            sub, created = SubscriptionContract.objects.get_or_create(
                contract_number=spec["number"],
                defaults={
                    "customer": spec["customer"],
                    "start_date": spec["start_date"],
                    "end_date": spec.get("end_date"),
                    "frequency": spec["frequency"],
                    "currency": "USD",
                    "monthly_value": spec["monthly_value"],
                    "status": spec["status"],
                    "next_billing_date": spec.get("next_billing"),
                    "price_list_id": spec["pl"].id if spec.get("pl") else None,
                    "company_id": company_id,
                },
            )
            if created:
                SubscriptionItem.objects.create(
                    contract=sub,
                    item=svc_item,
                    qty=spec["qty"],
                    rate=spec["rate"],
                    amount=spec["qty"] * spec["rate"],
                    description="Monthly platform subscription",
                    company_id=company_id,
                )
                self.stdout.write("  Created Subscription: {} [{}] — {}".format(
                    sub.contract_number, sub.status, spec["customer"].customer_name
                ))

    # ── Sales Return (RMA) ────────────────────────────────────────────────────

    def _seed_sales_return(self, company_id):
        from apps.sales.models import (
            DeliveryNote, DeliveryNoteItem,
            SalesReturn, SalesReturnItem,
        )

        dn1 = DeliveryNote.objects.filter(dn_number="DN-00001", company_id=company_id).first()
        if not dn1:
            return

        dn_items = list(dn1.items.filter(is_deleted=False)[:1])
        if not dn_items:
            return

        srn, created = SalesReturn.objects.get_or_create(
            return_number="SRN-00001",
            defaults={
                "customer": dn1.customer,
                "delivery_note": dn1,
                "posting_date": _d(-40),
                "return_reason": "3 units arrived damaged. Customer requesting replacement.",
                "status": SalesReturn.Status.SUBMITTED,
                "company_id": company_id,
            },
        )
        if created:
            di = dn_items[0]
            ret_qty = Decimal("3")
            SalesReturnItem.objects.create(
                sales_return=srn,
                dn_item=di,
                item=di.item,
                qty=ret_qty,
                rate=di.rate,
                amount=(ret_qty * di.rate).quantize(Decimal("0.01")),
                warehouse=di.warehouse,
                reason="Damaged in transit",
                company_id=company_id,
            )
            srn.net_total = ret_qty * di.rate
            srn.save(update_fields=["net_total"])
            self.stdout.write("  Created SalesReturn: {} — 3 units returned from {}".format(
                srn.return_number, dn1.customer.customer_name
            ))
