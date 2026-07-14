"""Seed command: Payroll (§6.5).

Creates realistic demo data:
- Ghana PAYE + SSNIT statutory pack (2025 rates)
- 5 salary components (Basic, Housing, Transport, PAYE, SSNIT)
- 2 salary structures (Standard Staff, Senior Staff)
- 5 employees assigned to structures
- 3 payroll periods (3 historical months)
- 2 completed/submitted payroll entries with salary slips
- 1 processing payroll entry
- 1 draft off-cycle bonus run
- 2 employee loans (1 active with schedule, 1 settled)
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _d(y, m, d):
    return datetime.date(y, m, d)


class Command(BaseCommand):
    help = "Seed Payroll demo data"

    def handle(self, *args, **options):
        self.stdout.write("=== Payroll seed ===")

        pack = self._seed_statutory_pack()
        components = self._seed_components()
        structures = self._seed_structures(components)
        employees = self._seed_employees()
        self._seed_assignments(employees, structures)
        periods = self._seed_periods()
        self._seed_payroll_entries(periods, pack)
        self._seed_loans(employees, periods)

        self.stdout.write("Payroll seed complete.")

    # ── Statutory Pack ───────────────────────────────────────────────────────

    def _seed_statutory_pack(self):
        from apps.payroll.models import StatutoryPack, StatutoryRule

        pack, created = StatutoryPack.objects.get_or_create(
            name="Ghana PAYE + SSNIT 2025",
            defaults=dict(
                country_code="GH",
                country_name="Ghana",
                effective_from=_d(2025, 1, 1),
                currency="GHS",
                is_active=True,
                description="Ghana statutory deductions: Employee SSNIT 5.5%, Employer SSNIT 13%, PAYE progressive",
                company_id=COMPANY_ID,
            ),
        )
        if created:
            # Employee SSNIT: 5.5% of basic salary, capped at GHS 2,000/month
            StatutoryRule.objects.create(
                pack=pack,
                name="Employee SSNIT",
                abbr="EMP_SSNIT",
                rule_type=StatutoryRule.RuleType.EMPLOYEE_CONTRIBUTION,
                calc_method=StatutoryRule.CalcMethod.FIXED_RATE_OF_BASE,
                rate=Decimal("5.5000"),
                cap_amount=Decimal("2000.00"),
                sequence=10,
                is_active=True,
                company_id=COMPANY_ID,
            )
            # Ghana PAYE — progressive, 2025 bands (GHS per month)
            StatutoryRule.objects.create(
                pack=pack,
                name="PAYE Income Tax",
                abbr="PAYE",
                rule_type=StatutoryRule.RuleType.INCOME_TAX,
                calc_method=StatutoryRule.CalcMethod.BRACKET,
                rate=Decimal("0"),
                brackets=[
                    {"min": 0, "max": 490, "rate": 0},
                    {"min": 490, "max": 850, "rate": 5},
                    {"min": 850, "max": 1000, "rate": 10},
                    {"min": 1000, "max": 5000, "rate": 17.5},
                    {"min": 5000, "max": 20000, "rate": 25},
                    {"min": 20000, "rate": 35},
                ],
                sequence=20,
                is_active=True,
                company_id=COMPANY_ID,
            )
            self.stdout.write("  Created StatutoryPack: Ghana PAYE + SSNIT 2025 (2 rules)")

        return pack

    # ── Salary Components ────────────────────────────────────────────────────

    def _seed_components(self):
        from apps.payroll.models import SalaryComponent

        # Formulas use float arithmetic (base is passed as float in context)
        specs = [
            dict(name="Basic Salary", abbr="BASIC", component_type="earning", is_based_on_formula=True, formula="base", amount=0),
            dict(name="Housing Allowance", abbr="HOUSE", component_type="earning", is_based_on_formula=True, formula="base * 0.2", amount=0),
            dict(name="Transport Allowance", abbr="TRANS", component_type="earning", is_based_on_formula=True, formula="base * 0.1", amount=0),
            dict(name="Overtime Pay", abbr="OT", component_type="earning", is_based_on_formula=True, formula="(base / 160) * 1.5 * overtime", amount=0),
        ]

        components = {}
        for s in specs:
            comp, created = SalaryComponent.objects.get_or_create(
                name=s["name"],
                defaults={**s, "is_tax": False, "is_statutory": False, "description": "", "company_id": COMPANY_ID},
            )
            if not created:
                # Ensure formula fields are up to date on idempotent re-run
                SalaryComponent.objects.filter(pk=comp.pk).update(
                    is_based_on_formula=s["is_based_on_formula"],
                    formula=s.get("formula", ""),
                    abbr=s["abbr"],
                )
                comp.refresh_from_db()
            else:
                self.stdout.write("  Created SalaryComponent: {}".format(comp.name))
            components[s["abbr"]] = comp

        return components

    # ── Salary Structures ────────────────────────────────────────────────────

    def _seed_structures(self, components):
        from apps.payroll.models import SalaryStructure, SalaryStructureComponent

        structures = {}

        # Standard Staff
        std, created = SalaryStructure.objects.get_or_create(
            name="Standard Staff",
            defaults=dict(description="Standard monthly salary structure for all staff", is_active=True, company_id=COMPANY_ID),
        )
        if created:
            for seq, abbr in [(10, "BASIC"), (20, "HOUSE"), (30, "TRANS")]:
                SalaryStructureComponent.objects.get_or_create(
                    structure=std, component=components[abbr],
                    defaults={"sequence": seq, "company_id": COMPANY_ID},
                )
            self.stdout.write("  Created SalaryStructure: Standard Staff")
        structures["standard"] = std

        # Senior Staff (adds overtime)
        senior, created = SalaryStructure.objects.get_or_create(
            name="Senior Staff",
            defaults=dict(description="Senior staff structure with overtime eligibility", is_active=True, company_id=COMPANY_ID),
        )
        if created:
            for seq, abbr in [(10, "BASIC"), (20, "HOUSE"), (30, "TRANS"), (40, "OT")]:
                SalaryStructureComponent.objects.get_or_create(
                    structure=senior, component=components[abbr],
                    defaults={"sequence": seq, "company_id": COMPANY_ID},
                )
            self.stdout.write("  Created SalaryStructure: Senior Staff")
        structures["senior"] = senior

        return structures

    # ── Employees ────────────────────────────────────────────────────────────

    def _seed_employees(self):
        from apps.hrm.models import Department, Employee

        dept, _ = Department.objects.get_or_create(
            name="Operations",
            defaults={"company_id": COMPANY_ID},
        )

        specs = [
            dict(first_name="Alex", last_name="Mensah", employee_number="EMP-001", email="alex.mensah@company.com"),
            dict(first_name="Efua", last_name="Boateng", employee_number="EMP-002", email="efua.boateng@company.com"),
            dict(first_name="Kojo", last_name="Asante", employee_number="EMP-003", email="kojo.asante@company.com"),
            dict(first_name="Abena", last_name="Osei", employee_number="EMP-004", email="abena.osei@company.com"),
            dict(first_name="Kwame", last_name="Darko", employee_number="EMP-005", email="kwame.darko@company.com"),
        ]

        employees = []
        for s in specs:
            emp, created = Employee.objects.get_or_create(
                employee_number=s["employee_number"],
                defaults={
                    **s,
                    "department": dept,
                    "status": "active",
                    "date_of_joining": _d(2023, 1, 1),
                    "company_id": COMPANY_ID,
                },
            )
            if created:
                self.stdout.write("  Created Employee: {} {}".format(emp.first_name, emp.last_name))
            employees.append(emp)
        return employees

    # ── Salary Assignments ───────────────────────────────────────────────────

    def _seed_assignments(self, employees, structures):
        from apps.payroll.models import SalaryStructureAssignment

        # Base salaries (GHS/month)
        assignments = [
            (employees[0], structures["standard"], Decimal("3500.00")),  # Alex
            (employees[1], structures["standard"], Decimal("4200.00")),  # Efua
            (employees[2], structures["senior"],   Decimal("6000.00")),  # Kojo
            (employees[3], structures["standard"], Decimal("2800.00")),  # Abena
            (employees[4], structures["senior"],   Decimal("8500.00")),  # Kwame
        ]

        for emp, struct, base in assignments:
            asgn, created = SalaryStructureAssignment.objects.get_or_create(
                employee=emp,
                structure=struct,
                defaults=dict(
                    base_salary=base,
                    currency="GHS",
                    effective_from=_d(2025, 1, 1),
                    company_id=COMPANY_ID,
                ),
            )
            if created:
                self.stdout.write("  Assigned {} → {} @ GHS {}/mo".format(
                    emp.first_name, struct.name, base
                ))

    # ── Payroll Periods ──────────────────────────────────────────────────────

    def _seed_periods(self):
        from apps.payroll.models import PayrollPeriod

        period_specs = [
            ("April 2025",    _d(2025, 4, 1), _d(2025, 4, 30), "closed"),
            ("May 2025",      _d(2025, 5, 1), _d(2025, 5, 31), "closed"),
            ("June 2025",     _d(2025, 6, 1), _d(2025, 6, 30), "active"),
            ("July 2025",     _d(2025, 7, 1), _d(2025, 7, 31), "draft"),
        ]

        periods = []
        for name, start, end, status in period_specs:
            p, created = PayrollPeriod.objects.get_or_create(
                name=name,
                defaults=dict(
                    start_date=start,
                    end_date=end,
                    frequency="monthly",
                    status=status,
                    company_id=COMPANY_ID,
                ),
            )
            if created:
                self.stdout.write("  Created PayrollPeriod: {}".format(name))
            periods.append(p)

        return periods

    # ── Payroll Entries ──────────────────────────────────────────────────────

    def _seed_payroll_entries(self, periods, pack):
        from apps.payroll.hooks.payroll_entry import compute_salary_slips, verify_slips
        from apps.payroll.models import PayrollEntry

        april, may, june, july = periods

        # April — submitted (historical)
        if not PayrollEntry.objects.filter(payroll_number="PAYROLL-00001").exists():
            e1 = PayrollEntry.objects.create(
                payroll_number="PAYROLL-00001",
                period=april,
                run_type=PayrollEntry.RunType.REGULAR,
                status=PayrollEntry.Status.DRAFT,
                currency="GHS",
                statutory_pack=pack,
                notes="April 2025 regular payroll",
                company_id=COMPANY_ID,
            )
            compute_salary_slips(e1)
            verify_slips(e1)
            e1.status = PayrollEntry.Status.SUBMITTED
            e1.save(update_fields=["status"])
            self.stdout.write("  Created PayrollEntry: PAYROLL-00001 [submitted] — April 2025, {} slips".format(
                e1.salary_slips.count()
            ))

        # May — submitted
        if not PayrollEntry.objects.filter(payroll_number="PAYROLL-00002").exists():
            e2 = PayrollEntry.objects.create(
                payroll_number="PAYROLL-00002",
                period=may,
                run_type=PayrollEntry.RunType.REGULAR,
                status=PayrollEntry.Status.DRAFT,
                currency="GHS",
                statutory_pack=pack,
                notes="May 2025 regular payroll",
                company_id=COMPANY_ID,
            )
            compute_salary_slips(e2)
            verify_slips(e2)
            e2.status = PayrollEntry.Status.SUBMITTED
            e2.save(update_fields=["status"])
            self.stdout.write("  Created PayrollEntry: PAYROLL-00002 [submitted] — May 2025, {} slips".format(
                e2.salary_slips.count()
            ))

        # June — processing (slips computed, awaiting manager sign-off)
        if not PayrollEntry.objects.filter(payroll_number="PAYROLL-00003").exists():
            e3 = PayrollEntry.objects.create(
                payroll_number="PAYROLL-00003",
                period=june,
                run_type=PayrollEntry.RunType.REGULAR,
                status=PayrollEntry.Status.DRAFT,
                currency="GHS",
                statutory_pack=pack,
                notes="June 2025 regular payroll",
                company_id=COMPANY_ID,
            )
            compute_salary_slips(e3)
            e3.status = PayrollEntry.Status.PROCESSING
            e3.save(update_fields=["status"])
            self.stdout.write("  Created PayrollEntry: PAYROLL-00003 [processing] — June 2025, {} slips".format(
                e3.salary_slips.count()
            ))

        # July — draft bonus run
        if not PayrollEntry.objects.filter(payroll_number="PAYROLL-BONUS-001").exists():
            PayrollEntry.objects.create(
                payroll_number="PAYROLL-BONUS-001",
                period=july,
                run_type=PayrollEntry.RunType.BONUS,
                status=PayrollEntry.Status.DRAFT,
                currency="GHS",
                notes="Q2 performance bonus run — off-cycle",
                company_id=COMPANY_ID,
            )
            self.stdout.write("  Created PayrollEntry: PAYROLL-BONUS-001 [draft] — July 2025 bonus")

    # ── Employee Loans ────────────────────────────────────────────────────────

    def _seed_loans(self, employees, periods):
        from apps.payroll.hooks.loan import generate_repayment_schedule
        from apps.payroll.models import EmployeeLoan, LoanRepaymentSchedule

        april, may, june, july = periods
        kojo = employees[2]  # Kojo — senior staff
        abena = employees[3]  # Abena

        # Loan 1: Kojo — GHS 12,000 car loan, 12 months @ 10% p.a., active (3 already deducted)
        loan1, created = EmployeeLoan.objects.get_or_create(
            loan_number="LOAN-00001",
            defaults=dict(
                employee=kojo,
                loan_type="loan",
                principal_amount=Decimal("12000.00"),
                interest_rate=Decimal("10.00"),
                repayment_periods=12,
                currency="GHS",
                disbursement_date=_d(2025, 2, 28),
                repayment_start_period=april,
                status=EmployeeLoan.Status.DRAFT,
                purpose="Vehicle purchase",
                company_id=COMPANY_ID,
            ),
        )
        if created:
            generate_repayment_schedule(loan1)
            loan1.status = EmployeeLoan.Status.ACTIVE
            loan1.save(update_fields=["status"])
            # Mark first 3 installments as deducted (April, May, June payrolls)
            for installment in LoanRepaymentSchedule.objects.filter(
                loan=loan1, installment_no__lte=3
            ):
                installment.status = LoanRepaymentSchedule.Status.DEDUCTED
                installment.deducted_on = _d(2025, installment.installment_no + 3, 30)
                installment.save(update_fields=["status", "deducted_on"])
            # Recalculate outstanding balance
            paid = LoanRepaymentSchedule.objects.filter(
                loan=loan1, status=LoanRepaymentSchedule.Status.DEDUCTED
            ).aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("total_amount"))["total"] or 0
            loan1.outstanding_balance = loan1.total_repayable - Decimal(str(paid))
            loan1.save(update_fields=["outstanding_balance"])
            self.stdout.write("  Created Loan: LOAN-00001 [active] — Kojo GHS 12,000 @ 10% (3/12 deducted)")

        # Loan 2: Abena — GHS 2,000 salary advance, 5 months, no interest, settled
        loan2, created = EmployeeLoan.objects.get_or_create(
            loan_number="LOAN-00002",
            defaults=dict(
                employee=abena,
                loan_type="advance",
                principal_amount=Decimal("2000.00"),
                interest_rate=Decimal("0"),
                repayment_periods=5,
                currency="GHS",
                disbursement_date=_d(2024, 10, 31),
                status=EmployeeLoan.Status.DRAFT,
                purpose="Emergency medical expenses",
                company_id=COMPANY_ID,
            ),
        )
        if created:
            generate_repayment_schedule(loan2)
            loan2.status = EmployeeLoan.Status.SETTLED
            loan2.outstanding_balance = Decimal("0")
            loan2.save(update_fields=["status", "outstanding_balance"])
            LoanRepaymentSchedule.objects.filter(loan=loan2).update(
                status=LoanRepaymentSchedule.Status.DEDUCTED
            )
            self.stdout.write("  Created Loan: LOAN-00002 [settled] — Abena GHS 2,000 advance (fully recovered)")
