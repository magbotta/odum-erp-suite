"""Payroll models (§6.5): salary structures, payroll runs, payslips, loans, statutory packs."""
from __future__ import annotations

from django.db import models

from apps.hrm.models import Employee
from core.metadata_engine.base_entity import BaseEntity


class SalaryComponent(BaseEntity):
    """
    A single earnings, deduction, or benefit item used in salary structures (§6.5).
    Amount is either a fixed value or computed via a Python formula string.
    """

    class ComponentType(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"
        BENEFIT = "benefit", "Benefit"

    name = models.CharField(max_length=100, unique=True)
    abbr = models.CharField(max_length=10, blank=True)
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    is_tax = models.BooleanField(default=False)
    is_statutory = models.BooleanField(default=False, help_text="e.g. social security, pension")
    is_based_on_formula = models.BooleanField(default=False)
    formula = models.TextField(
        blank=True,
        help_text="Python expression; can reference 'base', 'gross', and other component abbrs",
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    description = models.TextField(blank=True)
    # Cross-app: GL accounts for payroll posting
    payroll_account_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_salary_components"

    def __str__(self) -> str:
        return self.name


class SalaryStructure(BaseEntity):
    """A named set of salary components for a grade/employment type (§6.5)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_salary_structures"

    def __str__(self) -> str:
        return self.name


class SalaryStructureComponent(BaseEntity):
    """Ordered link between a SalaryStructure and a SalaryComponent."""

    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.CASCADE, related_name="components"
    )
    component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, related_name="structure_links"
    )
    sequence = models.PositiveSmallIntegerField(default=0)
    # Override the component's amount for this specific structure
    amount_override = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        help_text="Override component amount for this structure; null = use component default",
    )

    class Meta(BaseEntity.Meta):
        db_table = "payroll_structure_components"
        ordering = ["structure", "sequence"]
        unique_together = [("structure", "component")]

    def __str__(self) -> str:
        return f"{self.structure} → {self.component}"


class SalaryStructureAssignment(BaseEntity):
    """Assigns a salary structure + base salary to an employee from a date (§6.5)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="salary_assignments")
    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.PROTECT, related_name="assignments"
    )
    base_salary = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_structure_assignments"

    def __str__(self) -> str:
        return f"{self.employee} — {self.structure} from {self.effective_from}"


class PayrollPeriod(BaseEntity):
    """A payroll period (monthly, bi-weekly, etc.) that payroll runs are attached to (§6.5)."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        SEMI_MONTHLY = "semi_monthly", "Semi-Monthly"
        BIWEEKLY = "biweekly", "Bi-Weekly"
        WEEKLY = "weekly", "Weekly"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=100, help_text="e.g. January 2026")
    start_date = models.DateField()
    end_date = models.DateField()
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_periods"

    def __str__(self) -> str:
        return self.name


class PayrollEntry(BaseEntity):
    """
    A single payroll run for a set of employees in a period (§6.5).
    Computing it creates one SalarySlip per employee.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    class RunType(models.TextChoices):
        REGULAR = "regular", "Regular"
        BONUS = "bonus", "Bonus / Off-Cycle"
        CORRECTION = "correction", "Correction"

    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payroll_entries")
    payroll_number = models.CharField(max_length=50, blank=True, db_index=True)
    run_type = models.CharField(max_length=20, choices=RunType.choices, default=RunType.REGULAR)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_gross_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_deductions = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_net_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_loan_deductions = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Cross-app: GL journal entry created on submission
    journal_entry_id = models.UUIDField(null=True, blank=True)
    # Statutory pack applied to this run
    statutory_pack = models.ForeignKey(
        "StatutoryPack", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payroll_entries",
    )
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_entries"
        verbose_name = "Payroll Entry"
        verbose_name_plural = "Payroll Entries"

    def __str__(self) -> str:
        return self.payroll_number or f"PAYROLL/{self.period}"


class SalarySlip(BaseEntity):
    """
    A computed payslip for one employee in one payroll run (§6.5).
    Components are stored in SalarySlipComponent for full audit trail.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    payroll_entry = models.ForeignKey(
        PayrollEntry, on_delete=models.CASCADE, related_name="salary_slips"
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="salary_slips")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="salary_slips")
    structure = models.ForeignKey(
        SalaryStructure, null=True, on_delete=models.SET_NULL, related_name="salary_slips"
    )
    slip_number = models.CharField(max_length=50, blank=True)
    total_working_days = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    actual_working_days = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    base_salary = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Attendance-sourced hours (§6.4 cross-app)
    working_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    shift_differential_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Loan deduction applied this period
    loan_deduction_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    gross_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_deduction = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    net_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_salary_slips"
        unique_together = [("payroll_entry", "employee")]

    def __str__(self) -> str:
        return f"{self.slip_number or 'SLIP'} — {self.employee}"


class SalarySlipComponent(BaseEntity):
    """One computed component line on a SalarySlip (immutable once submitted)."""

    slip = models.ForeignKey(SalarySlip, on_delete=models.CASCADE, related_name="components")
    salary_component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, related_name="slip_components"
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_slip_components"

    def __str__(self) -> str:
        return "{} = {}".format(self.salary_component, self.amount)


# ── Statutory Compliance Packs ───────────────────────────────────────────────

class StatutoryPack(BaseEntity):
    """
    A country/jurisdiction-level compliance pack defining tax, social security,
    and pension rules (§6.5 statutory compliance packs as installable Apps).
    Stored as structured data rather than code so operators can maintain them
    without a code deployment.
    """

    class BracketMethod(models.TextChoices):
        CUMULATIVE = "cumulative", "Cumulative (standard PAYE)"
        FLAT_RATE = "flat_rate", "Flat Rate"
        TIERED = "tiered", "Tiered / Progressive"

    country_code = models.CharField(max_length=3, db_index=True, help_text="ISO 3166-1 alpha-2 or alpha-3")
    country_name = models.CharField(max_length=100)
    name = models.CharField(max_length=150, help_text="e.g. Ghana PAYE + SSNIT 2025")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_statutory_packs"

    def __str__(self) -> str:
        return self.name


class StatutoryRule(BaseEntity):
    """
    A single statutory deduction rule within a StatutoryPack
    (e.g., Employee SSNIT 5.5%, Employer SSNIT 13%, PAYE bracket).
    """

    class RuleType(models.TextChoices):
        EMPLOYEE_CONTRIBUTION = "employee", "Employee Contribution"
        EMPLOYER_CONTRIBUTION = "employer", "Employer Contribution"
        INCOME_TAX = "income_tax", "Income Tax (PAYE)"

    class CalcMethod(models.TextChoices):
        FIXED_RATE = "fixed_rate", "Fixed Rate % of gross"
        BRACKET = "bracket", "Bracket / Progressive"
        FLAT_AMOUNT = "flat_amount", "Flat Amount"
        FIXED_RATE_OF_BASE = "fixed_rate_of_base", "Fixed Rate % of base salary"

    pack = models.ForeignKey(StatutoryPack, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=100)
    abbr = models.CharField(max_length=20, blank=True)
    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    calc_method = models.CharField(max_length=30, choices=CalcMethod.choices)
    rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=0,
        help_text="Percentage rate (e.g. 5.5 for 5.5%) — used when calc_method is fixed_rate",
    )
    # JSONB brackets for progressive tax: [{min: 0, max: 3000, rate: 0}, {min: 3001, rate: 15}, ...]
    brackets = models.JSONField(default=list, blank=True)
    cap_amount = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Max deduction per period (0 = no cap)",
    )
    applies_to_component = models.ForeignKey(
        SalaryComponent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="statutory_rules",
        help_text="If set, rule operates on this component's amount rather than gross",
    )
    sequence = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_statutory_rules"
        ordering = ["pack", "sequence"]

    def __str__(self) -> str:
        return "{} ({})".format(self.name, self.pack)

    def compute(self, gross: "Decimal", base: "Decimal") -> "Decimal":
        """Return the computed deduction amount for a given gross / base salary."""
        from decimal import Decimal as D

        if self.calc_method == self.CalcMethod.FIXED_RATE:
            amount = (gross * self.rate / D("100")).quantize(D("0.01"))
        elif self.calc_method == self.CalcMethod.FIXED_RATE_OF_BASE:
            amount = (base * self.rate / D("100")).quantize(D("0.01"))
        elif self.calc_method == self.CalcMethod.FLAT_AMOUNT:
            amount = D(str(self.rate))
        elif self.calc_method == self.CalcMethod.BRACKET:
            amount = _apply_bracket(gross, self.brackets)
        else:
            amount = D("0")

        if self.cap_amount and self.cap_amount > 0:
            amount = min(amount, self.cap_amount)
        return amount


def _apply_bracket(gross, brackets):
    """Progressive bracket tax calculation."""
    from decimal import Decimal as D

    tax = D("0")
    for band in sorted(brackets, key=lambda b: b.get("min", 0)):
        lo = D(str(band.get("min", 0)))
        hi = D(str(band["max"])) if "max" in band else None
        rate = D(str(band.get("rate", 0))) / D("100")
        if gross <= lo:
            break
        taxable = (min(gross, hi) if hi else gross) - lo
        tax += taxable * rate
    return tax.quantize(D("0.01"))


# ── Employee Loans & Advances ────────────────────────────────────────────────

class EmployeeLoan(BaseEntity):
    """
    A salary advance or formal loan to an employee, recovered by automatic
    deduction across future SalarySlips (§6.5 loans/advances with deduction
    scheduling).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        DISBURSED = "disbursed", "Disbursed"
        ACTIVE = "active", "Active (recovering)"
        SETTLED = "settled", "Settled"
        CANCELLED = "cancelled", "Cancelled"

    loan_number = models.CharField(max_length=30, blank=True, db_index=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="loans")
    loan_type = models.CharField(
        max_length=20,
        choices=[("advance", "Salary Advance"), ("loan", "Formal Loan")],
        default="loan",
    )
    principal_amount = models.DecimalField(max_digits=19, decimal_places=4)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Annual interest rate % (0 for interest-free advances)",
    )
    repayment_periods = models.PositiveSmallIntegerField(
        help_text="Number of payroll periods over which to recover the loan",
    )
    monthly_installment = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_repayable = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    outstanding_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    disbursement_date = models.DateField(null=True, blank=True)
    repayment_start_period = models.ForeignKey(
        PayrollPeriod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_starts",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_employee_loans"

    def __str__(self) -> str:
        return self.loan_number or "Loan/{}".format(self.employee)


class LoanRepaymentSchedule(BaseEntity):
    """
    One installment row in a loan repayment schedule.
    Linked to a SalarySlip once the deduction is applied.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DEDUCTED = "deducted", "Deducted"
        WAIVED = "waived", "Waived"

    loan = models.ForeignKey(EmployeeLoan, on_delete=models.CASCADE, related_name="schedule")
    installment_no = models.PositiveSmallIntegerField()
    period = models.ForeignKey(
        PayrollPeriod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_installments",
    )
    principal_component = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    interest_component = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_amount = models.DecimalField(max_digits=19, decimal_places=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Soft link to the SalarySlip that carried this deduction
    salary_slip_id = models.UUIDField(null=True, blank=True)
    deducted_on = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "payroll_loan_repayment_schedule"
        ordering = ["loan", "installment_no"]

    def __str__(self) -> str:
        return "Installment {} of {}".format(self.installment_no, self.loan)
