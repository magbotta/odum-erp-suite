"""
Legal Services models (§7.3).
Matter management, conflict checking, trust accounting, time & billing (LEDES), court deadlines.
Depends on: Project Mgmt (matters as projects), CRM (clients), Accounting (trust sub-ledger).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class MatterType(BaseEntity):
    """A category of legal matter (Litigation, Corporate M&A, Real Estate, etc.)."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True)
    billing_method = models.CharField(
        max_length=20,
        choices=[
            ("hourly", "Hourly"),
            ("flat_fee", "Flat Fee"),
            ("contingency", "Contingency"),
            ("capped", "Capped / Blended"),
        ],
        default="hourly",
    )

    class Meta(BaseEntity.Meta):
        db_table = "legal_matter_types"

    def __str__(self) -> str:
        return self.name


class Matter(BaseEntity):
    """
    A legal matter / case — extends Project Management via cross-app link (§7.3).
    Adds matter-specific fields: type, responsible attorney, adverse parties, SoL date.
    """

    class Status(models.TextChoices):
        INTAKE = "intake", "Intake"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On Hold"
        CLOSED = "closed", "Closed"
        ARCHIVED = "archived", "Archived"

    matter_number = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=500)
    matter_type = models.ForeignKey(
        MatterType, null=True, blank=True, on_delete=models.SET_NULL, related_name="matters"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INTAKE)
    # Client
    client_crm_id = models.UUIDField(db_index=True, help_text="CRM Account/Contact UUID")
    client_name = models.CharField(max_length=255)
    # Attorneys
    responsible_attorney_employee_id = models.UUIDField(null=True, blank=True)
    originating_attorney_employee_id = models.UUIDField(null=True, blank=True)
    # Dates
    opened_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)
    statute_of_limitations_date = models.DateField(null=True, blank=True)
    # Billing
    billing_method = models.CharField(
        max_length=20,
        choices=[("hourly", "Hourly"), ("flat_fee", "Flat Fee"),
                 ("contingency", "Contingency"), ("capped", "Capped")],
        default="hourly",
    )
    billing_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    budget = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Cross-app: Project record for task/timesheet tracking
    project_id = models.UUIDField(null=True, blank=True)
    # Trust account if retainer received
    trust_account = models.ForeignKey(
        "TrustAccount", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="matters",
    )
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_matters"

    def __str__(self) -> str:
        return f"{self.matter_number} — {self.name}"


class AdverseParty(BaseEntity):
    """A party adverse to the client in a Matter — checked during conflict searches (§7.3)."""

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="adverse_parties")
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=100, blank=True,
                            help_text="e.g. Defendant, Opposing Counsel, Witness")
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_adverse_parties"

    def __str__(self) -> str:
        return f"{self.matter} ⟷ {self.name}"


class ConflictCheck(BaseEntity):
    """
    A conflict-of-interest check run before opening a new matter or accepting a client (§7.3).
    Uses AI-assisted fuzzy name matching across all historical matters and adverse parties.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAR = "clear", "Clear — No Conflicts"
        CONFLICT_FOUND = "conflict_found", "Conflict Found"
        WAIVED = "waived", "Conflict Waived"

    matter = models.ForeignKey(
        Matter, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflict_checks"
    )
    search_terms = models.JSONField(help_text="List of names/entities searched")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    ran_at = models.DateTimeField(auto_now_add=True)
    ran_by_employee_id = models.UUIDField(null=True, blank=True)
    hits = models.JSONField(default=list, help_text="Matched matter/party records")
    waiver_notes = models.TextField(blank=True)
    waived_by_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_conflict_checks"

    def __str__(self) -> str:
        return f"ConflictCheck [{self.status}] for {self.matter}"


class TrustAccount(BaseEntity):
    """
    An IOLTA / client-funds trust account (§7.3).
    Entirely segregated from operating funds; per-client sub-ledger enforced by TrustLedgerEntry.
    Hard rule: no transaction may bring any client's trust balance below zero.
    """

    account_name = models.CharField(max_length=255)
    bank_account_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    current_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Cross-app: Accounting bank account for 3-way reconciliation
    accounting_bank_account_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_trust_accounts"

    def __str__(self) -> str:
        return self.account_name


class TrustLedgerEntry(BaseEntity):
    """
    An immutable per-client trust ledger entry — posted on every trust fund movement (§7.3).
    Running balance per (trust_account, matter) is maintained here for 3-way reconciliation.
    """

    class EntryType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit (Retainer / Top-Up)"
        DISBURSEMENT = "disbursement", "Disbursement to Client"
        FEE_TRANSFER = "fee_transfer", "Transfer to Operating (Earned Fees)"
        ADJUSTMENT = "adjustment", "Adjustment"

    trust_account = models.ForeignKey(
        TrustAccount, on_delete=models.PROTECT, related_name="entries"
    )
    matter = models.ForeignKey(
        Matter, on_delete=models.PROTECT, related_name="trust_entries"
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    balance_after = models.DecimalField(max_digits=19, decimal_places=4)
    entry_date = models.DateField()
    description = models.CharField(max_length=500, blank=True)
    journal_entry_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_trust_ledger_entries"

    def __str__(self) -> str:
        return f"{self.trust_account} / {self.matter} — {self.entry_type} {self.amount}"


class LegalTimeEntry(BaseEntity):
    """
    Billable / non-billable time entry for a Matter (§7.3).
    Reuses Project Timesheet entry concept but adds LEDES billing metadata.
    """

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="time_entries")
    timekeeper_employee_id = models.UUIDField(db_index=True)
    entry_date = models.DateField()
    hours = models.DecimalField(max_digits=7, decimal_places=2)
    is_billable = models.BooleanField(default=True)
    billing_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    billing_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    activity_code = models.CharField(max_length=10, blank=True,
                                     help_text="LEDES activity code (e.g. L110)")
    task_code = models.CharField(max_length=10, blank=True,
                                 help_text="LEDES task code (e.g. L100)")
    description = models.CharField(max_length=500)
    is_invoiced = models.BooleanField(default=False)
    billing_invoice_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_time_entries"

    def __str__(self) -> str:
        return f"{self.matter} — {self.hours}h [{self.entry_date}]"


class CourtDeadline(BaseEntity):
    """
    A jurisdiction-computed court or regulatory deadline for a Matter (§7.3).
    Missed deadlines are a leading malpractice risk — mandatory escalation on this model.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        MET = "met", "Met"
        MISSED = "missed", "Missed"
        EXTENDED = "extended", "Extended"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="court_deadlines")
    deadline_type = models.CharField(max_length=150,
                                     help_text="e.g. Statute of Limitations, Answer, Discovery cutoff")
    due_date = models.DateField()
    jurisdiction = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reminder_days_before = models.PositiveSmallIntegerField(default=30)
    notes = models.TextField(blank=True)
    responsible_attorney_employee_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_court_deadlines"
        ordering = ["due_date"]

    def __str__(self) -> str:
        return f"{self.matter} — {self.deadline_type} [{self.due_date}]"


class LegalDocument(BaseEntity):
    """A document attached to a Matter with version control (§7.3)."""

    class DocumentStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINAL = "final", "Final"
        EXECUTED = "executed", "Executed / Signed"
        SUPERSEDED = "superseded", "Superseded"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=500)
    document_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )
    version = models.PositiveSmallIntegerField(default=1)
    file_path = models.CharField(max_length=500, blank=True)
    uploaded_by_employee_id = models.UUIDField(null=True, blank=True)
    e_signed = models.BooleanField(default=False)
    e_sign_reference = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "legal_documents"

    def __str__(self) -> str:
        return f"{self.matter} — {self.title} v{self.version}"
