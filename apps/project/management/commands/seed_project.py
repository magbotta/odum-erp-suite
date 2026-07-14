"""Seed Project Management demo data (§6.6)."""
from __future__ import annotations

import datetime
import uuid as _uuid

from django.core.management.base import BaseCommand

COMPANY_ID = _uuid.UUID("00000000-0000-0000-0000-000000000001")

# Stable placeholder UUIDs (cross-app soft refs — same as seed_payroll.py)
EMP_ALEX  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
EMP_EFUA  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000002")
EMP_KOJO  = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000003")
EMP_ABENA = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000004")
EMP_KWAME = _uuid.UUID("aaaaaaaa-0001-0001-0001-000000000005")

CUSTOMER_TECHCORP = _uuid.UUID("cccccccc-0001-0001-0001-000000000001")
CUSTOMER_RETAILCO = _uuid.UUID("cccccccc-0001-0001-0001-000000000002")


class Command(BaseCommand):
    help = "Seed Project Management demo data"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Project Management data...")
        templates = self._seed_templates()
        projects = self._seed_projects(templates)
        self._seed_members(projects)
        self._seed_tasks(projects)
        self._seed_milestones(projects)
        self._seed_billing_rules(projects)
        self._seed_risks_issues(projects)
        self._seed_timesheets(projects)
        self.stdout.write(self.style.SUCCESS("Project Management seed complete."))

    # ── Templates ─────────────────────────────────────────────────────────────

    def _seed_templates(self):
        from apps.project.models import ProjectTemplate, ProjectTemplateTask

        tmpl1, _ = ProjectTemplate.objects.get_or_create(
            name="Website Development",
            defaults={
                "description": "Standard website build — discovery through launch",
                "estimated_days": 60,
                "default_billing_type": "time_and_material",
                "company_id": COMPANY_ID,
            },
        )
        tasks = [
            ("Discovery & Requirements", 0, 5, 20),
            ("UX / Wireframes",          5, 10, 40),
            ("Design & Assets",         15, 8,  32),
            ("Frontend Development",    23, 15, 120),
            ("Backend / CMS Setup",     23, 12, 80),
            ("QA & Testing",            38, 8,  40),
            ("Launch & Handover",       46, 5,  20),
        ]
        for i, (title, offset, duration, hours) in enumerate(tasks):
            ProjectTemplateTask.objects.get_or_create(
                template=tmpl1,
                title=title,
                defaults={
                    "sequence": i + 1,
                    "day_offset": offset,
                    "duration_days": duration,
                    "estimated_hours": hours,
                    "company_id": COMPANY_ID,
                },
            )

        tmpl2, _ = ProjectTemplate.objects.get_or_create(
            name="ERP Implementation",
            defaults={
                "description": "End-to-end ERP rollout — assessment through go-live",
                "estimated_days": 120,
                "default_billing_type": "milestone",
                "company_id": COMPANY_ID,
            },
        )
        tasks2 = [
            ("As-Is Assessment",        0,  10, 40),
            ("Gap Analysis & Design",  10,  15, 60),
            ("Configuration",          25,  30, 200),
            ("Data Migration",         45,  20, 80),
            ("User Acceptance Testing",65,  15, 60),
            ("Training",               80,  10, 40),
            ("Go-Live Support",        90,  10, 60),
            ("Hypercare",             100,  20, 40),
        ]
        for i, (title, offset, duration, hours) in enumerate(tasks2):
            ProjectTemplateTask.objects.get_or_create(
                template=tmpl2,
                title=title,
                defaults={
                    "sequence": i + 1,
                    "day_offset": offset,
                    "duration_days": duration,
                    "estimated_hours": hours,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Templates: 2")
        return {"website_dev": tmpl1, "erp_impl": tmpl2}

    # ── Projects ──────────────────────────────────────────────────────────────

    def _seed_projects(self, templates):
        from apps.project.models import Project

        p1, _ = Project.objects.get_or_create(
            project_code="PRJ-001",
            defaults={
                "project_name": "TechCorp Website Redesign",
                "status": Project.Status.ACTIVE,
                "billing_type": Project.BillingType.TIME_AND_MATERIAL,
                "description": "Complete rebrand and responsive website rebuild for TechCorp.",
                "start_date": datetime.date(2026, 1, 15),
                "expected_end_date": datetime.date(2026, 3, 31),
                "is_billable": True,
                "budget": 45000,
                "currency": "USD",
                "customer_id": CUSTOMER_TECHCORP,
                "customer_name": "TechCorp Ltd",
                "project_manager_id": EMP_ALEX,
                "project_manager_name": "Alex Mensah",
                "template": templates["website_dev"],
                "percent_complete": 45,
                "company_id": COMPANY_ID,
            },
        )

        p2, _ = Project.objects.get_or_create(
            project_code="PRJ-002",
            defaults={
                "project_name": "RetailCo ERP Rollout",
                "status": Project.Status.ACTIVE,
                "billing_type": Project.BillingType.MILESTONE,
                "description": "Full Odum ERP implementation for RetailCo's 12 branches.",
                "start_date": datetime.date(2026, 2, 1),
                "expected_end_date": datetime.date(2026, 7, 31),
                "is_billable": True,
                "budget": 180000,
                "currency": "USD",
                "customer_id": CUSTOMER_RETAILCO,
                "customer_name": "RetailCo Ghana",
                "project_manager_id": EMP_EFUA,
                "project_manager_name": "Efua Asante",
                "template": templates["erp_impl"],
                "percent_complete": 25,
                "company_id": COMPANY_ID,
            },
        )

        p3, _ = Project.objects.get_or_create(
            project_code="PRJ-003",
            defaults={
                "project_name": "Internal HR System Upgrade",
                "status": Project.Status.PLANNING,
                "billing_type": Project.BillingType.NON_BILLABLE,
                "description": "Internal upgrade of HR modules and self-service portal.",
                "start_date": datetime.date(2026, 4, 1),
                "expected_end_date": datetime.date(2026, 6, 30),
                "is_billable": False,
                "budget": 12000,
                "currency": "USD",
                "project_manager_id": EMP_KOJO,
                "project_manager_name": "Kojo Darko",
                "percent_complete": 0,
                "company_id": COMPANY_ID,
            },
        )

        self.stdout.write("  Projects: 3")
        return {"techcorp": p1, "retailco": p2, "internal_hr": p3}

    # ── Members ───────────────────────────────────────────────────────────────

    def _seed_members(self, projects):
        from apps.project.models import ProjectMember

        members = [
            # TechCorp
            (projects["techcorp"], EMP_ALEX,  "Alex Mensah",  "manager",    120, 85),
            (projects["techcorp"], EMP_EFUA,  "Efua Asante",  "lead",       100, 75),
            (projects["techcorp"], EMP_KOJO,  "Kojo Darko",   "member",     80,  60),
            # RetailCo
            (projects["retailco"], EMP_EFUA,  "Efua Asante",  "manager",    200, 80),
            (projects["retailco"], EMP_ABENA, "Abena Boateng","consultant", 150, 90),
            (projects["retailco"], EMP_KWAME, "Kwame Osei",   "member",     120, 65),
            # Internal HR
            (projects["internal_hr"], EMP_KOJO,  "Kojo Darko",   "manager", 60, 0),
            (projects["internal_hr"], EMP_KWAME, "Kwame Osei",   "member",  40, 0),
        ]

        for proj, emp_id, emp_name, role, alloc_hrs, billing_rate in members:
            ProjectMember.objects.get_or_create(
                project=proj,
                employee_id=emp_id,
                defaults={
                    "employee_name": emp_name,
                    "role": role,
                    "allocated_hours": alloc_hrs,
                    "billing_rate": billing_rate,
                    "cost_rate": billing_rate * 0.6,
                    "is_active": True,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Members: {}".format(len(members)))

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def _seed_tasks(self, projects):
        from apps.project.models import ProjectTask

        # TechCorp tasks
        tc_tasks = [
            ("Discovery & Requirements", "done",        "high",   20,  20),
            ("UX Wireframes",            "done",        "high",   40,  42),
            ("Design & Brand Assets",    "done",        "medium", 32,  35),
            ("Frontend Development",     "in_progress", "high",   120, 55),
            ("Backend / CMS Setup",      "in_progress", "high",   80,  30),
            ("QA & Testing",             "open",        "medium", 40,  0),
            ("Launch & Handover",        "open",        "medium", 20,  0),
        ]
        for i, (title, status, priority, est, actual) in enumerate(tc_tasks):
            ProjectTask.objects.get_or_create(
                project=projects["techcorp"],
                title=title,
                defaults={
                    "status": status,
                    "priority": priority,
                    "sequence": i + 1,
                    "estimated_hours": est,
                    "actual_hours": actual,
                    "company_id": COMPANY_ID,
                },
            )

        # RetailCo tasks
        rc_tasks = [
            ("As-Is Assessment",          "done",        "high",   40,  44),
            ("Gap Analysis & Design",     "done",        "high",   60,  58),
            ("Configuration",             "in_progress", "high",   200, 80),
            ("Data Migration",            "open",        "high",   80,  0),
            ("User Acceptance Testing",   "open",        "medium", 60,  0),
            ("Training",                  "open",        "medium", 40,  0),
            ("Go-Live Support",           "open",        "low",    60,  0),
            ("Hypercare",                 "open",        "low",    40,  0),
        ]
        for i, (title, status, priority, est, actual) in enumerate(rc_tasks):
            ProjectTask.objects.get_or_create(
                project=projects["retailco"],
                title=title,
                defaults={
                    "status": status,
                    "priority": priority,
                    "sequence": i + 1,
                    "estimated_hours": est,
                    "actual_hours": actual,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Tasks: {} (TechCorp) + {} (RetailCo)".format(
            len(tc_tasks), len(rc_tasks)
        ))

    # ── Milestones ────────────────────────────────────────────────────────────

    def _seed_milestones(self, projects):
        from apps.project.models import Milestone

        milestones = [
            # TechCorp
            (projects["techcorp"], "Design Approved",
             datetime.date(2026, 2, 15), "achieved",
             datetime.date(2026, 2, 12), 0),
            (projects["techcorp"], "Frontend Complete",
             datetime.date(2026, 3, 10), "pending", None, 0),
            (projects["techcorp"], "Go-Live",
             datetime.date(2026, 3, 31), "pending", None, 0),
            # RetailCo
            (projects["retailco"], "Phase 1: Configuration Complete",
             datetime.date(2026, 4, 30), "pending", None, 60000),
            (projects["retailco"], "Phase 2: Data Migration Sign-off",
             datetime.date(2026, 5, 31), "pending", None, 50000),
            (projects["retailco"], "Go-Live",
             datetime.date(2026, 7, 31), "pending", None, 70000),
        ]

        for proj, title, due, status, achieved_at, billing in milestones:
            Milestone.objects.get_or_create(
                project=proj,
                title=title,
                defaults={
                    "due_date": due,
                    "status": status,
                    "achieved_at": achieved_at,
                    "billing_amount": billing,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Milestones: {}".format(len(milestones)))

    # ── Billing rules ─────────────────────────────────────────────────────────

    def _seed_billing_rules(self, projects):
        from apps.project.models import BillingRule, Milestone

        # TechCorp: bill on timesheet approval
        BillingRule.objects.get_or_create(
            project=projects["techcorp"],
            billing_event=BillingRule.BillingEvent.TIMESHEET_APPROVAL,
            defaults={
                "description": "Monthly timesheet billing",
                "tax_rate": 0,
                "is_active": True,
                "company_id": COMPANY_ID,
            },
        )

        # RetailCo: milestone billing for each phase
        for milestone in Milestone.objects.filter(
            project=projects["retailco"], is_deleted=False
        ):
            if milestone.billing_amount > 0:
                BillingRule.objects.get_or_create(
                    project=projects["retailco"],
                    milestone=milestone,
                    defaults={
                        "billing_event": BillingRule.BillingEvent.MILESTONE,
                        "description": "Milestone: {}".format(milestone.title),
                        "billing_amount": milestone.billing_amount,
                        "tax_rate": 15,
                        "is_active": True,
                        "company_id": COMPANY_ID,
                    },
                )

        self.stdout.write("  Billing rules seeded.")

    # ── Risks & Issues ────────────────────────────────────────────────────────

    def _seed_risks_issues(self, projects):
        from apps.project.models import RiskIssue

        items = [
            (projects["techcorp"], "risk",  "Client feedback delay risk",
             "Client may not respond to design reviews in time.",
             "medium", "open", 30,
             "Schedule review checkpoints with client success manager."),
            (projects["techcorp"], "issue", "CMS integration scope creep",
             "Client requesting custom plugin development beyond original scope.",
             "high", "in_progress", None,
             "Raise change request; update SOW before proceeding."),
            (projects["retailco"], "risk",  "Data quality risk for migration",
             "Legacy data has inconsistent formats across branches.",
             "high", "open", 60,
             "Run data profiling in Phase 1; allocate 2 weeks for cleansing."),
            (projects["retailco"], "risk",  "Key stakeholder availability",
             "CFO may not be available during UAT week.",
             "medium", "open", 40,
             "Confirm availability 3 weeks before UAT start; nominate backup approver."),
            (projects["retailco"], "issue", "Network connectivity at branch 7",
             "Branch 7 does not have reliable internet for real-time sync.",
             "critical", "in_progress", None,
             "Evaluate offline-first mode or upgrade branch connectivity."),
        ]

        for proj, rtype, title, desc, severity, status, prob, mitigation in items:
            RiskIssue.objects.get_or_create(
                project=proj,
                title=title,
                defaults={
                    "record_type": rtype,
                    "description": desc,
                    "severity": severity,
                    "status": status,
                    "probability": prob,
                    "mitigation_plan": mitigation,
                    "company_id": COMPANY_ID,
                },
            )

        self.stdout.write("  Risks/Issues: {}".format(len(items)))

    # ── Timesheets ────────────────────────────────────────────────────────────

    def _seed_timesheets(self, projects):
        from apps.project.models import Timesheet, TimesheetEntry, ProjectTask

        if Timesheet.objects.filter(
            timesheet_number="TS-00001", is_deleted=False
        ).exists():
            self.stdout.write("  Timesheets already seeded, skipping.")
            return

        from core.numbering.service import get_next_number

        week1_start = datetime.date(2026, 3, 2)
        week1_end   = datetime.date(2026, 3, 8)

        # Alex — TechCorp frontend work
        ts1 = Timesheet.objects.create(
            timesheet_number=get_next_number("TS", COMPANY_ID),
            employee_id=EMP_ALEX,
            employee_name="Alex Mensah",
            start_date=week1_start,
            end_date=week1_end,
            status=Timesheet.Status.APPROVED,
            company_id=COMPANY_ID,
        )
        tc_frontend = ProjectTask.objects.filter(
            project=projects["techcorp"], title="Frontend Development", is_deleted=False
        ).first()
        _entries_alex = [
            (projects["techcorp"], tc_frontend, "development",
             datetime.datetime(2026, 3, 3, 9, 0), datetime.datetime(2026, 3, 3, 17, 0),
             8, True, 85),
            (projects["techcorp"], tc_frontend, "development",
             datetime.datetime(2026, 3, 4, 9, 0), datetime.datetime(2026, 3, 4, 17, 0),
             8, True, 85),
            (projects["techcorp"], None, "meeting",
             datetime.datetime(2026, 3, 5, 10, 0), datetime.datetime(2026, 3, 5, 11, 0),
             1, False, 0),
            (projects["techcorp"], tc_frontend, "development",
             datetime.datetime(2026, 3, 6, 9, 0), datetime.datetime(2026, 3, 6, 17, 0),
             8, True, 85),
            (projects["techcorp"], tc_frontend, "review",
             datetime.datetime(2026, 3, 7, 9, 0), datetime.datetime(2026, 3, 7, 13, 0),
             4, True, 85),
        ]
        total_h = 0
        total_b = 0
        total_ba = 0
        for proj, task, activity, ft, tt, hours, billable, rate in _entries_alex:
            ba = hours * rate if billable else 0
            TimesheetEntry.objects.create(
                timesheet=ts1,
                project=proj,
                task=task,
                activity_type=activity,
                from_time=ft,
                to_time=tt,
                hours=hours,
                is_billable=billable,
                billing_rate=rate,
                billing_amount=ba,
                company_id=COMPANY_ID,
            )
            total_h += hours
            if billable:
                total_b += hours
                total_ba += ba
        ts1.total_hours = total_h
        ts1.total_billable_hours = total_b
        ts1.total_billing_amount = total_ba
        ts1.save(update_fields=["total_hours", "total_billable_hours", "total_billing_amount"])

        # Efua — RetailCo configuration
        ts2 = Timesheet.objects.create(
            timesheet_number=get_next_number("TS", COMPANY_ID),
            employee_id=EMP_EFUA,
            employee_name="Efua Asante",
            start_date=week1_start,
            end_date=week1_end,
            status=Timesheet.Status.SUBMITTED,
            company_id=COMPANY_ID,
        )
        rc_config = ProjectTask.objects.filter(
            project=projects["retailco"], title="Configuration", is_deleted=False
        ).first()
        _entries_efua = [
            (projects["retailco"], rc_config, "development",
             datetime.datetime(2026, 3, 3, 8, 0), datetime.datetime(2026, 3, 3, 16, 0),
             8, True, 80),
            (projects["retailco"], rc_config, "development",
             datetime.datetime(2026, 3, 4, 8, 0), datetime.datetime(2026, 3, 4, 16, 0),
             8, True, 80),
            (projects["retailco"], rc_config, "documentation",
             datetime.datetime(2026, 3, 5, 9, 0), datetime.datetime(2026, 3, 5, 13, 0),
             4, True, 80),
            (projects["retailco"], None, "meeting",
             datetime.datetime(2026, 3, 6, 14, 0), datetime.datetime(2026, 3, 6, 16, 0),
             2, False, 0),
            (projects["retailco"], rc_config, "development",
             datetime.datetime(2026, 3, 7, 8, 0), datetime.datetime(2026, 3, 7, 16, 0),
             8, True, 80),
        ]
        total_h = 0
        total_b = 0
        total_ba = 0
        for proj, task, activity, ft, tt, hours, billable, rate in _entries_efua:
            ba = hours * rate if billable else 0
            TimesheetEntry.objects.create(
                timesheet=ts2,
                project=proj,
                task=task,
                activity_type=activity,
                from_time=ft,
                to_time=tt,
                hours=hours,
                is_billable=billable,
                billing_rate=rate,
                billing_amount=ba,
                company_id=COMPANY_ID,
            )
            total_h += hours
            if billable:
                total_b += hours
                total_ba += ba
        ts2.total_hours = total_h
        ts2.total_billable_hours = total_b
        ts2.total_billing_amount = total_ba
        ts2.save(update_fields=["total_hours", "total_billable_hours", "total_billing_amount"])

        # Kojo — draft timesheet (TechCorp backend)
        ts3 = Timesheet.objects.create(
            timesheet_number=get_next_number("TS", COMPANY_ID),
            employee_id=EMP_KOJO,
            employee_name="Kojo Darko",
            start_date=week1_start,
            end_date=week1_end,
            status=Timesheet.Status.DRAFT,
            company_id=COMPANY_ID,
        )
        tc_backend = ProjectTask.objects.filter(
            project=projects["techcorp"], title="Backend / CMS Setup", is_deleted=False
        ).first()
        _entries_kojo = [
            (projects["techcorp"], tc_backend, "development",
             datetime.datetime(2026, 3, 3, 9, 0), datetime.datetime(2026, 3, 3, 17, 0),
             8, True, 60),
            (projects["techcorp"], tc_backend, "development",
             datetime.datetime(2026, 3, 4, 9, 0), datetime.datetime(2026, 3, 4, 17, 0),
             8, True, 60),
            (projects["techcorp"], tc_backend, "support",
             datetime.datetime(2026, 3, 5, 9, 0), datetime.datetime(2026, 3, 5, 13, 0),
             4, True, 60),
        ]
        total_h = 0
        total_b = 0
        total_ba = 0
        for proj, task, activity, ft, tt, hours, billable, rate in _entries_kojo:
            ba = hours * rate if billable else 0
            TimesheetEntry.objects.create(
                timesheet=ts3,
                project=proj,
                task=task,
                activity_type=activity,
                from_time=ft,
                to_time=tt,
                hours=hours,
                is_billable=billable,
                billing_rate=rate,
                billing_amount=ba,
                company_id=COMPANY_ID,
            )
            total_h += hours
            if billable:
                total_b += hours
                total_ba += ba
        ts3.total_hours = total_h
        ts3.total_billable_hours = total_b
        ts3.total_billing_amount = total_ba
        ts3.save(update_fields=["total_hours", "total_billable_hours", "total_billing_amount"])

        self.stdout.write("  Timesheets: 3 (1 approved, 1 submitted, 1 draft)")
