"""
Management command: seed realistic HRM dummy data.
Usage: python manage.py seed_hrm [--clear]

Covers: Departments, Job Positions, Employees (with hierarchy), Shifts,
Holiday List, Leave Types, Leave Balances, Leave Applications, Attendance
records (30 days), Job Applicants, Interviews, Performance Reviews, Goals,
Employee Documents, Disciplinary Cases, Onboarding Checklists.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()
TODAY = date.today()
YEAR = TODAY.year


DEPARTMENTS = [
    ("Engineering",       "Software development and platform infrastructure"),
    ("Product",           "Product management, UX, and roadmap planning"),
    ("Sales",             "Revenue generation and business development"),
    ("Marketing",         "Brand, demand generation, and content"),
    ("Customer Success",  "Onboarding, support, and retention"),
    ("Finance",           "Accounting, FP&A, and treasury"),
    ("HR & People Ops",   "Recruiting, people ops, and culture"),
    ("Legal & Compliance","Legal counsel and regulatory compliance"),
    ("Operations",        "IT infrastructure, procurement, and facilities"),
]

SHIFTS = [
    # (name, type, start, end, hours)
    ("Standard Day",   "morning",   time(9,0),  time(17,0), 8),
    ("Early Morning",  "morning",   time(7,0),  time(15,0), 8),
    ("Late Shift",     "afternoon", time(13,0), time(21,0), 8),
    ("Night Shift",    "night",     time(22,0), time(6,0),  8),
    ("Flexible",       "flexible",  time(8,0),  time(18,0), 8),
]

LEAVE_TYPES = [
    # (name, days/yr, paid, carry_fwd, max_carry, freq)
    ("Annual Leave",       20.0, True,  True,  5.0, "annually"),
    ("Sick Leave",         10.0, True,  False, 0.0, "annually"),
    ("Maternity Leave",    90.0, True,  False, 0.0, "annually"),
    ("Paternity Leave",    10.0, True,  False, 0.0, "annually"),
    ("Bereavement Leave",   5.0, True,  False, 0.0, "annually"),
    ("Unpaid Leave",        0.0, False, False, 0.0, "annually"),
    ("Study Leave",         5.0, True,  False, 0.0, "annually"),
    ("Emergency Leave",     3.0, True,  False, 0.0, "annually"),
]

# (first, last, dept_idx, designation, emp_type, status, manager_idx_or_None, gender)
EMPLOYEES = [
    # C-suite / leadership
    ("Sarah",   "Chen",      6, "Chief People Officer",   "full_time", "active", None,  "female"),
    ("Marcus",  "Wright",    0, "VP Engineering",         "full_time", "active", None,  "male"),
    ("Priya",   "Patel",     1, "VP Product",             "full_time", "active", None,  "female"),
    ("James",   "O'Brien",   2, "VP Sales",               "full_time", "active", None,  "male"),
    ("Amara",   "Mensah",    5, "CFO",                    "full_time", "active", None,  "female"),
    # Engineering
    ("Daniel",  "Kim",       0, "Senior Software Engineer","full_time","active", 1,     "male"),
    ("Sofia",   "Rossi",     0, "Senior Software Engineer","full_time","active", 1,     "female"),
    ("Kwame",   "Asante",    0, "Software Engineer",      "full_time","active", 1,     "male"),
    ("Fatima",  "Al-Hassan", 0, "Software Engineer",      "full_time","active", 1,     "female"),
    ("Liam",    "Murphy",    0, "Junior Engineer",        "full_time","probation",1,   "male"),
    ("Yuki",    "Tanaka",    0, "DevOps Engineer",        "full_time","active", 1,     "female"),
    # Product
    ("Elena",   "Volkov",    1, "Senior Product Manager", "full_time","active", 2,     "female"),
    ("Carlos",  "Diaz",      1, "Product Designer",       "full_time","active", 2,     "male"),
    # Sales
    ("Rachel",  "Thompson",  2, "Sales Manager",          "full_time","active", 3,     "female"),
    ("Ahmed",   "Hassan",    2, "Account Executive",      "full_time","active", 13,    "male"),
    ("Grace",   "Osei",      2, "Account Executive",      "full_time","active", 13,    "female"),
    ("Tomasz",  "Kowalski",  2, "Sales Development Rep",  "full_time","active", 13,    "male"),
    # Marketing
    ("Nadia",   "Petrov",    3, "Marketing Manager",      "full_time","active", None,  "female"),
    ("Felix",   "Weber",     3, "Content Strategist",     "full_time","active", 17,    "male"),
    # Customer Success
    ("Zara",    "Ali",       4, "CS Team Lead",           "full_time","active", None,  "female"),
    ("Ethan",   "Brown",     4, "Customer Success Manager","full_time","active", 19,   "male"),
    # Finance
    ("Ingrid",  "Larsson",   5, "Senior Accountant",      "full_time","active", 4,     "female"),
    # HR
    ("Oliver",  "Jackson",   6, "HR Business Partner",    "full_time","active", 0,     "male"),
    # Legal
    ("Natasha", "Ivanova",   7, "General Counsel",        "full_time","active", None,  "female"),
    # Operations
    ("Ben",     "Adeyemi",   8, "IT Manager",             "full_time","active", None,  "male"),
    # Part-time / Contract
    ("Mei",     "Zhang",     0, "Contract QA Engineer",   "contract", "active", 1,     "female"),
    ("Tom",     "Carter",    3, "Marketing Intern",       "intern",   "active", 17,    "male"),
]

JOB_POSITIONS = [
    ("Senior Backend Engineer",  0, "full_time", "open",   2),
    ("Product Manager",          1, "full_time", "open",   1),
    ("Account Executive",        2, "full_time", "open",   3),
    ("Frontend Engineer",        0, "full_time", "open",   1),
    ("Data Analyst",             5, "full_time", "open",   1),
    ("DevOps Engineer",          0, "full_time", "on_hold",1),
    ("Customer Success Manager", 4, "full_time", "filled", 1),
]

APPLICANTS = [
    # (name, email, position_idx, source, status, exp_years)
    ("Alex Johnson",    "alex.j@example.com",    0, "linkedin",  "interview",   5),
    ("Maria Garcia",    "m.garcia@example.com",  0, "referral",  "shortlisted", 7),
    ("David Park",      "d.park@example.com",    0, "job_board", "screening",   3),
    ("Aisha Williams",  "a.williams@example.com",1, "direct",    "offer",       4),
    ("Kevin Lee",       "k.lee@example.com",     2, "linkedin",  "interview",   6),
    ("Emma Davis",      "e.davis@example.com",   2, "recruiter", "applied",     2),
    ("Sam Nguyen",      "s.nguyen@example.com",  3, "linkedin",  "shortlisted", 4),
    ("Laura Schmidt",   "l.schmidt@example.com", 4, "direct",    "hired",       5),
    ("Omar Abdullah",   "o.abd@example.com",     5, "job_board", "rejected",    8),
    ("Chloe Martin",    "c.martin@example.com",  2, "campus",    "withdrawn",   1),
]

PERF_REVIEWS = [
    # (emp_idx, cycle_type, period, rating, status)
    (5,  "manager", "H1 2026", Decimal("4.2"), "submitted"),
    (6,  "manager", "H1 2026", Decimal("4.5"), "acknowledged"),
    (7,  "manager", "H1 2026", Decimal("3.8"), "submitted"),
    (11, "manager", "H1 2026", Decimal("4.7"), "acknowledged"),
    (14, "manager", "H1 2026", Decimal("3.5"), "draft"),
    (19, "manager", "H1 2026", Decimal("4.1"), "submitted"),
    (5,  "self",    "H1 2026", Decimal("4.0"), "submitted"),
    (6,  "self",    "H1 2026", Decimal("4.3"), "acknowledged"),
]

GOALS_DATA = [
    # (emp_idx, title, period, progress, status)
    (5,  "Ship metadata-driven REST API v2",                "Q3 2026", 75, "in_progress"),
    (5,  "Reduce API p95 latency below 100ms",             "Q3 2026", 60, "in_progress"),
    (6,  "Launch redesigned entity form component",        "Q3 2026", 90, "in_progress"),
    (7,  "Complete HIPAA compliance implementation",       "Q3 2026", 40, "in_progress"),
    (11, "Deliver Q3 Product Roadmap deck to board",       "Q3 2026",100, "completed"),
    (13, "Achieve $2M new ARR in Q3",                      "Q3 2026", 65, "in_progress"),
    (14, "Close 8 enterprise deals",                       "Q3 2026", 50, "in_progress"),
    (19, "Reduce churn rate to below 3%",                  "Q3 2026", 80, "in_progress"),
    (4,  "Close FY2026 books within 5 business days",     "Q4 2026",  0, "not_started"),
    (22, "Onboard 3 new hires by end of Q3",              "Q3 2026", 67, "in_progress"),
]

DISCIPLINARY = [
    # (emp_idx, case_type, days_ago, description, status)
    (16, "verbal_warning", 90,
     "Repeated late submissions of weekly pipeline reports without prior notice.",
     "closed"),
    (9,  "warning", 45,
     "Failure to follow code review process on two consecutive sprint cycles.",
     "resolved"),
]


class Command(BaseCommand):
    help = "Seed realistic HRM dummy data."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing HRM data first")

    def handle(self, *args, **options):
        from apps.hrm.models import (
            Attendance, ChecklistTask, Department, DisciplinaryCase,
            Employee, EmployeeChecklist, EmployeeDocument, Goal, Holiday,
            HolidayList, Interview, JobApplicant, JobPosition, LeaveApplication,
            LeaveBalance, LeaveType, PerformanceReview, Shift, ShiftAssignment,
        )

        if options["clear"]:
            self.stdout.write("  Clearing HRM data…")
            for M in [
                ChecklistTask, EmployeeChecklist, DisciplinaryCase,
                PerformanceReview, Goal, Interview, JobApplicant,
                EmployeeDocument, ShiftAssignment, Attendance, LeaveApplication,
                LeaveBalance, Holiday, HolidayList, LeaveType, Employee,
                JobPosition, Shift, Department,
            ]:
                M.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Cleared."))

        admin = User.objects.filter(is_superuser=True).first()

        # ── 1. Departments ────────────────────────────────────────────────────
        self.stdout.write("  Seeding departments…")
        dept_objs = []
        for name, desc in DEPARTMENTS:
            obj, _ = Department.objects.get_or_create(
                name=name, defaults={"description": desc}
            )
            dept_objs.append(obj)

        # ── 2. Job Positions (before employees so we can set hiring_manager) ──
        self.stdout.write("  Seeding job positions…")
        position_objs = []
        for title, dept_idx, emp_type, status, headcount in JOB_POSITIONS:
            p, _ = JobPosition.objects.get_or_create(
                title=title,
                defaults={
                    "department": dept_objs[dept_idx],
                    "employment_type": emp_type,
                    "status": status,
                    "headcount": headcount,
                    "description": f"We are hiring a {title} to join our growing team.",
                    "requirements": "3+ years of relevant experience. Strong communication skills.",
                    "expected_start_date": TODAY + timedelta(days=30),
                },
            )
            position_objs.append(p)

        # ── 3. Shifts ─────────────────────────────────────────────────────────
        self.stdout.write("  Seeding shifts…")
        shift_objs = []
        for name, stype, start, end, hours in SHIFTS:
            s, _ = Shift.objects.get_or_create(
                name=name,
                defaults={
                    "shift_type": stype,
                    "start_time": start,
                    "end_time": end,
                    "total_hours": Decimal(str(hours)),
                    "late_entry_grace_minutes": 15,
                    "early_exit_grace_minutes": 15,
                    "overtime_threshold_hours": Decimal("8"),
                },
            )
            shift_objs.append(s)

        default_shift = shift_objs[0]

        # ── 4. Employees ──────────────────────────────────────────────────────
        self.stdout.write("  Seeding employees…")
        emp_objs = []
        for idx, (first, last, dept_idx, designation, emp_type, status, mgr_idx, gender) in enumerate(EMPLOYEES):
            emp_num = f"EMP-{str(idx+1).zfill(4)}"
            join_date = TODAY - timedelta(days=random.randint(30, 1200))
            dob = TODAY - timedelta(days=random.randint(25*365, 50*365))
            e, created = Employee.objects.get_or_create(
                employee_number=emp_num,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{first.lower()}.{last.lower().replace(' ', '').replace(chr(39), '')}@odum-erp.io",
                    "department": dept_objs[dept_idx],
                    "designation": designation,
                    "employment_type": emp_type,
                    "status": status,
                    "date_of_joining": join_date,
                    "date_of_birth": dob,
                    "gender": gender,
                    "nationality": random.choice(["US", "UK", "GH", "NG", "IN", "DE", "FR"]),
                    "phone": f"+1-555-{random.randint(1000,9999)}",
                    "notice_period_days": 30,
                    "emergency_contact_name": f"{random.choice(['Alice','Bob','Carol'])} {last}",
                    "emergency_contact_phone": f"+1-555-{random.randint(1000,9999)}",
                    "emergency_contact_relation": random.choice(["Spouse", "Parent", "Sibling"]),
                },
            )
            emp_objs.append(e)

        # Set manager FKs (after all employees created)
        for idx, (_, _, _, _, _, _, mgr_idx, _) in enumerate(EMPLOYEES):
            if mgr_idx is not None:
                emp_objs[idx].manager = emp_objs[mgr_idx]
                emp_objs[idx].save(update_fields=["manager"])

        # Set dept heads
        dept_objs[6].head_employee_id = emp_objs[0].pk  # HR dept head = Sarah Chen
        dept_objs[6].save(update_fields=["head_employee_id"])
        dept_objs[0].head_employee_id = emp_objs[1].pk  # Eng head = Marcus Wright
        dept_objs[0].save(update_fields=["head_employee_id"])

        # Assign shifts
        for emp in emp_objs:
            shift = shift_objs[4] if emp.employment_type == "contract" else default_shift
            ShiftAssignment.objects.get_or_create(
                employee=emp,
                shift=shift,
                from_date=emp.date_of_joining or TODAY - timedelta(days=180),
                defaults={"is_active": True},
            )

        # ── 5. Holiday List ───────────────────────────────────────────────────
        self.stdout.write("  Seeding holiday list…")
        hl, _ = HolidayList.objects.get_or_create(
            name=f"US Public Holidays {YEAR}",
            defaults={
                "from_date": date(YEAR, 1, 1),
                "to_date": date(YEAR, 12, 31),
                "country": "US",
                "is_default": True,
            },
        )
        us_holidays = [
            (date(YEAR, 1,  1),  "New Year's Day"),
            (date(YEAR, 1, 20),  "Martin Luther King Jr. Day"),
            (date(YEAR, 2, 17),  "Presidents' Day"),
            (date(YEAR, 5, 26),  "Memorial Day"),
            (date(YEAR, 6, 19),  "Juneteenth"),
            (date(YEAR, 7,  4),  "Independence Day"),
            (date(YEAR, 9,  1),  "Labor Day"),
            (date(YEAR,11, 27),  "Thanksgiving Day"),
            (date(YEAR,11, 28),  "Day after Thanksgiving"),
            (date(YEAR,12, 25),  "Christmas Day"),
            (date(YEAR,12, 26),  "Christmas Holiday"),
        ]
        for hdate, hdesc in us_holidays:
            Holiday.objects.get_or_create(
                holiday_list=hl, holiday_date=hdate,
                defaults={"description": hdesc, "is_weekly_off": False},
            )

        # ── 6. Leave Types ────────────────────────────────────────────────────
        self.stdout.write("  Seeding leave types…")
        lt_objs = []
        for name, days, paid, carry, max_carry, freq in LEAVE_TYPES:
            lt, _ = LeaveType.objects.get_or_create(
                name=name,
                defaults={
                    "days_allowed_per_year": Decimal(str(days)),
                    "is_paid": paid,
                    "carry_forward": carry,
                    "max_carry_forward_days": Decimal(str(max_carry)),
                    "allow_negative_balance": False,
                    "accrual_frequency": freq,
                },
            )
            lt_objs.append(lt)

        # ── 7. Leave Balances + Applications ──────────────────────────────────
        self.stdout.write("  Seeding leave balances and applications…")
        annual_lt = lt_objs[0]
        sick_lt   = lt_objs[1]

        leave_app_objs = []
        for emp in emp_objs[:20]:  # first 20 employees
            for lt in (annual_lt, sick_lt):
                alloc = lt.days_allowed_per_year
                carried = Decimal("2") if lt.carry_forward else Decimal("0")
                taken = Decimal(str(random.randint(0, int(float(alloc) * 0.4))))
                LeaveBalance.objects.get_or_create(
                    employee=emp, leave_type=lt, year=YEAR,
                    defaults={
                        "total_allocated": alloc,
                        "carried_forward": carried,
                        "total_taken": taken,
                        "total_pending": Decimal("0"),
                    },
                )

        # Realistic leave applications
        leave_scenarios = [
            (5,  annual_lt, TODAY - timedelta(days=60), 5, "approved"),
            (6,  annual_lt, TODAY - timedelta(days=45), 3, "approved"),
            (7,  sick_lt,   TODAY - timedelta(days=20), 2, "approved"),
            (8,  annual_lt, TODAY + timedelta(days=14), 5, "pending"),
            (11, annual_lt, TODAY - timedelta(days=30), 2, "approved"),
            (13, annual_lt, TODAY + timedelta(days=7),  3, "pending"),
            (14, sick_lt,   TODAY - timedelta(days=10), 1, "approved"),
            (15, annual_lt, TODAY - timedelta(days=5),  4, "rejected"),
            (19, annual_lt, TODAY + timedelta(days=21), 5, "pending"),
            (20, sick_lt,   TODAY - timedelta(days=3),  2, "pending"),
        ]
        for emp_idx, lt, from_d, days, status in leave_scenarios:
            to_d = from_d + timedelta(days=days - 1)
            la, _ = LeaveApplication.objects.get_or_create(
                employee=emp_objs[emp_idx],
                leave_type=lt,
                from_date=from_d,
                defaults={
                    "to_date": to_d,
                    "total_days": Decimal(str(days)),
                    "reason": random.choice([
                        "Family vacation",
                        "Medical appointment",
                        "Personal reasons",
                        "Annual leave",
                        "Feeling unwell",
                    ]),
                    "status": status,
                    "approved_by": admin if status == "approved" else None,
                    "approved_at": timezone.now() - timedelta(days=random.randint(1,10)) if status == "approved" else None,
                    "rejection_reason": "Insufficient leave balance for the requested period." if status == "rejected" else "",
                },
            )
            leave_app_objs.append(la)

        # ── 8. Attendance (last 30 working days for first 15 employees) ────────
        self.stdout.write("  Seeding attendance records…")
        att_count = 0
        for emp in emp_objs[:15]:
            for day_offset in range(1, 31):
                att_date = TODAY - timedelta(days=day_offset)
                if att_date.weekday() >= 5:  # skip weekends
                    continue
                # 90% present, 5% on leave, 5% absent
                roll = random.random()
                if roll < 0.90:
                    check_in_h = random.randint(8, 9)
                    check_in_m = random.randint(0, 59)
                    check_out_h = random.randint(17, 18)
                    check_out_m = random.randint(0, 59)
                    ci = timezone.make_aware(
                        datetime(att_date.year, att_date.month, att_date.day, check_in_h, check_in_m)
                    )
                    co = timezone.make_aware(
                        datetime(att_date.year, att_date.month, att_date.day, check_out_h, check_out_m)
                    )
                    delta = co - ci
                    wh = Decimal(str(round(delta.total_seconds() / 3600, 2)))
                    ot = max(Decimal("0"), wh - Decimal("8"))
                    Attendance.objects.get_or_create(
                        employee=emp,
                        attendance_date=att_date,
                        defaults={
                            "check_in": ci,
                            "check_out": co,
                            "working_hours": wh,
                            "overtime_hours": ot,
                            "method": random.choice(["manual", "qr", "biometric"]),
                            "status": "present",
                            "shift": default_shift,
                            "late_entry": check_in_h >= 9 and check_in_m > 15,
                            "early_exit": check_out_h < 17,
                        },
                    )
                elif roll < 0.95:
                    Attendance.objects.get_or_create(
                        employee=emp,
                        attendance_date=att_date,
                        defaults={
                            "status": "on_leave",
                            "method": "manual",
                        },
                    )
                else:
                    Attendance.objects.get_or_create(
                        employee=emp,
                        attendance_date=att_date,
                        defaults={
                            "status": "absent",
                            "method": "manual",
                        },
                    )
                att_count += 1

        # ── 9. Job Applicants + Interviews ─────────────────────────────────────
        self.stdout.write("  Seeding job applicants and interviews…")
        applicant_objs = []
        for name, email, pos_idx, source, status, exp in APPLICANTS:
            app, _ = JobApplicant.objects.get_or_create(
                email=email,
                defaults={
                    "job_position": position_objs[pos_idx],
                    "applicant_name": name,
                    "phone": f"+1-555-{random.randint(1000,9999)}",
                    "source": source,
                    "status": status,
                    "applied_date": TODAY - timedelta(days=random.randint(5, 45)),
                    "experience_years": Decimal(str(exp)),
                    "expected_salary": Decimal(str(random.randint(80, 160) * 1000)),
                    "cover_letter": f"I am excited to apply for the {position_objs[pos_idx].title} role.",
                    "notes": "Strong candidate." if status not in ("rejected","withdrawn") else "",
                    "rejection_reason": "Insufficient experience for the seniority level." if status == "rejected" else "",
                },
            )
            applicant_objs.append(app)
            # Create 1-2 interviews for candidates in late stages
            if status in ("interview", "offer", "hired"):
                for itype in ["phone", "technical"]:
                    Interview.objects.get_or_create(
                        job_applicant=app,
                        interview_type=itype,
                        defaults={
                            "interviewer_name": random.choice([e.full_name for e in emp_objs[:5]]),
                            "scheduled_at": timezone.make_aware(
                                datetime(TODAY.year, TODAY.month, TODAY.day, 10, 0)
                            ) - timedelta(days=random.randint(5, 20)),
                            "duration_minutes": 60,
                            "status": "completed",
                            "feedback": "Strong technical background. Good communication. Proceed to next round.",
                            "score": random.randint(7, 10),
                            "recommendation": "yes",
                        },
                    )

        # ── 10. Performance Reviews + Goals ───────────────────────────────────
        self.stdout.write("  Seeding performance reviews and goals…")
        for emp_idx, cycle, period, rating, status in PERF_REVIEWS:
            reviewer = emp_objs[emp_objs[emp_idx].manager.pk == emp_objs[0].pk and 0 or 0] if emp_objs[emp_idx].manager else emp_objs[0]
            PerformanceReview.objects.get_or_create(
                employee=emp_objs[emp_idx],
                cycle_type=cycle,
                period=period,
                defaults={
                    "reviewer_employee_id": reviewer.pk,
                    "reviewer_name": reviewer.full_name,
                    "overall_rating": rating,
                    "strengths": "Excellent technical skills and collaborative spirit.",
                    "areas_for_improvement": "Can improve cross-team communication.",
                    "comments": "Solid performer who consistently delivers.",
                    "status": status,
                    "submitted_at": timezone.now() - timedelta(days=random.randint(5, 30)) if status in ("submitted","acknowledged") else None,
                    "acknowledged_at": timezone.now() - timedelta(days=random.randint(1, 5)) if status == "acknowledged" else None,
                },
            )

        for emp_idx, title, period, progress, status in GOALS_DATA:
            Goal.objects.get_or_create(
                employee=emp_objs[emp_idx],
                title=title,
                defaults={
                    "description": f"Deliver measurable outcomes for: {title}",
                    "key_results": "- KR1: Measurable outcome\n- KR2: Adoption metric\n- KR3: Quality metric",
                    "target_date": TODAY + timedelta(days=90),
                    "period": period,
                    "weight": Decimal("1"),
                    "progress_pct": progress,
                    "status": status,
                    "set_by_employee_id": emp_objs[0].pk,
                },
            )

        # ── 11. Employee Documents ─────────────────────────────────────────────
        self.stdout.write("  Seeding employee documents…")
        doc_templates = [
            ("contract",    "Employment Contract",        -365, 365*2),
            ("offer_letter","Offer Letter",               -370, None),
            ("nda",         "Non-Disclosure Agreement",   -360, None),
            ("policy_ack",  "Employee Handbook Acknowledgment", -355, None),
        ]
        for emp in emp_objs[:15]:
            for dtype, dname, issue_offset, expiry_offset in doc_templates:
                EmployeeDocument.objects.get_or_create(
                    employee=emp,
                    document_type=dtype,
                    document_name=dname,
                    defaults={
                        "issue_date": TODAY + timedelta(days=issue_offset),
                        "expiry_date": TODAY + timedelta(days=expiry_offset) if expiry_offset else None,
                        "is_verified": True,
                        "document_number": f"DOC-{random.randint(10000,99999)}",
                    },
                )
            # Add visa for non-US employees
            if emp.nationality not in ("US",):
                EmployeeDocument.objects.get_or_create(
                    employee=emp,
                    document_type="visa",
                    document_name="US Work Visa (H-1B)",
                    defaults={
                        "issue_date": TODAY - timedelta(days=300),
                        "expiry_date": TODAY + timedelta(days=365 * 2),
                        "is_verified": True,
                        "document_number": f"VISA-{random.randint(100000,999999)}",
                        "issuing_authority": "US Department of State",
                    },
                )

        # ── 12. Disciplinary Cases ─────────────────────────────────────────────
        self.stdout.write("  Seeding disciplinary cases…")
        for emp_idx, case_type, days_ago, desc, status in DISCIPLINARY:
            dc, created = DisciplinaryCase.objects.get_or_create(
                employee=emp_objs[emp_idx],
                case_type=case_type,
                incident_date=TODAY - timedelta(days=days_ago),
                defaults={
                    "description": desc,
                    "status": status,
                    "handled_by_employee_id": emp_objs[0].pk,
                    "resolution": "Employee acknowledged the issue and committed to improvement." if status in ("resolved","closed") else "",
                    "resolved_at": timezone.now() - timedelta(days=days_ago // 2) if status in ("resolved","closed") else None,
                    "is_confidential": True,
                },
            )

        # ── 13. Onboarding Checklists ──────────────────────────────────────────
        self.stdout.write("  Seeding onboarding checklists…")
        onboarding_tasks = [
            ("Sign employment contract",           "hr",       1),
            ("Complete I-9 / right-to-work check", "hr",       1),
            ("Set up laptop and system access",    "it",       3),
            ("Slack, email, and tools access",     "it",       2),
            ("Read and sign employee handbook",    "employee", 5),
            ("Complete mandatory security training","employee",7),
            ("Meet with direct manager",           "manager",  3),
            ("30-day check-in with HR",            "hr",       30),
        ]
        # Create checklists for 3 newest employees
        newest = sorted(emp_objs, key=lambda e: e.date_of_joining or date.min, reverse=True)[:3]
        for emp in newest:
            cl, _ = EmployeeChecklist.objects.get_or_create(
                employee=emp,
                checklist_type="onboarding",
                defaults={
                    "template_name": "Standard Onboarding",
                    "target_date": (emp.date_of_joining or TODAY) + timedelta(days=30),
                    "status": "in_progress",
                },
            )
            for i, (task_desc, responsible, due_offset) in enumerate(onboarding_tasks):
                due = (emp.date_of_joining or TODAY) + timedelta(days=due_offset)
                completed = due < TODAY
                ChecklistTask.objects.get_or_create(
                    checklist=cl,
                    task_description=task_desc,
                    defaults={
                        "responsible_type": responsible,
                        "due_date": due,
                        "is_completed": completed,
                        "completed_at": timezone.make_aware(
                            datetime(due.year, due.month, due.day, 10, 0)
                        ) if completed else None,
                    },
                )

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ HRM seed complete:\n"
            f"    {Department.objects.count()} departments\n"
            f"    {JobPosition.objects.count()} job positions\n"
            f"    {Employee.objects.count()} employees\n"
            f"    {Shift.objects.count()} shifts, {ShiftAssignment.objects.count()} assignments\n"
            f"    {HolidayList.objects.count()} holiday list(s) with {Holiday.objects.count()} holidays\n"
            f"    {LeaveType.objects.count()} leave types, "
            f"{LeaveBalance.objects.count()} balances, "
            f"{LeaveApplication.objects.count()} applications\n"
            f"    {Attendance.objects.count()} attendance records\n"
            f"    {JobApplicant.objects.count()} applicants, {Interview.objects.count()} interviews\n"
            f"    {PerformanceReview.objects.count()} performance reviews, {Goal.objects.count()} goals\n"
            f"    {EmployeeDocument.objects.count()} employee documents\n"
            f"    {DisciplinaryCase.objects.count()} disciplinary cases\n"
            f"    {EmployeeChecklist.objects.count()} onboarding checklists "
            f"({ChecklistTask.objects.count()} tasks)\n"
        ))
