"""Seed Asset Management demo data (§6.2)."""
from __future__ import annotations

import datetime
import uuid as _uuid
from decimal import Decimal

from django.core.management.base import BaseCommand

COMPANY_ID = _uuid.UUID("00000000-0000-0000-0000-000000000001")

EMP_ALEX  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
EMP_EFUA  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002")
EMP_KOJO  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000003")
EMP_ABENA = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000004")
EMP_KWAME = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000005")


class Command(BaseCommand):
    help = "Seed Asset Management demo data"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Asset Management data...")
        categories = self._seed_categories()
        assets = self._seed_assets(categories)
        self._seed_maintenance(assets)
        self._seed_movements(assets)
        self._seed_revaluations(assets)
        self._seed_insurance_warranties(assets)
        self._seed_leases(assets)
        self._seed_audit(assets)
        self._generate_depreciation(assets)
        self.stdout.write(self.style.SUCCESS("Asset Management seed complete."))

    # ── Categories ────────────────────────────────────────────────────────────

    def _seed_categories(self):
        from apps.asset_management.models import AssetCategory

        cats_data = [
            # (name, method, life_years, salvage_pct)
            ("Computer Equipment",   "straight_line",    3,  5),
            ("Office Furniture",     "straight_line",    7, 10),
            ("Motor Vehicles",       "declining_balance", 5, 15),
            ("Machinery & Plant",    "straight_line",   10,  5),
            ("Buildings",            "straight_line",   40,  0),
            ("Intangible Assets",    "straight_line",    5,  0),
            ("Leasehold Improvements","straight_line",  10,  0),
        ]
        cats = {}
        for name, method, life, salvage in cats_data:
            cat, _ = AssetCategory.objects.get_or_create(
                name=name,
                defaults={
                    "depreciation_method": method,
                    "useful_life_years": life,
                    "salvage_value_pct": salvage,
                    "company_id": COMPANY_ID,
                },
            )
            cats[name] = cat
        self.stdout.write("  Categories: {}".format(len(cats)))
        return cats

    # ── Assets ────────────────────────────────────────────────────────────────

    def _seed_assets(self, categories):
        from apps.asset_management.models import Asset

        # (code, name, category_key, status, purchase_date, price, location, custodian, serial)
        assets_data = [
            # Active assets
            ("AST-0001", "Dell Latitude 15 — Alex",       "Computer Equipment",    "active",
             datetime.date(2024, 3, 1),  1_800, "Head Office - Desk 4A", EMP_ALEX,  "DLLAT15-00001"),
            ("AST-0002", "Dell Latitude 15 — Efua",       "Computer Equipment",    "active",
             datetime.date(2024, 3, 1),  1_800, "Head Office - Desk 3B", EMP_EFUA,  "DLLAT15-00002"),
            ("AST-0003", "HP LaserJet 4000 — Finance",    "Computer Equipment",    "active",
             datetime.date(2023, 6, 15), 1_200, "Head Office - Finance Wing", None, "HPLJ4-FIN-001"),
            ("AST-0004", "Reception Desk & Chairs Set",   "Office Furniture",      "active",
             datetime.date(2022, 1, 10), 3_500, "Head Office - Reception", None,    ""),
            ("AST-0005", "Conference Table (12-seater)",  "Office Furniture",      "active",
             datetime.date(2022, 1, 10), 5_200, "Head Office - Board Room", None,   ""),
            ("AST-0006", "Toyota HiLux — Fleet 001",      "Motor Vehicles",        "active",
             datetime.date(2023, 2, 28), 48_000, "Accra Motor Pool",      EMP_KOJO, "GH-ACC-2023-001"),
            ("AST-0007", "Toyota HiLux — Fleet 002",      "Motor Vehicles",        "active",
             datetime.date(2023, 2, 28), 48_000, "Kumasi Office",         EMP_ABENA,"GH-KSI-2023-001"),
            ("AST-0008", "Industrial Generator 80kVA",    "Machinery & Plant",     "active",
             datetime.date(2021, 9, 15), 32_000, "Head Office - Plant Room", None,  "GEN-80KVA-001"),
            ("AST-0009", "CNC Milling Machine XL-500",    "Machinery & Plant",     "active",
             datetime.date(2020, 5, 1),  95_000, "Workshop Floor A",      EMP_KWAME,"CNC-XL500-009"),
            ("AST-0010", "Office Server Rack (2U)",       "Computer Equipment",    "active",
             datetime.date(2023, 11, 1), 8_500, "Server Room - Rack A",   None,     "SRV-RACK-001"),
            # Under maintenance
            ("AST-0011", "Ricoh Copier MP 2555",          "Computer Equipment",    "under_maintenance",
             datetime.date(2022, 4, 20), 4_200, "Head Office - Print Room", None,   "RICOH-MP2555-01"),
            # Draft (not yet capitalised)
            ("AST-0012", "MacBook Pro 16\" — New",        "Computer Equipment",    "draft",
             datetime.date(2026, 6, 30), 3_200, "Stores - Unallocated",   None,     "APMBP16-NEW-01"),
            ("AST-0013", "Standing Desk — 4 units",       "Office Furniture",      "draft",
             datetime.date(2026, 7, 1),  2_400, "Stores - Unallocated",   None,     ""),
            # Fully depreciated (old equipment)
            ("AST-0014", "HP Desktop 8200 Elite",         "Computer Equipment",    "active",
             datetime.date(2019, 1, 15), 1_100, "Archive Room",           None,     "HP8200E-014"),
            # Sold / disposed
            ("AST-0015", "Toyota Corolla — Old Fleet",    "Motor Vehicles",        "sold",
             datetime.date(2018, 6, 1),  22_000, "Disposed",              None,     "GH-OLD-2018"),
        ]

        assets = {}
        for (code, name, cat_key, status, pdate, price, location, custodian, serial) in assets_data:
            price_d = Decimal(str(price))
            cat = categories[cat_key]
            salvage = (price_d * cat.salvage_value_pct / 100).quantize(Decimal("0.01"))

            existing = Asset.objects.filter(asset_code=code).first()
            if existing:
                assets[code] = existing
                continue

            asset = Asset.objects.create(
                asset_code=code,
                asset_name=name,
                category=cat,
                status=status,
                purchase_date=pdate,
                purchase_price=price_d,
                current_value=price_d,
                salvage_value=salvage,
                useful_life_years=cat.useful_life_years,
                depreciation_method=cat.depreciation_method,
                depreciation_start_date=pdate,
                location=location,
                barcode="BC-{}".format(code),
                serial_no=serial,
                custodian_employee_id=custodian,
                custodian_name=_emp_name(custodian),
                company_id=COMPANY_ID,
            )

            # Handle sold asset
            if status == "sold":
                asset.disposal_date = datetime.date(2024, 1, 15)
                asset.disposal_amount = Decimal("8500")
                asset.disposal_reason = "Replaced by newer fleet vehicle"
                asset.save(update_fields=["disposal_date", "disposal_amount", "disposal_reason"])

            # Mark old HP desktop as fully depreciated
            if code == "AST-0014":
                asset.fully_depreciated = True
                asset.current_value = salvage
                asset.save(update_fields=["fully_depreciated", "current_value"])

            assets[code] = asset

        self.stdout.write("  Assets: {}".format(len(assets)))
        return assets

    # ── Maintenance ───────────────────────────────────────────────────────────

    def _seed_maintenance(self, assets):
        from apps.asset_management.models import AssetMaintenance

        records = [
            # (asset_code, type, scheduled, completion, status, cost, performed_by, next_date)
            ("AST-0006", "preventive", datetime.date(2026, 3, 15),
             datetime.date(2026, 3, 15), "completed", Decimal("450"),
             "AutoCare Accra", datetime.date(2026, 9, 15)),
            ("AST-0007", "preventive", datetime.date(2026, 4, 10),
             datetime.date(2026, 4, 10), "completed", Decimal("450"),
             "AutoCare Kumasi", datetime.date(2026, 10, 10)),
            ("AST-0008", "preventive", datetime.date(2026, 1, 20),
             datetime.date(2026, 1, 20), "completed", Decimal("1_200"),
             "PowerServe Ltd", datetime.date(2026, 7, 20)),
            ("AST-0008", "inspection", datetime.date(2026, 7, 20),
             None, "scheduled", Decimal("0"),
             "", datetime.date(2027, 1, 20)),
            ("AST-0009", "preventive", datetime.date(2026, 6, 1),
             None, "in_progress", Decimal("2_800"),
             "Precision Machining Services", None),
            ("AST-0011", "corrective", datetime.date(2026, 6, 28),
             None, "in_progress", Decimal("850"),
             "Ricoh Ghana Service", datetime.date(2026, 9, 28)),
            ("AST-0010", "inspection", datetime.date(2026, 5, 10),
             datetime.date(2026, 5, 10), "completed", Decimal("0"),
             "Internal IT", datetime.date(2026, 11, 10)),
        ]

        for (code, mtype, sched, comp, status, cost, performed_by, next_d) in records:
            asset = assets.get(code)
            if not asset:
                continue
            AssetMaintenance.objects.get_or_create(
                asset=asset,
                maintenance_type=mtype,
                scheduled_date=sched,
                defaults={
                    "completion_date": comp,
                    "status": status,
                    "cost": cost,
                    "performed_by": performed_by,
                    "next_maintenance_date": next_d,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Maintenance records: {}".format(len(records)))

    # ── Movements ─────────────────────────────────────────────────────────────

    def _seed_movements(self, assets):
        from apps.asset_management.models import AssetMovement

        moves = [
            ("AST-0001", datetime.date(2025, 9, 1),
             "Head Office - Desk 2C", "Head Office - Desk 4A",
             None, EMP_ALEX, "Alex Mensah", "Annual desk reshuffle"),
            ("AST-0006", datetime.date(2025, 11, 15),
             "Kumasi Office", "Accra Motor Pool",
             EMP_ABENA, EMP_KOJO, "Kojo Darko", "Reassignment — Kumasi project ended"),
            ("AST-0007", datetime.date(2025, 11, 15),
             "Accra Motor Pool", "Kumasi Office",
             EMP_KOJO, EMP_ABENA, "Abena Boateng", "Reassignment — Kumasi project started"),
        ]

        for (code, mdate, from_loc, to_loc, from_cust, to_cust, to_name, purpose) in moves:
            asset = assets.get(code)
            if not asset:
                continue
            AssetMovement.objects.get_or_create(
                asset=asset,
                movement_date=mdate,
                to_location=to_loc,
                defaults={
                    "from_location": from_loc,
                    "from_custodian_id": from_cust,
                    "to_custodian_id": to_cust,
                    "to_custodian_name": to_name,
                    "purpose": purpose,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Asset movements: {}".format(len(moves)))

    # ── Revaluations ──────────────────────────────────────────────────────────

    def _seed_revaluations(self, assets):
        from apps.asset_management.models import AssetRevaluation

        revs = [
            # Generator impairment after flood damage
            ("AST-0008", datetime.date(2025, 6, 30), "impairment",
             Decimal("18_000"), Decimal("14_500"),
             "Impairment following partial flood damage to cooling system"),
            # CNC machine revaluation (market appraisal)
            ("AST-0009", datetime.date(2024, 12, 31), "revaluation",
             Decimal("52_000"), Decimal("60_000"),
             "Independent appraisal — market value higher than book value"),
        ]

        for (code, rev_date, rtype, prev_val, new_val, reason) in revs:
            asset = assets.get(code)
            if not asset:
                continue
            AssetRevaluation.objects.get_or_create(
                asset=asset,
                revaluation_date=rev_date,
                defaults={
                    "revaluation_type": rtype,
                    "previous_value": prev_val,
                    "new_value": new_val,
                    "adjustment_amount": abs(new_val - prev_val),
                    "reason": reason,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Revaluations: {}".format(len(revs)))

    # ── Insurance & Warranties ────────────────────────────────────────────────

    def _seed_insurance_warranties(self, assets):
        from apps.asset_management.models import AssetInsurance, AssetWarranty

        insurance = [
            ("AST-0006", "POL-FLEET-2026-001", "Enterprise Insurance Ltd",
             Decimal("55_000"), Decimal("4_800"),
             datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
             "Comprehensive motor vehicle insurance"),
            ("AST-0007", "POL-FLEET-2026-002", "Enterprise Insurance Ltd",
             Decimal("55_000"), Decimal("4_800"),
             datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
             "Comprehensive motor vehicle insurance"),
            ("AST-0008", "POL-PLANT-2026-001", "Vanguard Commercial Insurance",
             Decimal("35_000"), Decimal("2_200"),
             datetime.date(2026, 1, 1), datetime.date(2026, 12, 31),
             "All-risk plant and machinery cover"),
            ("AST-0009", "POL-MACH-2025-001", "Vanguard Commercial Insurance",
             Decimal("80_000"), Decimal("6_500"),
             datetime.date(2025, 7, 1), datetime.date(2026, 7, 31),  # expiring soon-ish
             "All-risk machinery cover including business interruption"),
        ]

        for (code, pol_no, insurer, insured_val, premium, start, end, desc) in insurance:
            asset = assets.get(code)
            if not asset:
                continue
            AssetInsurance.objects.get_or_create(
                asset=asset,
                policy_number=pol_no,
                defaults={
                    "insurer_name": insurer,
                    "insured_value": insured_val,
                    "annual_premium": premium,
                    "policy_start": start,
                    "policy_end": end,
                    "coverage_description": desc,
                    "is_active": True,
                    "company_id": COMPANY_ID,
                },
            )

        warranties = [
            ("AST-0001", "WR-DELL-24-001", "Dell Technologies",
             datetime.date(2024, 3, 1), datetime.date(2027, 3, 1),
             "3-year ProSupport on-site warranty", False),
            ("AST-0002", "WR-DELL-24-002", "Dell Technologies",
             datetime.date(2024, 3, 1), datetime.date(2027, 3, 1),
             "3-year ProSupport on-site warranty", False),
            ("AST-0010", "WR-SRV-23-001", "Dell Technologies",
             datetime.date(2023, 11, 1), datetime.date(2026, 11, 1),
             "3-year ProSupport+ server warranty", False),
            ("AST-0009", "WR-CNC-20-001", "Haas Automation",
             datetime.date(2020, 5, 1), datetime.date(2022, 5, 1),
             "Original 2-year parts and labour warranty", False),
            # Extended warranty on CNC
            ("AST-0009", "WR-CNC-EXT-001", "Haas Service Ghana",
             datetime.date(2022, 5, 1), datetime.date(2025, 5, 1),
             "3-year extended service contract", True),
            ("AST-0003", "WR-HP-23-001", "HP Inc.",
             datetime.date(2023, 6, 15), datetime.date(2026, 6, 15),  # expiring soon
             "3-year HP Care Pack", False),
        ]

        for (code, war_no, vendor, start, end, desc, is_ext) in warranties:
            asset = assets.get(code)
            if not asset:
                continue
            AssetWarranty.objects.get_or_create(
                asset=asset,
                warranty_number=war_no,
                defaults={
                    "vendor_name": vendor,
                    "warranty_start": start,
                    "warranty_end": end,
                    "coverage_description": desc,
                    "is_extended": is_ext,
                    "is_active": end >= datetime.date.today(),
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Insurance policies: {} | Warranties: {}".format(
            len(insurance), len(warranties)
        ))

    # ── Leases ────────────────────────────────────────────────────────────────

    def _seed_leases(self, assets):
        from apps.asset_management.models import LeaseAgreement

        leases = [
            # Office photocopier on operating lease
            ("LS-0001", assets.get("AST-0011"), "Office Photocopier Lease",
             "Ricoh Ghana Ltd", "operating", "active",
             datetime.date(2022, 4, 1), datetime.date(2027, 3, 31), 60,
             Decimal("380"), Decimal("0.0600"),
             Decimal("19_800"), Decimal("19_800")),
            # Head office space lease (operating)
            ("LS-0002", None, "Head Office Lease — 4th Floor",
             "Prime Properties Ghana", "operating", "active",
             datetime.date(2023, 1, 1), datetime.date(2025, 12, 31), 36,
             Decimal("8_500"), Decimal("0.0800"),
             Decimal("272_000"), Decimal("272_000")),
            # Company van on finance lease
            ("LS-0003", assets.get("AST-0007"), "Fleet Van — Finance Lease",
             "SG Leasing Ghana", "finance", "active",
             datetime.date(2023, 3, 1), datetime.date(2028, 2, 28), 60,
             Decimal("2_100"), Decimal("0.0950"),
             Decimal("99_100"), Decimal("99_100")),
        ]

        for (lease_no, asset, desc, lessor, ltype, status,
             comm, end, months, monthly, rate, rou, liability) in leases:
            LeaseAgreement.objects.get_or_create(
                lease_number=lease_no,
                defaults={
                    "asset": asset,
                    "description": desc,
                    "lessor_name": lessor,
                    "lease_type": ltype,
                    "status": status,
                    "commencement_date": comm,
                    "end_date": end,
                    "lease_term_months": months,
                    "monthly_payment": monthly,
                    "discount_rate": rate,
                    "right_of_use_asset_value": rou,
                    "lease_liability": liability,
                    "currency": "USD",
                    "renewal_option": False,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Lease agreements: {}".format(len(leases)))

    # ── Physical audit ────────────────────────────────────────────────────────

    def _seed_audit(self, assets):
        from apps.asset_management.models import AssetAudit, AssetAuditLine
        from core.numbering.service import get_next_number

        if AssetAudit.objects.filter(company_id=COMPANY_ID).exists():
            self.stdout.write("  Audit already seeded, skipping.")
            return

        audit = AssetAudit.objects.create(
            audit_number=get_next_number("AUDIT", COMPANY_ID),
            audit_date=datetime.date(2026, 6, 15),
            location_filter="Head Office",
            status="completed",
            notes="Annual physical verification — Head Office assets",
            company_id=COMPANY_ID,
        )

        lines_data = [
            # (asset_code, finding_status, found_location, expected_location, condition)
            ("AST-0001", "found",   "Head Office - Desk 4A",    "Head Office - Desk 4A",    "good"),
            ("AST-0002", "found",   "Head Office - Desk 3B",    "Head Office - Desk 3B",    "good"),
            ("AST-0003", "found",   "Head Office - Finance Wing","Head Office - Finance Wing","fair"),
            ("AST-0004", "found",   "Head Office - Reception",  "Head Office - Reception",  "good"),
            ("AST-0005", "found",   "Head Office - Board Room", "Head Office - Board Room", "good"),
            ("AST-0008", "found",   "Head Office - Plant Room", "Head Office - Plant Room", "fair"),
            ("AST-0010", "found",   "Server Room - Rack A",     "Server Room - Rack A",     "good"),
            ("AST-0011", "found",   "Head Office - Print Room", "Head Office - Print Room", "poor"),
            # One item missing
            ("AST-0014", "missing", "",                         "Archive Room",              ""),
        ]

        found = 0
        missing = 0
        for (code, finding, found_loc, exp_loc, cond) in lines_data:
            asset = assets.get(code)
            AssetAuditLine.objects.create(
                audit=audit,
                asset=asset,
                scanned_barcode="BC-{}".format(code) if finding == "found" else "",
                expected_location=exp_loc,
                found_location=found_loc,
                finding_status=finding,
                condition=cond,
                company_id=COMPANY_ID,
            )
            if finding == "found":
                found += 1
            else:
                missing += 1

        audit.total_assets_found = found
        audit.total_assets_missing = missing
        audit.total_assets_expected = found + missing
        audit.save(update_fields=["total_assets_found", "total_assets_missing", "total_assets_expected"])

        self.stdout.write("  Audit: {} found, {} missing".format(found, missing))

    # ── Generate depreciation schedules ───────────────────────────────────────

    def _generate_depreciation(self, assets):
        from apps.asset_management.hooks.asset import generate_depreciation_schedule
        from apps.asset_management.models import Asset, AssetDepreciationSchedule

        count = 0
        for asset in Asset.objects.filter(
            status__in=["active", "under_maintenance"],
            is_deleted=False,
            company_id=COMPANY_ID,
        ):
            if not AssetDepreciationSchedule.objects.filter(asset=asset).exists():
                generate_depreciation_schedule(asset)
                count += 1

        total_rows = AssetDepreciationSchedule.objects.filter(company_id=COMPANY_ID).count()
        self.stdout.write(
            "  Depreciation schedules generated for {} assets ({} total rows)".format(count, total_rows)
        )


def _emp_name(emp_id):
    names = {
        _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001"): "Alex Mensah",
        _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002"): "Efua Asante",
        _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000003"): "Kojo Darko",
        _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000004"): "Abena Boateng",
        _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000005"): "Kwame Osei",
    }
    return names.get(emp_id, "") if emp_id else ""
