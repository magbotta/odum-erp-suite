"""
Seed command: populate the Purchasing module with realistic demo data.

Covers: Supplier Qualifications, RFQs (with supplier responses), Purchase
Requisitions, Purchase Orders (Draft → Received), Goods Receipts (which post
to the StockLedger), Landed Costs, Vendor Scorecards, and one Purchase Return.

Run:  python manage.py seed_purchasing
Re-runnable: all creates are guarded by get_or_create or existence checks.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


def _d(days: int) -> date:
    """Return today offset by *days* days."""
    return date.today() + timedelta(days=days)


class Command(BaseCommand):
    help = "Seed realistic Purchasing demo data."

    def handle(self, *args, **options):
        self.stdout.write("=== Purchasing seed ===")

        from apps.accounting.models import Vendor
        from apps.warehouse.models import Item, Warehouse

        # ── Resolve existing master data ──────────────────────────────────────
        vendors = list(Vendor.objects.filter(is_active=True).order_by("vendor_name")[:8])
        items = list(Item.objects.filter(is_purchase_item=True, is_active=True).order_by("item_code")[:12])
        stores_wh = Warehouse.objects.filter(
            warehouse_type=Warehouse.WarehouseType.STORES, is_active=True
        ).first()

        if not vendors:
            self.stdout.write(self.style.ERROR("No vendors found — run seed_accounting first."))
            return
        if not items:
            self.stdout.write(self.style.ERROR("No items found — run seed_warehouse first."))
            return
        if not stores_wh:
            self.stdout.write(self.style.ERROR("No stores warehouse found — run seed_warehouse first."))
            return

        company_id = vendors[0].company_id

        # pad items if needed
        while len(items) < 6:
            items = items + items
        while len(vendors) < 4:
            vendors = vendors + vendors

        self._seed_supplier_qualifications(vendors, company_id)
        rfq1, rfq2 = self._seed_rfqs(vendors, items, company_id)
        pr1, pr2, pr3 = self._seed_requisitions(vendors, items, stores_wh, company_id)
        pos = self._seed_purchase_orders(vendors, items, stores_wh, pr1, rfq1, company_id)
        self._seed_goods_receipts(pos, items, stores_wh, company_id)
        self._seed_landed_costs(company_id)
        self._seed_vendor_scorecards(vendors, company_id)
        self._seed_purchase_return(company_id)

        self.stdout.write(self.style.SUCCESS("Purchasing seed complete."))

    # ── Supplier Qualifications ───────────────────────────────────────────────

    def _seed_supplier_qualifications(self, vendors, company_id):
        from apps.purchasing.models import SupplierQualification

        specs = [
            {
                "vendor_name": "TechSource Ghana Ltd",
                "contact_name": "Kwame Asante",
                "contact_email": "kwame@techsource.gh",
                "contact_phone": "+233244001122",
                "business_type": "IT Hardware Distributor",
                "tax_registration_no": "GH-TAX-7890123",
                "status": SupplierQualification.Status.QUALIFIED,
                "has_tax_cert": True,
                "has_insurance_cert": True,
                "has_bank_details": True,
                "esg_questionnaire_completed": True,
                "qualification_score": 100,
                "notes": "Long-standing supplier; approved Q1.",
            },
            {
                "vendor_name": "AfriSoft Solutions",
                "contact_name": "Amara Diallo",
                "contact_email": "amara@afrisoft.io",
                "contact_phone": "+221771002233",
                "business_type": "Software Vendor",
                "tax_registration_no": "SN-TAX-4456789",
                "status": SupplierQualification.Status.UNDER_REVIEW,
                "has_tax_cert": True,
                "has_insurance_cert": False,
                "has_bank_details": True,
                "esg_questionnaire_completed": False,
                "qualification_score": 50,
                "notes": "Insurance certificate pending.",
            },
            {
                "vendor_name": "PanAfrica Office Supplies",
                "contact_name": "Fatou Coulibaly",
                "contact_email": "fatou@panafrica-office.com",
                "contact_phone": "+22520003344",
                "business_type": "Office Supplies Distributor",
                "tax_registration_no": "CI-TAX-3312345",
                "status": SupplierQualification.Status.NEW,
                "has_tax_cert": False,
                "has_insurance_cert": False,
                "has_bank_details": False,
                "esg_questionnaire_completed": False,
                "qualification_score": 0,
            },
            {
                "vendor_name": "NovaBuild Materials",
                "contact_name": "Emeka Obi",
                "contact_email": "emeka@novabuild.ng",
                "contact_phone": "+2348031114455",
                "business_type": "Construction Materials",
                "tax_registration_no": "NG-TAX-9901234",
                "status": SupplierQualification.Status.ADDITIONAL_INFO,
                "has_tax_cert": True,
                "has_insurance_cert": True,
                "has_bank_details": False,
                "esg_questionnaire_completed": True,
                "qualification_score": 75,
                "notes": "Bank details not yet provided.",
            },
        ]

        for spec in specs:
            obj, created = SupplierQualification.objects.get_or_create(
                contact_email=spec["contact_email"],
                company_id=company_id,
                defaults={**spec, "company_id": company_id},
            )
            if created:
                self.stdout.write(f"  Created SupplierQualification: {obj.vendor_name}")

    # ── RFQs ─────────────────────────────────────────────────────────────────

    def _seed_rfqs(self, vendors, items, company_id):
        from apps.purchasing.models import (
            RequestForQuotation, RFQItem,
            RFQSupplierResponse, RFQSupplierResponseItem,
        )

        rfq1, c1 = RequestForQuotation.objects.get_or_create(
            rfq_number="RFQ-00001",
            defaults={
                "posting_date": _d(-30),
                "response_deadline": _d(-15),
                "status": RequestForQuotation.Status.AWARDED,
                "message_for_supplier": "Please quote your best price for the items below, inclusive of delivery to our Accra warehouse.",
                "company_id": company_id,
            },
        )
        if c1:
            it1 = RFQItem.objects.create(
                rfq=rfq1,
                item_id=items[0].pk,
                item_code=items[0].item_code,
                item_name=items[0].item_name,
                qty=Decimal("100"),
                uom="EA",
                company_id=company_id,
            )
            it2 = RFQItem.objects.create(
                rfq=rfq1,
                item_id=items[1].pk,
                item_code=items[1].item_code,
                item_name=items[1].item_name,
                qty=Decimal("50"),
                uom="EA",
                company_id=company_id,
            )
            # Two vendor responses
            resp_a, _ = RFQSupplierResponse.objects.get_or_create(
                rfq=rfq1, vendor_id=vendors[0].pk,
                defaults={
                    "vendor_name": vendors[0].vendor_name,
                    "status": RFQSupplierResponse.Status.AWARDED,
                    "response_date": _d(-18),
                    "currency": "USD",
                    "delivery_days": 7,
                    "payment_terms": "Net 30",
                    "total_amount": Decimal("3250.00"),
                    "company_id": company_id,
                },
            )
            RFQSupplierResponseItem.objects.get_or_create(
                response=resp_a, rfq_item=it1,
                defaults={"quoted_rate": Decimal("22.00"), "quoted_amount": Decimal("2200.00"), "company_id": company_id},
            )
            RFQSupplierResponseItem.objects.get_or_create(
                response=resp_a, rfq_item=it2,
                defaults={"quoted_rate": Decimal("21.00"), "quoted_amount": Decimal("1050.00"), "company_id": company_id},
            )
            resp_b, _ = RFQSupplierResponse.objects.get_or_create(
                rfq=rfq1, vendor_id=vendors[1].pk,
                defaults={
                    "vendor_name": vendors[1].vendor_name,
                    "status": RFQSupplierResponse.Status.REJECTED,
                    "response_date": _d(-17),
                    "currency": "USD",
                    "delivery_days": 14,
                    "payment_terms": "Net 45",
                    "total_amount": Decimal("3500.00"),
                    "company_id": company_id,
                },
            )
            RFQSupplierResponseItem.objects.get_or_create(
                response=resp_b, rfq_item=it1,
                defaults={"quoted_rate": Decimal("24.00"), "quoted_amount": Decimal("2400.00"), "company_id": company_id},
            )
            RFQSupplierResponseItem.objects.get_or_create(
                response=resp_b, rfq_item=it2,
                defaults={"quoted_rate": Decimal("22.00"), "quoted_amount": Decimal("1100.00"), "company_id": company_id},
            )
            self.stdout.write(f"  Created RFQ: {rfq1.rfq_number} (awarded to {vendors[0].vendor_name})")

        rfq2, c2 = RequestForQuotation.objects.get_or_create(
            rfq_number="RFQ-00002",
            defaults={
                "posting_date": _d(-7),
                "response_deadline": _d(7),
                "status": RequestForQuotation.Status.SENT,
                "message_for_supplier": "Urgent requirement — please respond within 7 days.",
                "company_id": company_id,
            },
        )
        if c2:
            RFQItem.objects.create(
                rfq=rfq2,
                item_id=items[2].pk,
                item_code=items[2].item_code,
                item_name=items[2].item_name,
                qty=Decimal("200"),
                uom="EA",
                company_id=company_id,
            )
            RFQSupplierResponse.objects.get_or_create(
                rfq=rfq2, vendor_id=vendors[2].pk,
                defaults={
                    "vendor_name": vendors[2].vendor_name,
                    "status": RFQSupplierResponse.Status.PENDING,
                    "currency": "USD",
                    "delivery_days": 0,
                    "company_id": company_id,
                },
            )
            RFQSupplierResponse.objects.get_or_create(
                rfq=rfq2, vendor_id=vendors[3].pk,
                defaults={
                    "vendor_name": vendors[3].vendor_name,
                    "status": RFQSupplierResponse.Status.RESPONDED,
                    "response_date": _d(-2),
                    "currency": "USD",
                    "delivery_days": 10,
                    "payment_terms": "50% upfront",
                    "total_amount": Decimal("4800.00"),
                    "company_id": company_id,
                },
            )
            self.stdout.write(f"  Created RFQ: {rfq2.rfq_number} (open, 2 suppliers)")

        return rfq1, rfq2

    # ── Purchase Requisitions ─────────────────────────────────────────────────

    def _seed_requisitions(self, vendors, items, stores_wh, company_id):
        from apps.purchasing.models import PurchaseRequisition, PurchaseRequisitionItem

        specs = [
            {
                "number": "PR-00001",
                "posting_date": _d(-45),
                "required_by_date": _d(-30),
                "status": PurchaseRequisition.Status.ORDERED,
                "purpose": "Q1 stock replenishment for fast-moving consumables.",
                "items": [(items[0], 100), (items[1], 50), (items[2], 75)],
            },
            {
                "number": "PR-00002",
                "posting_date": _d(-15),
                "required_by_date": _d(15),
                "status": PurchaseRequisition.Status.APPROVED,
                "purpose": "Additional raw materials for Q2 production schedule.",
                "items": [(items[3], 200), (items[4], 150)],
            },
            {
                "number": "PR-00003",
                "posting_date": _d(-3),
                "required_by_date": _d(14),
                "status": PurchaseRequisition.Status.SUBMITTED,
                "purpose": "Office supplies restock requested by Admin.",
                "items": [(items[5], 60)],
            },
        ]

        result = []
        for spec in specs:
            pr, created = PurchaseRequisition.objects.get_or_create(
                requisition_number=spec["number"],
                defaults={
                    "posting_date": spec["posting_date"],
                    "required_by_date": spec["required_by_date"],
                    "status": spec["status"],
                    "purpose": spec["purpose"],
                    "company_id": company_id,
                },
            )
            if created:
                for item, qty in spec["items"]:
                    rate = item.standard_buying_price or Decimal("10.00")
                    PurchaseRequisitionItem.objects.create(
                        requisition=pr,
                        item_id=item.pk,
                        item_code=item.item_code,
                        item_name=item.item_name,
                        qty=Decimal(str(qty)),
                        uom="EA",
                        estimated_rate=rate,
                        estimated_amount=Decimal(str(qty)) * rate,
                        warehouse_id=stores_wh.pk,
                        company_id=company_id,
                    )
                self.stdout.write(f"  Created Requisition: {pr.requisition_number} [{pr.status}]")
            result.append(pr)

        return result[0], result[1], result[2]

    # ── Purchase Orders ───────────────────────────────────────────────────────

    def _seed_purchase_orders(self, vendors, items, stores_wh, pr1, rfq1, company_id):
        from apps.purchasing.models import PurchaseOrder, PurchaseOrderItem

        po_specs = [
            # PO-00001: fully received (from RFQ)
            {
                "number": "PO-00001",
                "vendor": vendors[0],
                "posting_date": _d(-28),
                "expected_delivery": _d(-14),
                "status": PurchaseOrder.Status.RECEIVED,
                "rfq_id": rfq1.pk,
                "items": [(items[0], 100, Decimal("22.00")), (items[1], 50, Decimal("21.00"))],
            },
            # PO-00002: partially received
            {
                "number": "PO-00002",
                "vendor": vendors[1],
                "posting_date": _d(-20),
                "expected_delivery": _d(-5),
                "status": PurchaseOrder.Status.PARTIALLY_RECEIVED,
                "items": [(items[2], 200, Decimal("15.50")), (items[3], 150, Decimal("8.75"))],
            },
            # PO-00003: submitted (pending receipt)
            {
                "number": "PO-00003",
                "vendor": vendors[2],
                "posting_date": _d(-10),
                "expected_delivery": _d(10),
                "status": PurchaseOrder.Status.SUBMITTED,
                "items": [(items[4], 80, Decimal("45.00")), (items[5], 60, Decimal("30.00"))],
            },
            # PO-00004: submitted from requisition PR-00002
            {
                "number": "PO-00004",
                "vendor": vendors[3],
                "posting_date": _d(-12),
                "expected_delivery": _d(5),
                "status": PurchaseOrder.Status.SUBMITTED,
                "requisition_id": pr1.pk,
                "items": [(items[0], 100, Decimal("21.50")), (items[1], 50, Decimal("20.00")), (items[2], 75, Decimal("14.80"))],
            },
            # PO-00005: blanket / contract PO (draft)
            {
                "number": "PO-00005",
                "vendor": vendors[0],
                "posting_date": _d(-5),
                "expected_delivery": _d(60),
                "status": PurchaseOrder.Status.DRAFT,
                "is_blanket": True,
                "items": [(items[3], 500, Decimal("8.50"))],
            },
            # PO-00006: already billed
            {
                "number": "PO-00006",
                "vendor": vendors[1],
                "posting_date": _d(-60),
                "expected_delivery": _d(-45),
                "status": PurchaseOrder.Status.BILLED,
                "items": [(items[5], 120, Decimal("28.00"))],
            },
        ]

        pos = []
        for spec in po_specs:
            vendor = spec["vendor"]
            po, created = PurchaseOrder.objects.get_or_create(
                po_number=spec["number"],
                defaults={
                    "vendor_id": vendor.pk,
                    "vendor_name": vendor.vendor_name,
                    "posting_date": spec["posting_date"],
                    "expected_delivery_date": spec.get("expected_delivery"),
                    "currency": vendor.default_currency or "USD",
                    "status": spec["status"],
                    "rfq_id": spec.get("rfq_id"),
                    "requisition_id": spec.get("requisition_id"),
                    "is_blanket_order": spec.get("is_blanket", False),
                    "blanket_order_end_date": _d(90) if spec.get("is_blanket") else None,
                    "terms_and_conditions": "Delivery terms: DDP Accra warehouse. Payment within 30 days of receipt.",
                    "company_id": company_id,
                },
            )
            if created:
                net = Decimal("0")
                for item, qty, rate in spec["items"]:
                    amount = Decimal(str(qty)) * rate
                    poi = PurchaseOrderItem.objects.create(
                        order=po,
                        item_id=item.pk,
                        item_code=item.item_code,
                        item_name=item.item_name,
                        qty=Decimal(str(qty)),
                        rate=rate,
                        amount=amount,
                        uom="EA",
                        warehouse_id=stores_wh.pk,
                        company_id=company_id,
                    )
                    net += amount
                    # Seed received qty for partially/fully received POs
                    if spec["status"] in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.BILLED):
                        poi.received_qty = poi.qty
                        poi.save(update_fields=["received_qty"])
                    elif spec["status"] == PurchaseOrder.Status.PARTIALLY_RECEIVED:
                        poi.received_qty = poi.qty / 2
                        poi.save(update_fields=["received_qty"])

                po.net_total = net
                po.grand_total = net
                po.save(update_fields=["net_total", "grand_total"])
                self.stdout.write(f"  Created PO: {po.po_number} [{po.status}] — {vendor.vendor_name} / ${net:,.2f}")
            pos.append(po)

        return pos

    # ── Goods Receipts ────────────────────────────────────────────────────────

    def _seed_goods_receipts(self, pos, items, stores_wh, company_id):
        from apps.purchasing.models import GoodsReceipt, GoodsReceiptItem, PurchaseOrder
        from apps.purchasing.hooks.goods_receipt import submit_grn

        # PO-00001 (Received): full GRN
        po1 = next((p for p in pos if p.po_number == "PO-00001"), None)
        if po1:
            grn1, c1 = GoodsReceipt.objects.get_or_create(
                grn_number="GRN-00001",
                defaults={
                    "purchase_order": po1,
                    "vendor_id": po1.vendor_id,
                    "vendor_name": po1.vendor_name,
                    "posting_date": _d(-13),
                    "status": GoodsReceipt.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c1:
                for poi in po1.items.all():
                    GoodsReceiptItem.objects.create(
                        receipt=grn1,
                        po_item=poi,
                        item_id=poi.item_id,
                        item_code=poi.item_code,
                        item_name=poi.item_name,
                        qty=poi.qty,
                        accepted_qty=poi.qty,
                        rejected_qty=Decimal("0"),
                        rate=poi.rate,
                        amount=poi.amount,
                        warehouse_id=stores_wh.pk,
                        warehouse_code=stores_wh.warehouse_code,
                        company_id=company_id,
                    )
                # Post to StockLedger
                submit_grn(grn1)
                self.stdout.write(f"  Created + submitted GRN: {grn1.grn_number} (full receipt for {po1.po_number})")

        # PO-00002 (Partially received): partial GRN — first 50% of ordered qty
        po2 = next((p for p in pos if p.po_number == "PO-00002"), None)
        if po2:
            grn2, c2 = GoodsReceipt.objects.get_or_create(
                grn_number="GRN-00002",
                defaults={
                    "purchase_order": po2,
                    "vendor_id": po2.vendor_id,
                    "vendor_name": po2.vendor_name,
                    "posting_date": _d(-4),
                    "status": GoodsReceipt.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c2:
                for poi in po2.items.all():
                    partial_qty = (poi.qty / 2).quantize(Decimal("0.0001"))
                    GoodsReceiptItem.objects.create(
                        receipt=grn2,
                        po_item=poi,
                        item_id=poi.item_id,
                        item_code=poi.item_code,
                        item_name=poi.item_name,
                        qty=partial_qty,
                        accepted_qty=partial_qty,
                        rejected_qty=Decimal("0"),
                        rate=poi.rate,
                        amount=partial_qty * poi.rate,
                        warehouse_id=stores_wh.pk,
                        warehouse_code=stores_wh.warehouse_code,
                        company_id=company_id,
                    )
                submit_grn(grn2)
                self.stdout.write(f"  Created + submitted GRN: {grn2.grn_number} (50% receipt for {po2.po_number})")

        # PO-00006 (Billed): historical GRN already received
        po6 = next((p for p in pos if p.po_number == "PO-00006"), None)
        if po6:
            grn6, c6 = GoodsReceipt.objects.get_or_create(
                grn_number="GRN-00003",
                defaults={
                    "purchase_order": po6,
                    "vendor_id": po6.vendor_id,
                    "vendor_name": po6.vendor_name,
                    "posting_date": _d(-44),
                    "status": GoodsReceipt.Status.SUBMITTED,
                    "company_id": company_id,
                },
            )
            if c6:
                for poi in po6.items.all():
                    # Include 2 rejected units for quality tracking
                    accepted = poi.qty - 2
                    GoodsReceiptItem.objects.create(
                        receipt=grn6,
                        po_item=poi,
                        item_id=poi.item_id,
                        item_code=poi.item_code,
                        item_name=poi.item_name,
                        qty=poi.qty,
                        accepted_qty=accepted,
                        rejected_qty=Decimal("2"),
                        rate=poi.rate,
                        amount=accepted * poi.rate,
                        warehouse_id=stores_wh.pk,
                        warehouse_code=stores_wh.warehouse_code,
                        company_id=company_id,
                    )
                submit_grn(grn6)
                self.stdout.write(f"  Created + submitted GRN: {grn6.grn_number} (historical billed PO)")

        # Draft GRN against PO-00003 (not yet submitted)
        po3 = next((p for p in pos if p.po_number == "PO-00003"), None)
        if po3:
            grn_draft, cd = GoodsReceipt.objects.get_or_create(
                grn_number="GRN-00004",
                defaults={
                    "purchase_order": po3,
                    "vendor_id": po3.vendor_id,
                    "vendor_name": po3.vendor_name,
                    "posting_date": date.today(),
                    "status": GoodsReceipt.Status.DRAFT,
                    "company_id": company_id,
                },
            )
            if cd:
                for poi in po3.items.all():
                    GoodsReceiptItem.objects.create(
                        receipt=grn_draft,
                        po_item=poi,
                        item_id=poi.item_id,
                        item_code=poi.item_code,
                        item_name=poi.item_name,
                        qty=poi.qty,
                        accepted_qty=poi.qty,
                        rejected_qty=Decimal("0"),
                        rate=poi.rate,
                        amount=poi.amount,
                        warehouse_id=stores_wh.pk,
                        warehouse_code=stores_wh.warehouse_code,
                        company_id=company_id,
                    )
                self.stdout.write(f"  Created DRAFT GRN: {grn_draft.grn_number} (pending submission)")

    # ── Landed Costs ──────────────────────────────────────────────────────────

    def _seed_landed_costs(self, company_id):
        from apps.purchasing.models import (
            GoodsReceipt, LandedCost, LandedCostCharge, LandedCostAllocation,
        )

        grn1 = GoodsReceipt.objects.filter(grn_number="GRN-00001", company_id=company_id).first()
        if not grn1:
            return

        lc, created = LandedCost.objects.get_or_create(
            landed_cost_number="LC-00001",
            defaults={
                "goods_receipt": grn1,
                "posting_date": _d(-12),
                "allocation_method": LandedCost.AllocationMethod.BY_AMOUNT,
                "is_posted": True,
                "company_id": company_id,
            },
        )
        if created:
            freight = LandedCostCharge.objects.create(
                landed_cost=lc,
                charge_type="freight",
                description="Freight from Tema Port to Accra warehouse",
                amount=Decimal("350.00"),
                company_id=company_id,
            )
            insurance = LandedCostCharge.objects.create(
                landed_cost=lc,
                charge_type="insurance",
                description="Cargo insurance",
                amount=Decimal("75.00"),
                company_id=company_id,
            )
            total_charges = freight.amount + insurance.amount
            grn_items = list(grn1.items.filter(is_deleted=False))
            base_total = sum(i.amount for i in grn_items) or Decimal("1")
            for gi in grn_items:
                LandedCostAllocation.objects.create(
                    landed_cost=lc,
                    grn_item=gi,
                    allocated_amount=(total_charges * (gi.amount / base_total)).quantize(Decimal("0.0001")),
                    company_id=company_id,
                )
            lc.total_taxes_and_charges = total_charges
            lc.save(update_fields=["total_taxes_and_charges"])
            self.stdout.write(f"  Created LandedCost: {lc.landed_cost_number} (freight + insurance on GRN-00001)")

    # ── Vendor Scorecards ─────────────────────────────────────────────────────

    def _seed_vendor_scorecards(self, vendors, company_id):
        from apps.purchasing.models import VendorScorecard

        period_start = date(date.today().year, 1, 1)
        period_end = date(date.today().year, 3, 31)

        scorecard_data = [
            {
                "vendor": vendors[0],
                "total_pos": 8,
                "on_time_pos": 7,
                "on_time_pct": Decimal("87.50"),
                "total_received": Decimal("1500"),
                "rejected": Decimal("12"),
                "rejection_pct": Decimal("0.80"),
                "price_variance": Decimal("-2.50"),
                "composite": Decimal("86.85"),
            },
            {
                "vendor": vendors[1],
                "total_pos": 5,
                "on_time_pos": 3,
                "on_time_pct": Decimal("60.00"),
                "total_received": Decimal("800"),
                "rejected": Decimal("40"),
                "rejection_pct": Decimal("5.00"),
                "price_variance": Decimal("1.20"),
                "composite": Decimal("67.50"),
            },
            {
                "vendor": vendors[2],
                "total_pos": 3,
                "on_time_pos": 3,
                "on_time_pct": Decimal("100.00"),
                "total_received": Decimal("350"),
                "rejected": Decimal("0"),
                "rejection_pct": Decimal("0.00"),
                "price_variance": Decimal("0.00"),
                "composite": Decimal("100.00"),
            },
        ]

        for sd in scorecard_data:
            v = sd["vendor"]
            obj, created = VendorScorecard.objects.get_or_create(
                vendor_id=v.pk,
                period_start=period_start,
                period_end=period_end,
                company_id=company_id,
                defaults={
                    "vendor_name": v.vendor_name,
                    "total_pos": sd["total_pos"],
                    "on_time_pos": sd["on_time_pos"],
                    "on_time_delivery_pct": sd["on_time_pct"],
                    "total_received_qty": sd["total_received"],
                    "rejected_qty": sd["rejected"],
                    "quality_rejection_pct": sd["rejection_pct"],
                    "price_variance_pct": sd["price_variance"],
                    "composite_score": sd["composite"],
                },
            )
            if created:
                self.stdout.write(f"  Created VendorScorecard: {v.vendor_name} — score {sd['composite']}")

    # ── Purchase Return ───────────────────────────────────────────────────────

    def _seed_purchase_return(self, company_id):
        from apps.purchasing.models import (
            GoodsReceipt, GoodsReceiptItem,
            PurchaseReturn, PurchaseReturnItem,
        )
        from apps.purchasing.hooks.goods_receipt import submit_grn as submit_return_stock

        grn3 = GoodsReceipt.objects.filter(grn_number="GRN-00003", company_id=company_id).first()
        if not grn3:
            return

        # 2 units were rejected on GRN-00003 — return them
        grn_items = list(grn3.items.filter(rejected_qty__gt=0, is_deleted=False))
        if not grn_items:
            return

        prn, created = PurchaseReturn.objects.get_or_create(
            return_number="PRN-00001",
            defaults={
                "goods_receipt": grn3,
                "vendor_id": grn3.vendor_id,
                "vendor_name": grn3.vendor_name,
                "posting_date": _d(-42),
                "return_reason": "2 units received damaged — rejecting and returning to supplier for credit.",
                "status": PurchaseReturn.Status.SUBMITTED,
                "company_id": company_id,
            },
        )
        if created:
            net = Decimal("0")
            for gi in grn_items:
                amount = gi.rejected_qty * gi.rate
                PurchaseReturnItem.objects.create(
                    purchase_return=prn,
                    grn_item=gi,
                    item_id=gi.item_id,
                    item_code=gi.item_code,
                    item_name=gi.item_name,
                    qty=gi.rejected_qty,
                    rate=gi.rate,
                    amount=amount,
                    warehouse_id=gi.warehouse_id,
                    reason="Damaged on arrival",
                    company_id=company_id,
                )
                net += amount

            prn.net_total = net
            prn.save(update_fields=["net_total"])
            self.stdout.write(f"  Created PurchaseReturn: {prn.return_number} — ${net:,.2f} (2 damaged units returned)")
