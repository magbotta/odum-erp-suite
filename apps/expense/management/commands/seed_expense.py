"""Seed command: Expense & Travel (§6.11).

Creates realistic demo data:
- 4 expense categories with policy limits
- 1 expense policy with per-category rules
- 2 mileage rates (car & motorcycle)
- 4 corporate cards
- 6 expense claims (various statuses, some with policy violations)
- 3 travel requests (approved with itinerary, submitted, draft)
- 5 mileage logs
- 2 corporate card statements with charges and auto-match run
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand


def _d(offset_days: int = 0) -> datetime.date:
    return datetime.date.today() + datetime.timedelta(days=offset_days)


# Stable placeholder UUIDs for cross-app employee refs (would be HRM Employee PKs)
EMP_ALEX = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
EMP_EFUA = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002")
EMP_KOJO = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000003")
EMP_ABENA = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000004")

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Command(BaseCommand):
    help = "Seed Expense & Travel demo data"

    def handle(self, *args, **options):
        self.stdout.write("=== Expense & Travel seed ===")

        categories = self._seed_categories()
        policy = self._seed_policy(categories)
        mileage_rates = self._seed_mileage_rates()
        cards = self._seed_corporate_cards()
        claims = self._seed_expense_claims(categories, policy)
        self._seed_travel_requests(policy)
        self._seed_mileage_logs(claims, mileage_rates)
        self._seed_card_statements(cards, claims)

        self.stdout.write("Expense & Travel seed complete.")

    # ── Categories ──────────────────────────────────────────────────────

    def _seed_categories(self):
        from apps.expense.models import ExpenseCategory

        specs = [
            dict(
                name="Meals & Entertainment",
                code="MEALS",
                description="Business meals, client entertainment, team lunches",
                daily_limit=Decimal("75.00"),
                per_claim_limit=Decimal("200.00"),
                requires_receipt_above=Decimal("25.00"),
                is_mileage=False,
            ),
            dict(
                name="Accommodation",
                code="HOTEL",
                description="Hotels and serviced apartments for business travel",
                daily_limit=Decimal("200.00"),
                per_claim_limit=Decimal("500.00"),
                requires_receipt_above=Decimal("0.01"),
                is_mileage=False,
            ),
            dict(
                name="Transportation",
                code="TRANSPORT",
                description="Flights, trains, taxis, rideshare, airport transfers",
                daily_limit=Decimal("0"),
                per_claim_limit=Decimal("1500.00"),
                requires_receipt_above=Decimal("10.00"),
                is_mileage=False,
            ),
            dict(
                name="Mileage",
                code="MILEAGE",
                description="Personal vehicle mileage reimbursement",
                daily_limit=Decimal("0"),
                per_claim_limit=Decimal("0"),
                requires_receipt_above=Decimal("0"),
                is_mileage=True,
            ),
            dict(
                name="Office Supplies",
                code="SUPPLIES",
                description="Stationery, printer ink, small office purchases",
                daily_limit=Decimal("0"),
                per_claim_limit=Decimal("100.00"),
                requires_receipt_above=Decimal("5.00"),
                is_mileage=False,
            ),
        ]

        cats = []
        for s in specs:
            cat, created = ExpenseCategory.objects.get_or_create(
                code=s["code"],
                defaults={**s, "company_id": COMPANY_ID},
            )
            if created:
                self.stdout.write("  Created Category: {}".format(cat.name))
            cats.append(cat)
        return cats

    # ── Policy ──────────────────────────────────────────────────────────

    def _seed_policy(self, categories):
        from apps.expense.models import ExpensePolicy, ExpensePolicyRule

        policy, created = ExpensePolicy.objects.get_or_create(
            name="Standard Employee Policy",
            defaults={
                "is_active": True,
                "max_hotel_rate_per_night": Decimal("180.00"),
                "max_flight_fare_class": "economy",
                "mileage_rate_per_km": Decimal("0.45"),
                "company_id": COMPANY_ID,
            },
        )
        if created:
            self.stdout.write("  Created Policy: {}".format(policy.name))

        # Per-category rules (stricter limits than category defaults)
        cat_map = {c.code: c for c in categories}
        rules = [
            dict(category=cat_map["MEALS"], daily_limit=Decimal("60.00"), per_claim_limit=Decimal("150.00"), requires_receipt=True),
            dict(category=cat_map["HOTEL"], daily_limit=Decimal("180.00"), per_claim_limit=Decimal("500.00"), requires_receipt=True),
            dict(category=cat_map["TRANSPORT"], daily_limit=Decimal("0"), per_claim_limit=Decimal("1200.00"), requires_receipt=True),
        ]
        for r in rules:
            ExpensePolicyRule.objects.get_or_create(
                policy=policy,
                category=r["category"],
                defaults={
                    "daily_limit": r["daily_limit"],
                    "per_claim_limit": r["per_claim_limit"],
                    "requires_receipt": r["requires_receipt"],
                    "company_id": COMPANY_ID,
                },
            )

        return policy

    # ── Mileage Rates ───────────────────────────────────────────────────

    def _seed_mileage_rates(self):
        from apps.expense.models import MileageRate

        specs = [
            dict(
                name="Standard Car Rate 2025",
                vehicle_type=MileageRate.VehicleType.CAR,
                rate_per_km=Decimal("0.4500"),
                rate_per_mile=Decimal("0.7242"),
                currency="USD",
                effective_from=datetime.date(2025, 1, 1),
            ),
            dict(
                name="Motorcycle Rate 2025",
                vehicle_type=MileageRate.VehicleType.MOTORCYCLE,
                rate_per_km=Decimal("0.2800"),
                rate_per_mile=Decimal("0.4506"),
                currency="USD",
                effective_from=datetime.date(2025, 1, 1),
            ),
        ]

        rates = []
        for s in specs:
            rate, created = MileageRate.objects.get_or_create(
                name=s["name"],
                defaults={**s, "is_active": True, "company_id": COMPANY_ID},
            )
            if created:
                self.stdout.write("  Created MileageRate: {}".format(rate.name))
            rates.append(rate)
        return rates

    # ── Corporate Cards ─────────────────────────────────────────────────

    def _seed_corporate_cards(self):
        from apps.expense.models import CorporateCard

        specs = [
            dict(employee_id=EMP_ALEX, employee_name="Alex Mensah", card_number_last4="4242", card_network="visa", card_type="corporate", credit_limit=Decimal("5000.00")),
            dict(employee_id=EMP_EFUA, employee_name="Efua Boateng", card_number_last4="5678", card_network="mastercard", card_type="corporate", credit_limit=Decimal("3000.00")),
            dict(employee_id=EMP_KOJO, employee_name="Kojo Asante", card_number_last4="3333", card_network="amex", card_type="purchase", credit_limit=Decimal("8000.00")),
            dict(employee_id=EMP_ABENA, employee_name="Abena Osei", card_number_last4="9999", card_network="visa", card_type="virtual", credit_limit=Decimal("1000.00")),
        ]

        cards = []
        for s in specs:
            card, created = CorporateCard.objects.get_or_create(
                employee_id=s["employee_id"],
                card_number_last4=s["card_number_last4"],
                defaults={**s, "currency": "USD", "is_active": True, "company_id": COMPANY_ID},
            )
            if created:
                self.stdout.write("  Created CorporateCard: {} *{}".format(card.employee_name, card.card_number_last4))
            cards.append(card)
        return cards

    # ── Expense Claims ──────────────────────────────────────────────────

    def _seed_expense_claims(self, categories, policy):
        from apps.expense.models import ExpenseClaim, ExpenseClaimLine
        from apps.expense.hooks.expense_claim import submit_claim, approve_claim, reimburse_claim

        cat = {c.code: c for c in categories}
        claims = []

        # Claim 1 — Alex, reimbursed, Accra client trip
        claim1, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00001",
            defaults=dict(
                employee_id=EMP_ALEX,
                employee_name="Alex Mensah",
                from_date=_d(-45),
                to_date=_d(-42),
                purpose="Client meeting — Accra",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.AP_PAYMENT,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            _add_line(claim1, cat["HOTEL"], "Labadi Beach Hotel x3 nights", Decimal("165.00"), _d(-45), receipt=True)
            _add_line(claim1, cat["MEALS"], "Client dinner at Santoku", Decimal("87.50"), _d(-44), receipt=True, violation=True, violation_reason="Meals claim limit is 150.00; submitted 87.50 — over daily limit 60.00")
            _add_line(claim1, cat["TRANSPORT"], "Airport taxi both ways", Decimal("45.00"), _d(-45), receipt=True)
            submit_claim(claim1)
            claim1.status = ExpenseClaim.Status.SUBMITTED
            claim1.save(update_fields=["status"])
            approve_claim(claim1)
            reimburse_claim(claim1, payment_reference="PMT-2025-0341", reimbursed_at=_d(-38))
            self.stdout.write("  Created Claim: EXP-00001 [reimbursed] — Alex Mensah")
        claims.append(claim1)

        # Claim 2 — Efua, approved, Kumasi office visit
        claim2, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00002",
            defaults=dict(
                employee_id=EMP_EFUA,
                employee_name="Efua Boateng",
                from_date=_d(-30),
                to_date=_d(-28),
                purpose="Kumasi office support visit",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.AP_PAYMENT,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            _add_line(claim2, cat["HOTEL"], "Golden Tulip Kumasi x2 nights", Decimal("130.00"), _d(-30), receipt=True)
            _add_line(claim2, cat["TRANSPORT"], "Bus ticket Accra–Kumasi return", Decimal("38.00"), _d(-30), receipt=True)
            _add_line(claim2, cat["MEALS"], "Team lunch x2 days", Decimal("52.00"), _d(-29), receipt=True)
            submit_claim(claim2)
            claim2.status = ExpenseClaim.Status.SUBMITTED
            claim2.save(update_fields=["status"])
            approve_claim(claim2)
            self.stdout.write("  Created Claim: EXP-00002 [approved] — Efua Boateng")
        claims.append(claim2)

        # Claim 3 — Kojo, submitted with policy violation
        claim3, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00003",
            defaults=dict(
                employee_id=EMP_KOJO,
                employee_name="Kojo Asante",
                from_date=_d(-20),
                to_date=_d(-18),
                purpose="Lagos partner conference",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.AP_PAYMENT,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            # Hotel exceeds policy cap ($250 > $180/night)
            _add_line(claim3, cat["HOTEL"], "Eko Hotels Lagos x2 nights", Decimal("250.00"), _d(-20), receipt=True)
            _add_line(claim3, cat["TRANSPORT"], "Return flight Lagos", Decimal("380.00"), _d(-20), receipt=True)
            _add_line(claim3, cat["MEALS"], "Conference meals x3 days", Decimal("55.00"), _d(-19), receipt=False)
            submit_claim(claim3)
            claim3.status = ExpenseClaim.Status.SUBMITTED
            claim3.save(update_fields=["status"])
            self.stdout.write("  Created Claim: EXP-00003 [submitted, has violation] — Kojo Asante")
        claims.append(claim3)

        # Claim 4 — Abena, submitted
        claim4, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00004",
            defaults=dict(
                employee_id=EMP_ABENA,
                employee_name="Abena Osei",
                from_date=_d(-15),
                to_date=_d(-14),
                purpose="Office supplies purchase",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.PAYROLL,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            _add_line(claim4, cat["SUPPLIES"], "Printer cartridges", Decimal("68.00"), _d(-15), receipt=True)
            _add_line(claim4, cat["SUPPLIES"], "Notebooks and pens", Decimal("22.00"), _d(-15), receipt=True)
            submit_claim(claim4)
            claim4.status = ExpenseClaim.Status.SUBMITTED
            claim4.save(update_fields=["status"])
            self.stdout.write("  Created Claim: EXP-00004 [submitted] — Abena Osei")
        claims.append(claim4)

        # Claim 5 — Alex, rejected
        claim5, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00005",
            defaults=dict(
                employee_id=EMP_ALEX,
                employee_name="Alex Mensah",
                from_date=_d(-60),
                to_date=_d(-60),
                purpose="Team celebration dinner",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.AP_PAYMENT,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            _add_line(claim5, cat["MEALS"], "Team dinner — non-business", Decimal("320.00"), _d(-60), receipt=True)
            submit_claim(claim5)
            claim5.status = ExpenseClaim.Status.SUBMITTED
            claim5.save(update_fields=["status"])
            from apps.expense.hooks.expense_claim import reject_claim
            reject_claim(claim5, reason="Personal celebration not eligible for reimbursement")
            self.stdout.write("  Created Claim: EXP-00005 [rejected] — Alex Mensah")
        claims.append(claim5)

        # Claim 6 — Efua, draft
        claim6, created = ExpenseClaim.objects.get_or_create(
            claim_number="EXP-00006",
            defaults=dict(
                employee_id=EMP_EFUA,
                employee_name="Efua Boateng",
                from_date=_d(-5),
                to_date=_d(-3),
                purpose="Cape Coast district training",
                policy=policy,
                currency="USD",
                status=ExpenseClaim.Status.DRAFT,
                reimbursement_method=ExpenseClaim.ReimbursementMethod.AP_PAYMENT,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            _add_line(claim6, cat["HOTEL"], "Hans Cottage Botel x2 nights", Decimal("95.00"), _d(-5), receipt=False)
            _add_line(claim6, cat["TRANSPORT"], "Shared taxi Cape Coast", Decimal("28.00"), _d(-5), receipt=True)
            self.stdout.write("  Created Claim: EXP-00006 [draft] — Efua Boateng")
        claims.append(claim6)

        return claims

    # ── Travel Requests ─────────────────────────────────────────────────

    def _seed_travel_requests(self, policy):
        from apps.expense.models import TravelRequest, TravelItinerary
        from apps.expense.hooks.expense_claim import approve_claim

        # TR-1: approved with itinerary
        tr1, created = TravelRequest.objects.get_or_create(
            request_number="TR-00001",
            defaults=dict(
                employee_id=EMP_KOJO,
                employee_name="Kojo Asante",
                purpose="Q3 partner summit — Nairobi",
                destination="Nairobi, Kenya",
                from_date=_d(10),
                to_date=_d(14),
                estimated_cost=Decimal("1850.00"),
                currency="USD",
                policy=policy,
                status=TravelRequest.Status.APPROVED,
                booking_status=TravelRequest.BookingStatus.BOOKED,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            TravelItinerary.objects.create(
                travel_request=tr1,
                segment_type=TravelItinerary.SegmentType.FLIGHT,
                description="Accra (ACC) → Nairobi (NBO) return — Kenya Airways",
                from_date=_d(10),
                to_date=_d(14),
                vendor="Kenya Airways",
                booking_ref="KQ-2025-8812",
                cost=Decimal("920.00"),
                currency="USD",
                policy_compliant=True,
                company_id=COMPANY_ID,
            )
            TravelItinerary.objects.create(
                travel_request=tr1,
                segment_type=TravelItinerary.SegmentType.HOTEL,
                description="Radisson Blu Nairobi x4 nights",
                from_date=_d(10),
                to_date=_d(14),
                vendor="Radisson Blu",
                booking_ref="RBN-44771",
                cost=Decimal("720.00"),
                currency="USD",
                policy_compliant=False,
                violation_note="Rate $180/night equals policy cap; approved with CFO exception",
                company_id=COMPANY_ID,
            )
            self.stdout.write("  Created TravelRequest: TR-00001 [approved, booked] — Kojo Asante → Nairobi")

        # TR-2: submitted awaiting approval
        tr2, created = TravelRequest.objects.get_or_create(
            request_number="TR-00002",
            defaults=dict(
                employee_id=EMP_ABENA,
                employee_name="Abena Osei",
                purpose="Client onboarding — Takoradi",
                destination="Takoradi, Ghana",
                from_date=_d(7),
                to_date=_d(9),
                estimated_cost=Decimal("420.00"),
                currency="USD",
                policy=policy,
                status=TravelRequest.Status.SUBMITTED,
                booking_status=TravelRequest.BookingStatus.NOT_BOOKED,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            self.stdout.write("  Created TravelRequest: TR-00002 [submitted] — Abena Osei → Takoradi")

        # TR-3: draft
        tr3, created = TravelRequest.objects.get_or_create(
            request_number="TR-00003",
            defaults=dict(
                employee_id=EMP_EFUA,
                employee_name="Efua Boateng",
                purpose="Regional sales conference — Lomé",
                destination="Lomé, Togo",
                from_date=_d(20),
                to_date=_d(22),
                estimated_cost=Decimal("650.00"),
                currency="USD",
                policy=policy,
                status=TravelRequest.Status.DRAFT,
                booking_status=TravelRequest.BookingStatus.NOT_BOOKED,
                company_id=COMPANY_ID,
            ),
        )
        if created:
            self.stdout.write("  Created TravelRequest: TR-00003 [draft] — Efua Boateng → Lomé")

    # ── Mileage Logs ───────────────────────────────────────────────────

    def _seed_mileage_logs(self, claims, mileage_rates):
        from apps.expense.models import MileageLog

        car_rate = next((r for r in mileage_rates if r.vehicle_type == "car"), None)
        moto_rate = next((r for r in mileage_rates if r.vehicle_type == "motorcycle"), None)

        # Link to EXP-00001 (Alex, reimbursed)
        claim1 = next((c for c in claims if c.claim_number == "EXP-00001"), None)

        logs = [
            dict(
                claim=claim1,
                employee_id=EMP_ALEX,
                employee_name="Alex Mensah",
                trip_date=_d(-44),
                from_location="Accra Office, Airport Road",
                to_location="Labadi Beach Hotel",
                distance_km=Decimal("12.5"),
                mileage_rate=car_rate,
                reimbursable_amount=(Decimal("12.5") * Decimal("0.45")).quantize(Decimal("0.01")),
                purpose="Client site transfer",
            ),
            dict(
                claim=None,
                employee_id=EMP_EFUA,
                employee_name="Efua Boateng",
                trip_date=_d(-28),
                from_location="Kumasi Suame Office",
                to_location="GCB Bank Kumasi",
                distance_km=Decimal("8.2"),
                mileage_rate=car_rate,
                reimbursable_amount=(Decimal("8.2") * Decimal("0.45")).quantize(Decimal("0.01")),
                purpose="Bank run for petty cash",
            ),
            dict(
                claim=None,
                employee_id=EMP_KOJO,
                employee_name="Kojo Asante",
                trip_date=_d(-18),
                from_location="East Legon",
                to_location="Kotoka International Airport",
                distance_km=Decimal("15.0"),
                mileage_rate=car_rate,
                reimbursable_amount=(Decimal("15.0") * Decimal("0.45")).quantize(Decimal("0.01")),
                purpose="Airport drop-off for Lagos trip",
            ),
            dict(
                claim=None,
                employee_id=EMP_ABENA,
                employee_name="Abena Osei",
                trip_date=_d(-14),
                from_location="Osu Office",
                to_location="Makola Market",
                distance_km=Decimal("5.8"),
                mileage_rate=moto_rate,
                reimbursable_amount=(Decimal("5.8") * Decimal("0.28")).quantize(Decimal("0.01")),
                purpose="Office supplies errand",
            ),
            dict(
                claim=None,
                employee_id=EMP_ALEX,
                employee_name="Alex Mensah",
                trip_date=_d(-7),
                from_location="Airport Residential",
                to_location="Client HQ, Tema",
                distance_km=Decimal("28.3"),
                mileage_rate=car_rate,
                reimbursable_amount=(Decimal("28.3") * Decimal("0.45")).quantize(Decimal("0.01")),
                purpose="Customer site visit",
            ),
        ]

        for l in logs:
            log, created = MileageLog.objects.get_or_create(
                employee_id=l["employee_id"],
                trip_date=l["trip_date"],
                from_location=l["from_location"],
                defaults={**l, "distance_miles": Decimal("0"), "company_id": COMPANY_ID},
            )
            if created:
                self.stdout.write("  Created MileageLog: {} → {} ({} km)".format(
                    l["from_location"][:20], l["to_location"][:20], l["distance_km"]
                ))

    # ── Corporate Card Statements ───────────────────────────────────────

    def _seed_card_statements(self, cards, claims):
        from apps.expense.hooks.corporate_card import import_statement, auto_match_statement
        from apps.expense.models import CorporateCardStatement

        alex_card = next((c for c in cards if c.employee_name == "Alex Mensah"), None)
        efua_card = next((c for c in cards if c.employee_name == "Efua Boateng"), None)

        # EXP-00001 lines: hotel $165, transport $45, meals $87.50
        # Match hotel and transport lines
        if not CorporateCardStatement.objects.filter(
            card=alex_card, statement_period="2025-06"
        ).exists():
            stmt = import_statement(
                alex_card,
                statement_period="2025-06",
                from_date=datetime.date(2025, 6, 1),
                to_date=datetime.date(2025, 6, 30),
                charges=[
                    dict(date=_d(-45), merchant_name="Labadi Beach Hotel", merchant_category="Hotel", amount=165.00),
                    dict(date=_d(-45), merchant_name="Accra Taxi Services", merchant_category="Transport", amount=45.00),
                    dict(date=_d(-44), merchant_name="Santoku Restaurant", merchant_category="Restaurant", amount=87.50),
                    dict(date=_d(-43), merchant_name="Shoprite Accra Mall", merchant_category="Retail", amount=34.20),
                ],
            )
            result = auto_match_statement(stmt)
            self.stdout.write(
                "  Imported card statement for Alex *4242 — matched {}/{} charges".format(
                    result["matched"], result["matched"] + result["unmatched"]
                )
            )

        # Efua card — June statement
        if not CorporateCardStatement.objects.filter(
            card=efua_card, statement_period="2025-06"
        ).exists():
            stmt2 = import_statement(
                efua_card,
                statement_period="2025-06",
                from_date=datetime.date(2025, 6, 1),
                to_date=datetime.date(2025, 6, 30),
                charges=[
                    dict(date=_d(-30), merchant_name="Golden Tulip Kumasi", merchant_category="Hotel", amount=130.00),
                    dict(date=_d(-30), merchant_name="STC Bus Terminal", merchant_category="Transport", amount=38.00),
                    dict(date=_d(-29), merchant_name="Royal Meal Kumasi", merchant_category="Restaurant", amount=52.00),
                ],
            )
            result2 = auto_match_statement(stmt2)
            self.stdout.write(
                "  Imported card statement for Efua *5678 — matched {}/{} charges".format(
                    result2["matched"], result2["matched"] + result2["unmatched"]
                )
            )


# ── Helper ──────────────────────────────────────────────────────────────────

def _add_line(claim, category, description, amount, date, receipt=True, violation=False, violation_reason=""):
    from apps.expense.models import ExpenseClaimLine

    ExpenseClaimLine.objects.get_or_create(
        claim=claim,
        description=description,
        defaults=dict(
            expense_date=date,
            category=category,
            amount=amount,
            sanctioned_amount=amount,
            currency="USD",
            exchange_rate=Decimal("1"),
            amount_in_company_currency=amount,
            receipt_attached=receipt,
            policy_violation=violation,
            violation_reason=violation_reason,
            company_id=claim.company_id,
        ),
    )
