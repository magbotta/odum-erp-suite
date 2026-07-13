"""
Management command: seed realistic CRM dummy data.
Usage: python manage.py seed_crm [--clear]
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

# ── Seed data tables ──────────────────────────────────────────────────────────

TERRITORIES = [
    ("West Coast", "geographic"),
    ("East Coast", "geographic"),
    ("EMEA", "geographic"),
    ("APAC", "geographic"),
    ("Enterprise", "vertical"),
    ("Mid-Market", "vertical"),
]

CAMPAIGNS = [
    ("Q3 2026 Webinar Series", "webinar", "google", "cpc", "q3-webinar"),
    ("LinkedIn Lead Gen — Manufacturing", "social", "linkedin", "paid-social", "manufacturing-2026"),
    ("ERP Comparison Guide", "content", "organic", "seo", "erp-guide"),
    ("Q4 Email Nurture", "email", "newsletter", "email", "q4-nurture"),
    ("Trade Show — APAC Summit", "event", "event", "offline", "apac-summit"),
]

ACCOUNTS = [
    ("Acme Corporation", "manufacturing", "https://acme.example.com", "+1-415-555-0100", 850, 4_200_000),
    ("Blue Ocean Logistics", "retail", "https://blueocean.example.com", "+1-212-555-0200", 230, 9_100_000),
    ("Cascade Health Systems", "healthcare", "https://cascadehealth.example.com", "+1-503-555-0300", 1200, 15_500_000),
    ("Delta Financial Group", "finance", "https://deltafinancial.example.com", "+44-20-7946-0400", 450, 28_000_000),
    ("Evergreen Tech Solutions", "technology", "https://evergreen.example.com", "+1-206-555-0500", 180, 6_750_000),
    ("Frontier Education Trust", "education", "https://frontier-edu.example.com", "+1-312-555-0600", 95, 3_200_000),
    ("Granite Manufacturing Co.", "manufacturing", "https://granite-mfg.example.com", "+1-713-555-0700", 340, 11_800_000),
    ("Harbor Retail Group", "retail", "https://harbor-retail.example.com", "+1-305-555-0800", 620, 22_400_000),
    ("Insight Analytics Inc.", "technology", "https://insight-analytics.example.com", "+1-415-555-0900", 75, 4_900_000),
    ("Jasper Government Services", "government", "https://jasper-gov.example.com", "+1-202-555-1000", 160, 8_600_000),
]

CONTACTS = [
    # (first, last, title, department, account_idx)
    ("Sarah", "Chen", "CFO", "Finance", 0),
    ("Marcus", "Osei", "IT Director", "Technology", 0),
    ("Priya", "Nair", "VP Operations", "Operations", 1),
    ("James", "Thornton", "CEO", "Executive", 1),
    ("Amara", "Diallo", "Procurement Manager", "Procurement", 2),
    ("Elena", "Vasquez", "CTO", "Technology", 2),
    ("David", "Park", "Finance Director", "Finance", 3),
    ("Fatima", "Al-Rashid", "COO", "Operations", 3),
    ("Liam", "Murphy", "Head of IT", "Technology", 4),
    ("Yuki", "Tanaka", "VP Sales", "Sales", 4),
    ("Kofi", "Mensah", "Principal", "Administration", 5),
    ("Aisha", "Ibrahim", "Finance Manager", "Finance", 5),
    ("Robert", "Gallagher", "Plant Manager", "Operations", 6),
    ("Mei", "Lin", "Purchasing Director", "Procurement", 6),
    ("Carlos", "Reyes", "Store Operations VP", "Operations", 7),
    ("Ingrid", "Svensson", "CFO", "Finance", 7),
    ("Thomas", "Adeyemi", "CTO", "Technology", 8),
    ("Nkechi", "Okafor", "CEO", "Executive", 8),
    ("William", "Hayes", "City Manager", "Administration", 9),
    ("Sophia", "Petrov", "IT Manager", "Technology", 9),
]

LEAD_DATA = [
    ("SkyNet Retail — ERP Upgrade", "Jordan Rivers", "jordan@skynet-retail.example.com", "+1-404-555-2001", "SkyNet Retail", "referral", 60),
    ("Mountain View Schools — SIS", "Patricia Owens", "p.owens@mvschools.example.com", "+1-720-555-2002", "Mountain View Schools", "website", 35),
    ("Bright Future Microfinance", "Emmanuel Asante", "e.asante@brightfuture.example.com", "+233-30-555-2003", "Bright Future MFI", "event", 45),
    ("Pacific Coast Distributors", "Hana Yamamoto", "h.yamamoto@pcd.example.com", "+81-3-555-2004", "Pacific Coast Distributors", "cold_outreach", 20),
    ("Meridian Hospital Group", "Dr. Alex Nwosu", "a.nwosu@meridian.example.com", "+1-312-555-2005", "Meridian Hospital Group", "referral", 70),
    ("Northern Lights Energy", "Bjorn Larsen", "b.larsen@nlenergy.example.com", "+47-23-555-2006", "Northern Lights Energy", "advertisement", 25),
    ("Coastal Farms Co-op", "Maria Santos", "m.santos@coastalfarms.example.com", "+1-831-555-2007", "Coastal Farms Co-op", "website", 30),
    ("Premier Legal Partners", "Christine Abbot", "c.abbot@premierlegal.example.com", "+1-617-555-2008", "Premier Legal Partners", "referral", 55),
    ("Atlas Telecom", "Rajesh Patel", "r.patel@atlastelecom.example.com", "+91-22-555-2009", "Atlas Telecom", "cold_outreach", 15),
    ("Green Valley NPO", "Akinwale Bello", "a.bello@greenvalley.example.com", "+234-1-555-2010", "Green Valley NPO", "event", 40),
    ("TechStart Ventures", "Samantha Ko", "s.ko@techstart.example.com", "+1-628-555-2011", "TechStart Ventures", "website", 20),
    ("Westfield Manufacturing", "Derek Hughes", "d.hughes@westfield-mfg.example.com", "+1-216-555-2012", "Westfield Manufacturing", "referral", 65),
]

PIPELINE_STAGES = [
    # (name, sequence, probability, is_won, is_lost)
    ("Prospecting", 1, 10, False, False),
    ("Qualification", 2, 20, False, False),
    ("Needs Analysis", 3, 35, False, False),
    ("Value Proposition", 4, 50, False, False),
    ("Decision Making", 5, 70, False, False),
    ("Contract Sent", 6, 85, False, False),
    ("Closed Won", 7, 100, True, False),
    ("Closed Lost", 8, 0, False, True),
]

OPPORTUNITY_NAMES = [
    ("Acme ERP Full Suite Rollout", 0, 4, 145_000),
    ("Blue Ocean WMS + Accounting", 1, 2, 89_000),
    ("Cascade HIS Phase 1", 2, 5, 220_000),
    ("Delta Financial CRM + Reporting", 3, 3, 78_000),
    ("Evergreen Dev Platform License", 4, 1, 52_000),
    ("Frontier SIS Implementation", 5, 4, 67_000),
    ("Granite MRP Upgrade", 6, 5, 112_000),
    ("Harbor POS Rollout — 40 Stores", 7, 6, 188_000),
    ("Insight Analytics Add-On", 8, 2, 31_000),
    ("Jasper Gov Suite Contract", 9, 3, 295_000),
    ("SkyNet Retail Phase 2 Upsell", 0, 4, 44_000),
    ("Mountain View HR + Payroll", 1, 1, 38_000),
]

CASE_SUBJECTS = [
    ("Login SSO fails after password reset", "high"),
    ("Report export producing blank PDF", "medium"),
    ("Invoice total rounding error on GBP", "high"),
    ("Email notifications not sending", "medium"),
    ("Bulk import stalls at 500 rows", "low"),
    ("Dashboard widgets not loading for Sales Rep role", "medium"),
    ("Missing stock ledger entries after GRN submit", "critical"),
    ("Date picker shows wrong timezone in APAC", "low"),
    ("IBAN validation rejects valid DE accounts", "medium"),
    ("Payslip PDF missing gross pay line", "high"),
]

COMPETITORS = [
    ("Odoo", "https://odoo.com", "Large module ecosystem, low cost", "Enterprise license required for key modules"),
    ("ERPNext / Frappe", "https://erpnext.com", "Fully open source, active community", "Steeper learning curve, smaller ecosystem"),
    ("Salesforce", "https://salesforce.com", "Best-in-class CRM depth, huge ecosystem", "Expensive, no self-host, not a full ERP"),
    ("Microsoft Dynamics 365", "https://dynamics.microsoft.com", "Deep Microsoft 365 integration", "High cost, complex implementation"),
    ("SAP Business One", "https://sap.com", "Enterprise brand recognition", "Very expensive, rigid customisation"),
]

ACTIVITY_DATA = [
    ("call", "Intro call — discussed pain points with current ERP"),
    ("email", "Sent product overview deck and pricing matrix"),
    ("meeting", "On-site demo with IT and Finance stakeholders"),
    ("call", "Follow-up: answered questions on migration timeline"),
    ("task", "Prepare custom ROI analysis for CFO review"),
    ("note", "Champion is the CFO — budget approved in Q3"),
    ("meeting", "Technical deep-dive with IT team"),
    ("email", "Sent references from similar-size clients"),
    ("call", "Negotiation call — requested volume discount"),
    ("task", "Loop in implementation partner for scoping"),
]


class Command(BaseCommand):
    help = "Seed realistic CRM dummy data across all 13 entities."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing CRM data before seeding")

    def handle(self, *args, **options):
        from apps.crm.models import (
            Account, Activity, Campaign, Case, Competitor, Contact,
            Lead, Opportunity, OpportunityCompetitor, OpportunityTeamMember,
            Pipeline, PipelineStage, Quota, Quote, QuoteItem, Territory,
        )

        if options["clear"]:
            self.stdout.write("  Clearing existing CRM data…")
            for Model in [
                OpportunityTeamMember, OpportunityCompetitor, QuoteItem, Quote,
                Case, Activity, Opportunity, Lead, Contact, Account,
                Competitor, PipelineStage, Pipeline, Quota, Campaign, Territory,
            ]:
                Model.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Cleared."))

        admin = User.objects.filter(is_superuser=True).first()
        users = list(User.objects.all()[:5]) or [admin]

        today = date.today()

        # 1. Territories
        self.stdout.write("  Seeding territories…")
        terr_objs = []
        for name, ttype in TERRITORIES:
            t, _ = Territory.objects.get_or_create(name=name, defaults={"territory_type": ttype})
            terr_objs.append(t)

        # 2. Campaigns
        self.stdout.write("  Seeding campaigns…")
        camp_objs = []
        statuses = ["active", "active", "completed", "draft", "completed"]
        for i, (name, ctype, src, med, camp) in enumerate(CAMPAIGNS):
            c, _ = Campaign.objects.get_or_create(name=name, defaults={
                "campaign_type": ctype,
                "status": statuses[i],
                "utm_source": src,
                "utm_medium": med,
                "utm_campaign": camp,
                "start_date": today - timedelta(days=random.randint(30, 120)),
                "budget": Decimal(str(random.randint(5, 50) * 1000)),
                "expected_revenue": Decimal(str(random.randint(50, 500) * 1000)),
                "owner": admin,
            })
            camp_objs.append(c)

        # 3. Competitors
        self.stdout.write("  Seeding competitors…")
        comp_objs = []
        for name, website, strengths, weaknesses in COMPETITORS:
            c, _ = Competitor.objects.get_or_create(name=name, defaults={
                "website": website,
                "strengths": strengths,
                "weaknesses": weaknesses,
            })
            comp_objs.append(c)

        # 4. Accounts
        self.stdout.write("  Seeding accounts…")
        acct_objs = []
        for i, (name, industry, website, phone, emp_count, revenue) in enumerate(ACCOUNTS):
            a, _ = Account.objects.get_or_create(name=name, defaults={
                "industry": industry,
                "website": website,
                "phone": phone,
                "employee_count": emp_count,
                "annual_revenue": Decimal(str(revenue)),
                "territory": random.choice(terr_objs),
                "owner": random.choice(users),
            })
            acct_objs.append(a)

        # 5. Contacts
        self.stdout.write("  Seeding contacts…")
        contact_objs = []
        sources = ["website", "referral", "cold_outreach", "event", "advertisement", "other"]
        for first, last, title, dept, acct_idx in CONTACTS:
            email = f"{first.lower()}.{last.lower()}@{acct_objs[acct_idx].name.lower().replace(' ', '').replace('.', '')}.example.com"
            c, _ = Contact.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "title": title,
                    "department": dept,
                    "account": acct_objs[acct_idx],
                    "lead_source": random.choice(sources),
                    "territory": random.choice(terr_objs),
                    "owner": random.choice(users),
                },
            )
            contact_objs.append(c)

        # 6. Pipeline + Stages
        self.stdout.write("  Seeding pipeline…")
        pipeline, _ = Pipeline.objects.get_or_create(
            name="Enterprise Sales",
            defaults={"description": "Main enterprise pipeline", "is_default": True},
        )
        stage_objs = []
        for name, seq, prob, is_won, is_lost in PIPELINE_STAGES:
            s, _ = PipelineStage.objects.get_or_create(
                pipeline=pipeline, name=name,
                defaults={"sequence": seq, "probability": prob, "is_won": is_won, "is_lost": is_lost},
            )
            stage_objs.append(s)

        # Keep open stages (not won/lost) for seeding open opps
        open_stages = [s for s in stage_objs if not s.is_won and not s.is_lost]
        won_stage = next((s for s in stage_objs if s.is_won), None)
        lost_stage = next((s for s in stage_objs if s.is_lost), None)

        # 7. Leads
        self.stdout.write("  Seeding leads…")
        lead_objs = []
        lead_statuses = ["new", "working", "working", "nurturing", "converted", "disqualified", "new", "working", "nurturing", "working", "new", "working"]
        for i, (title, contact_name, email, phone, company, source, score) in enumerate(LEAD_DATA):
            status = lead_statuses[i]
            l, _ = Lead.objects.get_or_create(email=email, defaults={
                "title": title,
                "contact_name": contact_name,
                "phone": phone,
                "company": company,
                "lead_source": source,
                "status": status,
                "score": score,
                "campaign": random.choice(camp_objs) if random.random() > 0.4 else None,
                "territory": random.choice(terr_objs),
                "assigned_to": random.choice(users),
            })
            lead_objs.append(l)

        # 8. Opportunities
        self.stdout.write("  Seeding opportunities…")
        opp_objs = []
        for i, (name, acct_idx, stage_idx, amount) in enumerate(OPPORTUNITY_NAMES):
            stage_idx = min(stage_idx, len(open_stages) - 1)
            stage = open_stages[stage_idx]
            close_days = random.randint(15, 90)
            forecast_map = {10: "pipeline", 20: "pipeline", 35: "best_case", 50: "best_case", 70: "commit", 85: "commit"}
            forecast = forecast_map.get(stage.probability, "pipeline")
            o, _ = Opportunity.objects.get_or_create(name=name, defaults={
                "account": acct_objs[acct_idx],
                "primary_contact": contact_objs[acct_idx * 2] if acct_idx * 2 < len(contact_objs) else None,
                "pipeline": pipeline,
                "stage": stage,
                "amount": Decimal(str(amount)),
                "currency": "USD",
                "probability": stage.probability,
                "expected_close_date": today + timedelta(days=close_days),
                "forecast_category": forecast,
                "territory": random.choice(terr_objs),
                "assigned_to": random.choice(users),
                "lead": lead_objs[i] if i < len(lead_objs) else None,
            })
            opp_objs.append(o)
            # Link 1-2 competitors
            for comp in random.sample(comp_objs, k=random.randint(1, 2)):
                OpportunityCompetitor.objects.get_or_create(opportunity=o, competitor=comp)

        # 2 closed-won opps
        won_data = [
            ("Acme Phase 0 — Core License", 0, 58_000),
            ("Blue Ocean Inventory Module", 1, 34_500),
        ]
        for name, acct_idx, amount in won_data:
            o, _ = Opportunity.objects.get_or_create(name=name, defaults={
                "account": acct_objs[acct_idx],
                "pipeline": pipeline,
                "stage": won_stage,
                "amount": Decimal(str(amount)),
                "probability": 100,
                "forecast_category": "closed_won",
                "win_reason": "Best value + open-source flexibility",
                "closed_at": timezone.now() - timedelta(days=random.randint(5, 30)),
                "assigned_to": random.choice(users),
            })
            opp_objs.append(o)

        # 1 closed-lost opp
        o, _ = Opportunity.objects.get_or_create(name="Meridian Hospital — Initial Bid", defaults={
            "account": acct_objs[2],
            "pipeline": pipeline,
            "stage": lost_stage,
            "amount": Decimal("95000"),
            "probability": 0,
            "forecast_category": "closed_lost",
            "loss_reason": "Went with Microsoft Dynamics due to existing EA agreement",
            "closed_at": timezone.now() - timedelta(days=random.randint(10, 45)),
            "assigned_to": random.choice(users),
        })
        opp_objs.append(o)

        # Team members on top 3 opps
        if len(users) > 1:
            for opp in opp_objs[:3]:
                OpportunityTeamMember.objects.get_or_create(
                    opportunity=opp, user=random.choice(users),
                    defaults={"role": "Solutions Engineer", "credit_split": 20},
                )

        # 9. Activities
        self.stdout.write("  Seeding activities…")
        act_statuses = ["done", "done", "done", "open", "open", "done", "done", "open", "done", "open"]
        for i, (atype, subject) in enumerate(ACTIVITY_DATA):
            opp = opp_objs[i % len(opp_objs)]
            status = act_statuses[i]
            done_at = timezone.now() - timedelta(days=random.randint(1, 20)) if status == "done" else None
            Activity.objects.get_or_create(
                subject=subject,
                defaults={
                    "activity_type": atype,
                    "status": status,
                    "done_at": done_at,
                    "opportunity": opp,
                    "account": opp.account,
                    "contact": opp.primary_contact,
                    "assigned_to": random.choice(users),
                    "due_date": timezone.now() + timedelta(days=random.randint(1, 14)) if status == "open" else None,
                    "duration_minutes": random.choice([15, 30, 45, 60, 90]) if atype in ("call", "meeting") else None,
                },
            )

        # 10. Cases
        self.stdout.write("  Seeding cases…")
        case_statuses = ["closed", "resolved", "open", "escalated", "open", "closed", "resolved", "open", "open", "closed"]
        for i, (subject, priority) in enumerate(CASE_SUBJECTS):
            status = case_statuses[i]
            acct = acct_objs[i % len(acct_objs)]
            contact = contact_objs[i % len(contact_objs)]
            resolved_at = timezone.now() - timedelta(days=random.randint(1, 10)) if status in ("resolved", "closed") else None
            closed_at = timezone.now() - timedelta(days=random.randint(0, 5)) if status == "closed" else None
            escalated_at = timezone.now() - timedelta(days=random.randint(1, 3)) if status == "escalated" else None
            Case.objects.get_or_create(
                subject=subject,
                defaults={
                    "priority": priority,
                    "status": status,
                    "account": acct,
                    "contact": contact,
                    "opportunity": random.choice(opp_objs) if random.random() > 0.5 else None,
                    "sla_hours": {"low": 48, "medium": 24, "high": 8, "critical": 2}[priority],
                    "sla_breached": status == "escalated" and random.random() > 0.5,
                    "assigned_to": random.choice(users),
                    "resolved_at": resolved_at,
                    "closed_at": closed_at,
                    "escalated_at": escalated_at,
                    "resolution_notes": "Issue reproduced and patched in v1.2.1." if resolved_at else "",
                },
            )

        # 11. Quotes
        self.stdout.write("  Seeding quotes…")
        quote_data = [
            (opp_objs[0], "Accepted", 1, 145_000),
            (opp_objs[1], "Sent", 1, 89_000),
            (opp_objs[2], "Draft", 1, 220_000),
            (opp_objs[3], "Rejected", 1, 78_000),
            (opp_objs[4], "Draft", 1, 52_000),
        ]
        q_status_map = {"Draft": "draft", "Sent": "sent", "Accepted": "accepted", "Rejected": "rejected"}
        for i, (opp, q_status, _, amount) in enumerate(quote_data):
            q_num = f"QT-2026-{str(i+1).zfill(4)}"
            sent_at = timezone.now() - timedelta(days=random.randint(2, 15)) if q_status in ("Sent", "Accepted", "Rejected") else None
            accepted_at = timezone.now() - timedelta(days=random.randint(1, 5)) if q_status == "Accepted" else None
            rejected_at = timezone.now() - timedelta(days=random.randint(1, 5)) if q_status == "Rejected" else None
            subtotal = Decimal(str(amount))
            tax = (subtotal * Decimal("0.1")).quantize(Decimal("0.01"))
            grand = subtotal + tax
            quote, created = Quote.objects.get_or_create(quote_number=q_num, defaults={
                "opportunity": opp,
                "account": opp.account,
                "contact": opp.primary_contact,
                "status": q_status_map[q_status],
                "valid_until": today + timedelta(days=30),
                "currency": "USD",
                "subtotal": subtotal,
                "tax_amount": tax,
                "grand_total": grand,
                "assigned_to": random.choice(users),
                "sent_at": sent_at,
                "accepted_at": accepted_at,
                "rejected_at": rejected_at,
                "terms_and_conditions": "Net 30. Annual license. Includes first-year support.",
            })
            if created:
                QuoteItem.objects.create(
                    quote=quote,
                    description=f"Odum ERP Suite — {opp.name} Annual License",
                    quantity=Decimal("1"),
                    unit_price=subtotal,
                    discount_pct=Decimal("0"),
                    line_total=subtotal,
                )
                QuoteItem.objects.create(
                    quote=quote,
                    description="Implementation & Onboarding (Year 1)",
                    quantity=Decimal("1"),
                    unit_price=Decimal(str(int(amount * 0.15))),
                    discount_pct=Decimal("0"),
                    line_total=Decimal(str(int(amount * 0.15))),
                )

        # 12. Quotas
        self.stdout.write("  Seeding quotas…")
        q_start = date(today.year, 7, 1)
        q_end = date(today.year, 9, 30)
        for user in users[:3]:
            Quota.objects.get_or_create(
                user=user,
                period_start=q_start,
                defaults={
                    "period": "quarterly",
                    "period_end": q_end,
                    "target_amount": Decimal(str(random.randint(150, 400) * 1000)),
                    "currency": "USD",
                    "territory": random.choice(terr_objs),
                },
            )

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ CRM seed complete:\n"
            f"    {Territory.objects.count()} territories\n"
            f"    {Campaign.objects.count()} campaigns\n"
            f"    {Competitor.objects.count()} competitors\n"
            f"    {Account.objects.count()} accounts\n"
            f"    {Contact.objects.count()} contacts\n"
            f"    {Pipeline.objects.count()} pipeline(s), {PipelineStage.objects.count()} stages\n"
            f"    {Lead.objects.count()} leads\n"
            f"    {Opportunity.objects.count()} opportunities\n"
            f"    {Activity.objects.count()} activities\n"
            f"    {Case.objects.count()} cases\n"
            f"    {Quote.objects.count()} quotes  ({QuoteItem.objects.count()} line items)\n"
            f"    {Quota.objects.count()} quotas\n"
        ))
