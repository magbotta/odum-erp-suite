"""
Microfinance / Financial Services models (§7.1).
Loan/savings products, group lending, KYC/AML, teller cash management.
Depends on: Accounting (GL posting), CRM (borrower accounts), HRM (loan officers), AI (credit scoring).
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class LoanProduct(BaseEntity):
    """
    A configurable loan product with interest type and repayment settings (§7.1).
    """

    class InterestType(models.TextChoices):
        FLAT = "flat", "Flat Rate"
        DECLINING = "declining", "Declining Balance"
        REDUCING = "reducing", "Reducing Balance (Actuarial)"

    class RepaymentFrequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Bi-Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        BULLET = "bullet", "Bullet (Lump Sum)"

    name = models.CharField(max_length=255)
    product_code = models.CharField(max_length=20, blank=True)
    interest_type = models.CharField(
        max_length=20, choices=InterestType.choices, default=InterestType.DECLINING
    )
    annual_interest_rate = models.DecimalField(max_digits=7, decimal_places=4)
    repayment_frequency = models.CharField(
        max_length=20, choices=RepaymentFrequency.choices, default=RepaymentFrequency.MONTHLY
    )
    min_loan_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    max_loan_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    min_term_periods = models.PositiveSmallIntegerField(default=1)
    max_term_periods = models.PositiveSmallIntegerField(default=24)
    grace_period_periods = models.PositiveSmallIntegerField(default=0)
    processing_fee_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    late_penalty_rate = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    is_group_loan = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_loan_products"

    def __str__(self) -> str:
        return self.name


class SavingsProduct(BaseEntity):
    """A savings account product with interest rate and compounding rules (§7.1)."""

    class CompoundingFrequency(models.TextChoices):
        DAILY = "daily", "Daily"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUALLY = "annually", "Annually"

    name = models.CharField(max_length=255)
    product_code = models.CharField(max_length=20, blank=True)
    annual_interest_rate = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    compounding_frequency = models.CharField(
        max_length=20, choices=CompoundingFrequency.choices, default=CompoundingFrequency.MONTHLY
    )
    minimum_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    withdrawal_fee = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_savings_products"

    def __str__(self) -> str:
        return self.name


class LendingGroup(BaseEntity):
    """
    A solidarity / joint-liability group for group lending (§7.1).
    Members guarantee each other's loans.
    """

    name = models.CharField(max_length=255)
    group_number = models.CharField(max_length=50, blank=True, db_index=True)
    meeting_day = models.CharField(max_length=20, blank=True)
    meeting_location = models.TextField(blank=True)
    meeting_geojson = models.JSONField(null=True, blank=True)
    loan_officer_employee_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    formation_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_lending_groups"

    def __str__(self) -> str:
        return self.name


class Borrower(BaseEntity):
    """
    A microfinance client / borrower. May belong to a LendingGroup.
    Cross-app: CRM Account/Contact for relationship management.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        BLACKLISTED = "blacklisted", "Blacklisted"

    borrower_number = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    national_id = models.CharField(max_length=50, blank=True)  # encrypted in prod (§13)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    lending_group = models.ForeignKey(
        LendingGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="members",
    )
    credit_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    kyc_verified = models.BooleanField(default=False)
    crm_account_id = models.UUIDField(null=True, blank=True)
    registration_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_borrowers"

    def __str__(self) -> str:
        return f"{self.borrower_number} — {self.first_name} {self.last_name}"


class LoanAccount(BaseEntity):
    """
    An active loan account for a Borrower (§7.1).
    Amortization schedule is stored in LoanRepaymentSchedule rows.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active / Disbursed"
        DELINQUENT = "delinquent", "Delinquent"
        WRITTEN_OFF = "written_off", "Written Off"
        CLOSED = "closed", "Closed / Paid Off"

    loan_number = models.CharField(max_length=50, unique=True, db_index=True)
    borrower = models.ForeignKey(Borrower, on_delete=models.PROTECT, related_name="loans")
    product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name="loans")
    lending_group = models.ForeignKey(
        LendingGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loans",
    )
    principal_amount = models.DecimalField(max_digits=19, decimal_places=4)
    outstanding_principal = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    accrued_interest = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_repaid = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    disbursement_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    term_periods = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    loan_officer_employee_id = models.UUIDField(null=True, blank=True)
    # Cross-app: Accounting GL entries
    loan_account_gl_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_loan_accounts"

    def __str__(self) -> str:
        return self.loan_number


class LoanRepaymentSchedule(BaseEntity):
    """One installment row in the amortization schedule for a LoanAccount (§7.1)."""

    loan = models.ForeignKey(
        LoanAccount, on_delete=models.CASCADE, related_name="schedule"
    )
    period_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    principal_due = models.DecimalField(max_digits=19, decimal_places=4)
    interest_due = models.DecimalField(max_digits=19, decimal_places=4)
    total_due = models.DecimalField(max_digits=19, decimal_places=4)
    principal_paid = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    interest_paid = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    is_paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_repayment_schedule"
        ordering = ["loan", "period_number"]

    def __str__(self) -> str:
        return f"{self.loan} — Period {self.period_number} ({self.due_date})"


class SavingsAccount(BaseEntity):
    """A savings account for an individual borrower or group (§7.1)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DORMANT = "dormant", "Dormant"
        CLOSED = "closed", "Closed"

    account_number = models.CharField(max_length=50, unique=True, db_index=True)
    borrower = models.ForeignKey(
        Borrower, null=True, blank=True, on_delete=models.PROTECT, related_name="savings_accounts"
    )
    lending_group = models.ForeignKey(
        LendingGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="savings_accounts",
    )
    product = models.ForeignKey(SavingsProduct, on_delete=models.PROTECT, related_name="accounts")
    balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    opened_date = models.DateField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_savings_accounts"

    def __str__(self) -> str:
        return self.account_number


class KYCDocument(BaseEntity):
    """
    An identity / compliance document submitted for KYC/AML verification (§7.1).
    document_data is PHI — encrypted in production (§13).
    """

    class DocumentType(models.TextChoices):
        NATIONAL_ID = "national_id", "National ID"
        PASSPORT = "passport", "Passport"
        DRIVERS_LICENSE = "drivers_license", "Driver's License"
        UTILITY_BILL = "utility_bill", "Utility Bill"
        OTHER = "other", "Other"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    borrower = models.ForeignKey(Borrower, on_delete=models.CASCADE, related_name="kyc_documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    document_number = models.CharField(max_length=100, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    issuing_authority = models.CharField(max_length=255, blank=True)
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    verified_by_employee_id = models.UUIDField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # File stored in object storage; path/URL here
    document_file_path = models.CharField(max_length=500, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_kyc_documents"
        verbose_name = "KYC Document"

    def __str__(self) -> str:
        return f"{self.borrower} — {self.document_type}"


class TellerTransaction(BaseEntity):
    """
    A teller / cash-desk transaction: disbursement, repayment collection, or savings deposit/withdrawal.
    Branch cash-in/cash-out with end-of-day till reconciliation (§7.1).
    """

    class TransactionType(models.TextChoices):
        LOAN_DISBURSEMENT = "loan_disbursement", "Loan Disbursement"
        LOAN_REPAYMENT = "loan_repayment", "Loan Repayment"
        SAVINGS_DEPOSIT = "savings_deposit", "Savings Deposit"
        SAVINGS_WITHDRAWAL = "savings_withdrawal", "Savings Withdrawal"
        FEE_COLLECTION = "fee_collection", "Fee Collection"
        CASH_IN = "cash_in", "Cash In (Teller)"
        CASH_OUT = "cash_out", "Cash Out (Teller)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REVERSED = "reversed", "Reversed"

    transaction_number = models.CharField(max_length=50, blank=True, db_index=True)
    transaction_type = models.CharField(max_length=25, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    teller_employee_id = models.UUIDField(null=True, blank=True)
    loan_account = models.ForeignKey(
        LoanAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="teller_transactions",
    )
    savings_account = models.ForeignKey(
        SavingsAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="teller_transactions",
    )
    payment_method = models.CharField(max_length=30, default="cash")
    mobile_reference = models.CharField(max_length=100, blank=True)
    # Cross-app: Accounting journal entry
    journal_entry_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "mfi_teller_transactions"

    def __str__(self) -> str:
        return f"{self.transaction_number} — {self.transaction_type} {self.amount}"
