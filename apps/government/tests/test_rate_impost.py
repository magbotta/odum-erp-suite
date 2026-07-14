"""
Unit tests: rate-impost calculation logic.

Tests the _compute_rate_charge helper and the full property rate bill-run,
verifying that the correct charge is derived from rateable_value + rate_pct
and that the minimum_charge floor is applied.
"""
import uuid
from decimal import Decimal
from django.test import TestCase

from apps.government.hooks.revenue import _compute_rate_charge


class RateImpostCalculationTest(TestCase):

    def test_standard_rate_applied(self):
        # 0.5% of GHS 100,000 = GHS 500
        result = _compute_rate_charge(
            rateable_value=Decimal("100000"),
            rate_pct=Decimal("0.5"),
            minimum_charge=Decimal("50"),
        )
        self.assertEqual(result, Decimal("500.00"))

    def test_minimum_charge_floor(self):
        # 0.5% of GHS 500 = GHS 2.50, but minimum is GHS 50
        result = _compute_rate_charge(
            rateable_value=Decimal("500"),
            rate_pct=Decimal("0.5"),
            minimum_charge=Decimal("50"),
        )
        self.assertEqual(result, Decimal("50"))

    def test_minimum_charge_not_applied_when_computed_is_higher(self):
        # 1% of GHS 20,000 = GHS 200, minimum is GHS 50
        result = _compute_rate_charge(
            rateable_value=Decimal("20000"),
            rate_pct=Decimal("1"),
            minimum_charge=Decimal("50"),
        )
        self.assertEqual(result, Decimal("200.00"))

    def test_zero_rateable_value_returns_minimum(self):
        result = _compute_rate_charge(
            rateable_value=Decimal("0"),
            rate_pct=Decimal("0.5"),
            minimum_charge=Decimal("75"),
        )
        self.assertEqual(result, Decimal("75"))

    def test_fractional_pct_rounds_to_two_decimal_places(self):
        # 0.333% of GHS 1000 = 3.33 (rounded to 2dp)
        result = _compute_rate_charge(
            rateable_value=Decimal("1000"),
            rate_pct=Decimal("0.333"),
            minimum_charge=Decimal("0"),
        )
        self.assertEqual(result, Decimal("3.33"))

    def test_commercial_rate_higher_than_residential(self):
        # Simulate: residential 0.5%, commercial 1.5%, same value
        residential = _compute_rate_charge(Decimal("50000"), Decimal("0.5"), Decimal("0"))
        commercial = _compute_rate_charge(Decimal("50000"), Decimal("1.5"), Decimal("0"))
        self.assertGreater(commercial, residential)
        self.assertEqual(residential, Decimal("250.00"))
        self.assertEqual(commercial, Decimal("750.00"))


class PropertyRateBillRunTest(TestCase):

    def setUp(self):
        from apps.government.models import GASBFund, PropertyParcel, RateImpost
        import datetime

        cid = uuid.uuid4()
        self.company_id = str(cid)

        self.fund = GASBFund.objects.create(
            company_id=cid,
            name="General Fund",
            fund_number="GF-001",
            fund_type="general",
            fiscal_year=2025,
        )

        # Active parcels
        self.parcel1 = PropertyParcel.objects.create(
            company_id=cid,
            parcel_number="ACC-001",
            street_address="1 Main St",
            ward="Ablekuma North",
            property_use="residential",
            valuation_basis="annual_value",
            rateable_value=Decimal("80000"),
            owner_name="Kwame Mensah",
            owner_phone="0241234567",
            gasb_fund=self.fund,
        )
        self.parcel2 = PropertyParcel.objects.create(
            company_id=cid,
            parcel_number="ACC-002",
            street_address="5 Commercial Ave",
            ward="Ablekuma North",
            property_use="commercial",
            valuation_basis="annual_value",
            rateable_value=Decimal("200000"),
            owner_name="Ama Owusu Trading",
            owner_phone="0271234567",
            gasb_fund=self.fund,
        )

        # Exempt parcel (exemption_reason is not empty → excluded from billing)
        # NOTE: our query filters: exemption_reason="" means NOT exempt
        # Exempt parcel has exemption_reason set
        self.exempt_parcel = PropertyParcel.objects.create(
            company_id=cid,
            parcel_number="ACC-EX1",
            street_address="10 Church Rd",
            ward="Ablekuma North",
            property_use="government",
            valuation_basis="annual_value",
            rateable_value=Decimal("500000"),
            owner_name="District Assembly",
            exemption_reason="Government property — exempt under LGA 2016",
            gasb_fund=self.fund,
        )

        # Rate impostes
        RateImpost.objects.create(
            company_id=cid,
            fiscal_year=2025,
            property_use="residential",
            valuation_basis="annual_value",
            rate_pct=Decimal("0.5"),
            minimum_charge=Decimal("50"),
            penalty_rate_pct=Decimal("10"),
            grace_period_days=30,
            effective_from=datetime.date(2025, 1, 1),
            gasb_fund=self.fund,
        )
        RateImpost.objects.create(
            company_id=cid,
            fiscal_year=2025,
            property_use="commercial",
            valuation_basis="annual_value",
            rate_pct=Decimal("1.5"),
            minimum_charge=Decimal("100"),
            penalty_rate_pct=Decimal("10"),
            grace_period_days=30,
            effective_from=datetime.date(2025, 1, 1),
            gasb_fund=self.fund,
        )

    def test_bill_run_creates_correct_number_of_bills(self):
        from apps.government.hooks.revenue import run_property_rate_bill_run
        from unittest.mock import patch

        with patch("apps.government.hooks.revenue.get_next_number",
                   side_effect=lambda prefix, cid: "{0}-{1}".format(prefix, uuid.uuid4().hex[:6])):
            ids = run_property_rate_bill_run(2025, self.company_id)

        # Only 2 non-exempt active parcels
        self.assertEqual(len(ids), 2)

    def test_bill_run_idempotent(self):
        from apps.government.hooks.revenue import run_property_rate_bill_run
        from unittest.mock import patch

        with patch("apps.government.hooks.revenue.get_next_number",
                   side_effect=lambda p, c: "{0}-{1}".format(p, uuid.uuid4().hex[:6])):
            ids_first = run_property_rate_bill_run(2025, self.company_id)
            ids_second = run_property_rate_bill_run(2025, self.company_id)

        self.assertEqual(len(ids_first), 2)
        self.assertEqual(len(ids_second), 0, "Re-run must not create duplicate bills.")

    def test_residential_bill_amount_correct(self):
        from apps.government.hooks.revenue import run_property_rate_bill_run
        from apps.government.models import GovernmentRevenueBill
        from unittest.mock import patch

        with patch("apps.government.hooks.revenue.get_next_number",
                   side_effect=lambda p, c: "{0}-{1}".format(p, uuid.uuid4().hex[:6])):
            run_property_rate_bill_run(2025, self.company_id)

        bill = GovernmentRevenueBill.objects.get(
            parcel_id=self.parcel1.id, fiscal_year=2025
        )
        # 0.5% of 80,000 = 400
        self.assertEqual(bill.payable_amount, Decimal("400.00"))

    def test_commercial_bill_amount_correct(self):
        from apps.government.hooks.revenue import run_property_rate_bill_run
        from apps.government.models import GovernmentRevenueBill
        from unittest.mock import patch

        with patch("apps.government.hooks.revenue.get_next_number",
                   side_effect=lambda p, c: "{0}-{1}".format(p, uuid.uuid4().hex[:6])):
            run_property_rate_bill_run(2025, self.company_id)

        bill = GovernmentRevenueBill.objects.get(
            parcel_id=self.parcel2.id, fiscal_year=2025
        )
        # 1.5% of 200,000 = 3,000
        self.assertEqual(bill.payable_amount, Decimal("3000.00"))

    def test_exempt_parcel_has_no_bill(self):
        from apps.government.hooks.revenue import run_property_rate_bill_run
        from apps.government.models import GovernmentRevenueBill
        from unittest.mock import patch

        with patch("apps.government.hooks.revenue.get_next_number",
                   side_effect=lambda p, c: "{0}-{1}".format(p, uuid.uuid4().hex[:6])):
            run_property_rate_bill_run(2025, self.company_id)

        self.assertFalse(
            GovernmentRevenueBill.objects.filter(parcel_id=self.exempt_parcel.id).exists()
        )
