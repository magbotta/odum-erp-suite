"""Payroll models (§6.5): salary structures, payroll runs, payslips, GL posting."""
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

    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payroll_entries")
    payroll_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_gross_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_deductions = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_net_pay = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Cross-app: GL journal entry created on submission
    journal_entry_id = models.UUIDField(null=True, blank=True)
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
        return f"{self.salary_component} = {self.amount}"
