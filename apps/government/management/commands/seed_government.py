"""Seed command for Government module (§7)."""
import datetime
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Command(BaseCommand):
    help = "Seed Government module: GASB Funds, Tenders, Permits, Service Requests, FOIA, Grants"

    def handle(self, *args, **options):
        from apps.government.models import (
            GASBFund, BudgetaryControl, Tender, TenderEvaluationCriteria, TenderBid,
            Permit, PermitInspection, GrantApplication,
            CitizenServiceRequest, FOIARequest,
        )

        self.stdout.write("Seeding Government module...")

        # ── GASB Funds ──────────────────────────────────────────────────────
        fund_data = [
            {"fund_number": "001", "name": "General Fund", "fund_type": "general",
             "appropriated_budget": 5000000, "encumbered_amount": 1200000,
             "expended_amount": 2800000, "available_balance": 1000000},
            {"fund_number": "210", "name": "Road Maintenance Special Revenue",
             "fund_type": "special_revenue",
             "appropriated_budget": 800000, "encumbered_amount": 150000,
             "expended_amount": 400000, "available_balance": 250000},
            {"fund_number": "310", "name": "Capital Infrastructure Projects",
             "fund_type": "capital_projects",
             "appropriated_budget": 3000000, "encumbered_amount": 600000,
             "expended_amount": 900000, "available_balance": 1500000},
            {"fund_number": "510", "name": "Water Utility Enterprise",
             "fund_type": "enterprise",
             "appropriated_budget": 1200000, "encumbered_amount": 200000,
             "expended_amount": 700000, "available_balance": 300000},
        ]
        funds = {}
        for fd in fund_data:
            f, created = GASBFund.objects.get_or_create(
                fund_number=fd["fund_number"],
                company_id=COMPANY_ID,
                defaults={
                    "name": fd["name"],
                    "fund_type": fd["fund_type"],
                    "fiscal_year": 2026,
                    "appropriated_budget": fd["appropriated_budget"],
                    "encumbered_amount": fd["encumbered_amount"],
                    "expended_amount": fd["expended_amount"],
                    "available_balance": fd["available_balance"],
                    "is_active": True,
                    "company_id": COMPANY_ID,
                }
            )
            funds[fd["fund_number"]] = f
            if created:
                self.stdout.write("  Created fund: {}".format(f))
        self.stdout.write("  {} GASB Funds".format(len(funds)))

        # ── Budgetary Control entries ────────────────────────────────────────
        bc_data = [
            {"entry_type": "encumbrance", "amount": 450000, "description": "Consulting services PO",
             "fund": funds["001"]},
            {"entry_type": "encumbrance", "amount": 180000, "description": "Road resurfacing PO",
             "fund": funds["210"]},
            {"entry_type": "expenditure", "amount": 350000,
             "description": "Software licenses invoice",
             "fund": funds["001"]},
            {"entry_type": "budget_amendment", "amount": 200000,
             "description": "Emergency COVID-19 supplemental appropriation",
             "fund": funds["001"]},
        ]
        bc_count = 0
        for i, bc in enumerate(bc_data, 1):
            entry_num = "BCE-{:04d}".format(i)
            obj, created = BudgetaryControl.objects.get_or_create(
                entry_number=entry_num,
                company_id=COMPANY_ID,
                defaults={
                    "gasb_fund_id": bc["fund"].id,
                    "entry_type": bc["entry_type"],
                    "status": "open",
                    "amount": bc["amount"],
                    "description": bc["description"],
                    "entry_date": datetime.date(2026, 1, 15),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                bc_count += 1
        self.stdout.write("  {} Budgetary Control entries".format(bc_count))

        # ── Tenders ──────────────────────────────────────────────────────────
        tender_data = [
            {
                "tender_number": "TEND-0001",
                "title": "Construction of Municipal Community Centre",
                "description": "Design and construction of a 5,000 sqm community centre in Central Ward",
                "procurement_method": "open",
                "status": "awarded",
                "estimated_value": 2500000,
                "publication_date": datetime.date(2025, 6, 1),
                "submission_deadline": datetime.datetime(2025, 8, 31, 17, 0),
                "award_date": datetime.date(2025, 10, 15),
                "awarded_vendor_name": "BuildRight Construction Ltd",
                "awarded_amount": 2350000,
                "fund": funds["310"],
            },
            {
                "tender_number": "TEND-0002",
                "title": "IT Infrastructure Refresh — City Hall",
                "description": "Supply and installation of network equipment, servers, and workstations",
                "procurement_method": "restricted",
                "status": "evaluation",
                "estimated_value": 350000,
                "publication_date": datetime.date(2026, 1, 10),
                "submission_deadline": datetime.datetime(2026, 3, 31, 17, 0),
                "fund": funds["001"],
            },
            {
                "tender_number": "TEND-0003",
                "title": "Road Resurfacing — District 4",
                "description": "Resurfacing of 12 km of roads in District 4 including drainage works",
                "procurement_method": "open",
                "status": "submissions_open",
                "estimated_value": 650000,
                "publication_date": datetime.date(2026, 2, 1),
                "submission_deadline": datetime.datetime(2026, 4, 30, 17, 0),
                "fund": funds["210"],
            },
            {
                "tender_number": "TEND-0004",
                "title": "Water Meter Replacement Programme",
                "description": "Supply and installation of 5,000 smart water meters",
                "procurement_method": "framework",
                "status": "draft",
                "estimated_value": 480000,
                "fund": funds["510"],
            },
        ]
        tenders = {}
        for td in tender_data:
            t, created = Tender.objects.get_or_create(
                tender_number=td["tender_number"],
                company_id=COMPANY_ID,
                defaults={
                    "title": td["title"],
                    "description": td["description"],
                    "procurement_method": td["procurement_method"],
                    "status": td["status"],
                    "gasb_fund": td["fund"],
                    "estimated_value": td["estimated_value"],
                    "currency": "USD",
                    "publication_date": td.get("publication_date"),
                    "submission_deadline": td.get("submission_deadline"),
                    "award_date": td.get("award_date"),
                    "awarded_vendor_name": td.get("awarded_vendor_name", ""),
                    "awarded_amount": td.get("awarded_amount", 0),
                    "ocds_ocid": "ocds-odum-{}-{}".format(
                        str(COMPANY_ID)[:8], td["tender_number"]),
                    "company_id": COMPANY_ID,
                }
            )
            tenders[td["tender_number"]] = t
            if created:
                self.stdout.write("  Created tender: {}".format(t))
        self.stdout.write("  {} Tenders".format(len(tenders)))

        # Evaluation criteria for the IT tender
        it_tender = tenders["TEND-0002"]
        criteria_data = [
            ("Technical Capability", "Vendor technical expertise and past projects", 40),
            ("Price Competitiveness", "Bid price vs. estimate", 35),
            ("Implementation Timeline", "Proposed delivery schedule", 15),
            ("Local Content", "Percentage of local suppliers and labour", 10),
        ]
        crit_count = 0
        for cname, cdesc, weight in criteria_data:
            _, created = TenderEvaluationCriteria.objects.get_or_create(
                tender=it_tender,
                criterion_name=cname,
                company_id=COMPANY_ID,
                defaults={
                    "description": cdesc,
                    "weight_pct": weight,
                    "max_score": 100,
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                crit_count += 1
        self.stdout.write("  {} Evaluation Criteria for {}".format(crit_count, it_tender))

        # Bids for the IT tender
        vendor_id_1 = uuid.UUID("bbbbbbbb-0001-0001-0001-000000000001")
        vendor_id_2 = uuid.UUID("bbbbbbbb-0001-0001-0001-000000000002")
        bid_data = [
            {"vendor_id": vendor_id_1, "vendor_name": "TechSolutions Ghana Ltd",
             "bid_amount": 325000, "technical_score": 82, "financial_score": 88,
             "total_score": 85, "status": "under_evaluation"},
            {"vendor_id": vendor_id_2, "vendor_name": "InfoBridge Africa",
             "bid_amount": 338000, "technical_score": 91, "financial_score": 75,
             "total_score": 84, "status": "under_evaluation"},
        ]
        bid_count = 0
        for bd in bid_data:
            _, created = TenderBid.objects.get_or_create(
                tender=it_tender,
                vendor_id=bd["vendor_id"],
                company_id=COMPANY_ID,
                defaults={
                    "vendor_name": bd["vendor_name"],
                    "bid_amount": bd["bid_amount"],
                    "submission_date": timezone.make_aware(datetime.datetime(2026, 3, 28, 14, 0)),
                    "status": bd["status"],
                    "technical_score": bd["technical_score"],
                    "financial_score": bd["financial_score"],
                    "total_score": bd["total_score"],
                    "has_tax_clearance": True,
                    "has_company_registration": True,
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                bid_count += 1
        self.stdout.write("  {} Tender Bids".format(bid_count))

        # ── Permits ──────────────────────────────────────────────────────────
        permit_data = [
            {
                "permit_number": "PERM-0001",
                "permit_type": "Building Permit",
                "applicant_name": "Kwame Asante",
                "applicant_email": "kwame.asante@gmail.com",
                "property_address": "45 Independence Avenue, North Ridge, Accra",
                "description": "Construction of 3-storey mixed-use building",
                "status": "issued",
                "application_date": datetime.date(2025, 9, 1),
                "issue_date": datetime.date(2025, 11, 15),
                "expiry_date": datetime.date(2026, 11, 15),
                "fee_amount": 2500,
                "fee_paid": True,
                "inspection_required": True,
                "inspection_passed": True,
                "fund": funds["001"],
            },
            {
                "permit_number": "PERM-0002",
                "permit_type": "Business Operating Licence",
                "applicant_name": "Akosua Mensah Trading",
                "applicant_email": "akosua@amtrading.com",
                "property_address": "12 Market Street, Kumasi Central",
                "description": "Retail trade — general merchandise",
                "status": "approved",
                "application_date": datetime.date(2026, 1, 10),
                "fee_amount": 350,
                "fee_paid": True,
                "inspection_required": False,
                "fund": funds["001"],
            },
            {
                "permit_number": "PERM-0003",
                "permit_type": "Environmental Impact Assessment Permit",
                "applicant_name": "Volta Aggregates Ltd",
                "applicant_email": "env@voltaaggregates.com",
                "property_address": "Quarry Site, Akosombo Road",
                "description": "Quarrying and aggregate extraction",
                "status": "under_review",
                "application_date": datetime.date(2026, 2, 5),
                "review_deadline": datetime.date(2026, 4, 5),
                "fee_amount": 5000,
                "fee_paid": True,
                "inspection_required": True,
                "fund": funds["001"],
            },
            {
                "permit_number": "PERM-0004",
                "permit_type": "Food Handling Permit",
                "applicant_name": "Golden Fork Restaurant",
                "applicant_email": "info@goldenfork.com",
                "property_address": "8 Airport Bypass Road, Accra",
                "description": "Restaurant — dine-in and takeout",
                "status": "rejected",
                "application_date": datetime.date(2025, 12, 1),
                "rejection_reason": "Kitchen facilities do not meet minimum hygiene standards. Reapply after renovation.",
                "fee_amount": 180,
                "fee_paid": True,
                "fund": funds["001"],
            },
        ]
        permits = {}
        for pd in permit_data:
            p, created = Permit.objects.get_or_create(
                permit_number=pd["permit_number"],
                company_id=COMPANY_ID,
                defaults={
                    "permit_type": pd["permit_type"],
                    "applicant_name": pd["applicant_name"],
                    "applicant_email": pd.get("applicant_email", ""),
                    "property_address": pd.get("property_address", ""),
                    "description": pd.get("description", ""),
                    "status": pd["status"],
                    "application_date": pd.get("application_date"),
                    "review_deadline": pd.get("review_deadline"),
                    "issue_date": pd.get("issue_date"),
                    "expiry_date": pd.get("expiry_date"),
                    "fee_amount": pd.get("fee_amount", 0),
                    "fee_paid": pd.get("fee_paid", False),
                    "inspection_required": pd.get("inspection_required", False),
                    "inspection_passed": pd.get("inspection_passed"),
                    "rejection_reason": pd.get("rejection_reason", ""),
                    "gasb_fund": pd.get("fund"),
                    "company_id": COMPANY_ID,
                }
            )
            permits[pd["permit_number"]] = p
            if created:
                self.stdout.write("  Created permit: {}".format(p))
        self.stdout.write("  {} Permits".format(len(permits)))

        # Inspection for the building permit
        _, created = PermitInspection.objects.get_or_create(
            permit=permits["PERM-0001"],
            inspection_type="Structural Inspection",
            company_id=COMPANY_ID,
            defaults={
                "scheduled_date": datetime.date(2025, 10, 20),
                "completed_date": datetime.date(2025, 10, 22),
                "outcome": "passed",
                "inspector_name": "Eng. Kofi Boateng",
                "notes": "Foundations and structural frame meet code requirements.",
                "company_id": COMPANY_ID,
            }
        )
        if created:
            self.stdout.write("  Created permit inspection for PERM-0001")

        # ── Citizen Service Requests ──────────────────────────────────────────
        csr_data = [
            {
                "request_number": "CSR-0001",
                "service_type": "Pothole Repair",
                "description": "Large pothole on Liberation Road near Danquah Circle. Causing vehicle damage.",
                "priority": "high",
                "status": "in_progress",
                "reporter_name": "Ama Acheampong",
                "reporter_email": "ama@email.com",
                "location_address": "Liberation Road, near Danquah Circle, Accra",
                "assigned_department": "Roads & Highways",
                "assigned_to_name": "Yaw Darko",
                "ward": "Okaikoi South",
                "target_resolution_date": datetime.date(2026, 7, 20),
            },
            {
                "request_number": "CSR-0002",
                "service_type": "Broken Street Light",
                "description": "3 street lights out on Cantonments Road from traffic light to roundabout.",
                "priority": "normal",
                "status": "resolved",
                "reporter_name": "Nana Osei",
                "reporter_email": "nana.osei@hotmail.com",
                "location_address": "Cantonments Road, Cantonments, Accra",
                "assigned_department": "Electricity & Lighting",
                "assigned_to_name": "Electricity Team B",
                "ward": "Cantonments",
                "resolved_at": timezone.make_aware(datetime.datetime(2026, 7, 5, 16, 30)),
                "resolution_notes": "Faulty bulbs replaced. All 3 lights restored.",
                "satisfaction_rating": 4,
            },
            {
                "request_number": "CSR-0003",
                "service_type": "Illegal Dumping",
                "description": "Waste dumped on vacant land near residential area causing health hazard.",
                "priority": "high",
                "status": "assigned",
                "reporter_name": "Community Residents Association",
                "reporter_email": "cra.labone@gmail.com",
                "location_address": "Labone, behind Labone JHS",
                "assigned_department": "Environmental Health",
                "assigned_to_name": "Kwesi Antwi",
                "ward": "Labone",
                "target_resolution_date": datetime.date(2026, 7, 16),
            },
            {
                "request_number": "CSR-0004",
                "service_type": "Noise Complaint",
                "description": "Night club playing loud music past midnight disturbing residential neighbours.",
                "priority": "normal",
                "status": "open",
                "reporter_name": "",
                "reporter_email": "",
                "location_address": "Ring Road Central, near Paloma Hotel",
                "assigned_department": "Environmental Health",
                "ward": "Ring Road",
            },
            {
                "request_number": "CSR-0005",
                "service_type": "Water Supply Disruption",
                "description": "No water supply to entire street for 5 days.",
                "priority": "emergency",
                "status": "closed",
                "reporter_name": "Janet Morrison",
                "reporter_email": "janet.m@yahoo.com",
                "location_address": "Adjiringanor Road, East Legon",
                "assigned_department": "Water & Sanitation",
                "ward": "East Legon",
                "resolved_at": timezone.make_aware(datetime.datetime(2026, 6, 28, 11, 0)),
                "resolution_notes": "Pipe burst repaired. Water restored to all properties.",
                "satisfaction_rating": 5,
            },
        ]
        csr_count = 0
        for cd in csr_data:
            _, created = CitizenServiceRequest.objects.get_or_create(
                request_number=cd["request_number"],
                company_id=COMPANY_ID,
                defaults={
                    "service_type": cd["service_type"],
                    "description": cd["description"],
                    "priority": cd.get("priority", "normal"),
                    "status": cd["status"],
                    "reporter_name": cd.get("reporter_name", ""),
                    "reporter_email": cd.get("reporter_email", ""),
                    "location_address": cd.get("location_address", ""),
                    "ward": cd.get("ward", ""),
                    "assigned_department": cd.get("assigned_department", ""),
                    "assigned_to_name": cd.get("assigned_to_name", ""),
                    "target_resolution_date": cd.get("target_resolution_date"),
                    "resolved_at": cd.get("resolved_at"),
                    "resolution_notes": cd.get("resolution_notes", ""),
                    "satisfaction_rating": cd.get("satisfaction_rating"),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                csr_count += 1
        self.stdout.write("  {} Citizen Service Requests".format(csr_count))

        # ── FOIA Requests ─────────────────────────────────────────────────────
        foia_data = [
            {
                "request_number": "FOIA-0001",
                "requester_name": "The Daily Dispatch",
                "requester_email": "newsdesk@dailydispatch.com",
                "requester_organization": "The Daily Dispatch (Newspaper)",
                "description": "Request for all contracts awarded under the Capital Infrastructure Fund in FY2025",
                "records_requested": "Contract documents, bid evaluations, and award letters for all capital projects approved in FY2025 (Fund 310)",
                "status": "fulfilled",
                "received_date": datetime.date(2026, 1, 5),
                "acknowledged_date": datetime.date(2026, 1, 6),
                "due_date": datetime.date(2026, 2, 4),
                "fulfilled_date": datetime.date(2026, 1, 28),
                "fee_waived": True,
                "response_notes": "37 contract documents released. 3 withheld under trade-secrets exemption.",
            },
            {
                "request_number": "FOIA-0002",
                "requester_name": "Citizens for Transparency",
                "requester_email": "info@cft-ghana.org",
                "requester_organization": "Citizens for Transparency NGO",
                "description": "All communications related to the Community Centre tender TEND-0001",
                "records_requested": "Emails, meeting minutes, evaluation scoresheets for Tender TEND-0001",
                "status": "in_review",
                "received_date": datetime.date(2026, 3, 1),
                "acknowledged_date": datetime.date(2026, 3, 2),
                "due_date": datetime.date(2026, 4, 1),
                "is_sensitive": True,
            },
            {
                "request_number": "FOIA-0003",
                "requester_name": "Kofi Appiah",
                "requester_email": "kofi.appiah@personal.com",
                "description": "Employee salary records for all senior staff",
                "records_requested": "Salary and benefits records for Director-level and above positions",
                "status": "denied",
                "received_date": datetime.date(2026, 2, 14),
                "due_date": datetime.date(2026, 3, 16),
                "denial_reason": "Request denied under privacy exemption. Salary information for identified individuals is exempt from public disclosure.",
                "denial_exemption": "Personal Privacy Exemption — Section 12(b)",
                "fee_waived": False,
                "fee_amount": 25,
            },
        ]
        foia_count = 0
        for fd in foia_data:
            _, created = FOIARequest.objects.get_or_create(
                request_number=fd["request_number"],
                company_id=COMPANY_ID,
                defaults={
                    "requester_name": fd["requester_name"],
                    "requester_email": fd.get("requester_email", ""),
                    "requester_organization": fd.get("requester_organization", ""),
                    "description": fd["description"],
                    "records_requested": fd["records_requested"],
                    "status": fd["status"],
                    "received_date": fd["received_date"],
                    "acknowledged_date": fd.get("acknowledged_date"),
                    "due_date": fd.get("due_date"),
                    "fulfilled_date": fd.get("fulfilled_date"),
                    "denial_reason": fd.get("denial_reason", ""),
                    "denial_exemption": fd.get("denial_exemption", ""),
                    "fee_waived": fd.get("fee_waived", False),
                    "fee_amount": fd.get("fee_amount", 0),
                    "is_sensitive": fd.get("is_sensitive", False),
                    "response_notes": fd.get("response_notes", ""),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                foia_count += 1
        self.stdout.write("  {} FOIA Requests".format(foia_count))

        # ── Grant Applications ────────────────────────────────────────────────
        grant_data = [
            {
                "grant_number": "GRT-001",
                "title": "Urban Mobility Infrastructure Grant — World Bank",
                "description": "Grant to fund public transport infrastructure improvements in Accra Metropolitan Area",
                "grant_type": "received",
                "status": "active",
                "counterpart_name": "World Bank Urban Development Fund",
                "counterpart_contact": "urbangrants@worldbank.org",
                "requested_amount": 5000000,
                "approved_amount": 4500000,
                "disbursed_amount": 1800000,
                "currency": "USD",
                "application_date": datetime.date(2024, 6, 1),
                "award_date": datetime.date(2024, 10, 1),
                "start_date": datetime.date(2025, 1, 1),
                "end_date": datetime.date(2027, 12, 31),
                "fund": funds["310"],
                "reporting_requirements": "Quarterly progress reports; Annual financial audit by approved auditor",
                "program_officer_name": "Abena Pokuaa",
            },
            {
                "grant_number": "GRT-002",
                "title": "Community Water Access Programme Grant",
                "description": "Grant to extend piped water access to 12 peri-urban communities",
                "grant_type": "received",
                "status": "approved",
                "counterpart_name": "USAID Water & Sanitation",
                "counterpart_contact": "wash@usaid.gov",
                "requested_amount": 1200000,
                "approved_amount": 1000000,
                "disbursed_amount": 0,
                "currency": "USD",
                "application_date": datetime.date(2025, 9, 1),
                "award_date": datetime.date(2026, 1, 15),
                "start_date": datetime.date(2026, 3, 1),
                "end_date": datetime.date(2028, 2, 28),
                "fund": funds["510"],
                "program_officer_name": "Kweku Asante",
            },
            {
                "grant_number": "GRT-003",
                "title": "Youth Skills Development Sub-Grant",
                "description": "Sub-grant issued to Bright Futures NGO for vocational training programme",
                "grant_type": "issued",
                "status": "active",
                "counterpart_name": "Bright Futures NGO",
                "counterpart_contact": "director@brightfutures.org.gh",
                "requested_amount": 80000,
                "approved_amount": 75000,
                "disbursed_amount": 37500,
                "currency": "USD",
                "application_date": datetime.date(2025, 11, 1),
                "award_date": datetime.date(2026, 1, 10),
                "start_date": datetime.date(2026, 2, 1),
                "end_date": datetime.date(2026, 12, 31),
                "fund": funds["001"],
                "reporting_requirements": "Monthly activity reports and receipts",
                "program_officer_name": "Esi Yankah",
            },
        ]
        grant_count = 0
        for gd in grant_data:
            _, created = GrantApplication.objects.get_or_create(
                grant_number=gd["grant_number"],
                company_id=COMPANY_ID,
                defaults={
                    "title": gd["title"],
                    "description": gd["description"],
                    "grant_type": gd["grant_type"],
                    "status": gd["status"],
                    "gasb_fund": gd.get("fund"),
                    "counterpart_name": gd.get("counterpart_name", ""),
                    "counterpart_contact": gd.get("counterpart_contact", ""),
                    "requested_amount": gd["requested_amount"],
                    "approved_amount": gd["approved_amount"],
                    "disbursed_amount": gd["disbursed_amount"],
                    "currency": gd.get("currency", "USD"),
                    "application_date": gd.get("application_date"),
                    "award_date": gd.get("award_date"),
                    "start_date": gd.get("start_date"),
                    "end_date": gd.get("end_date"),
                    "reporting_requirements": gd.get("reporting_requirements", ""),
                    "program_officer_name": gd.get("program_officer_name", ""),
                    "company_id": COMPANY_ID,
                }
            )
            if created:
                grant_count += 1
        self.stdout.write("  {} Grant Applications".format(grant_count))

        self.stdout.write(self.style.SUCCESS(
            "\nGovernment seed complete: {} funds, {} tenders, {} permits, "
            "{} CSRs, {} FOIA requests, {} grants".format(
                len(funds), len(tenders), len(permits), csr_count, foia_count, grant_count
            )
        ))
