"""
Accounting models (§6.1): Chart of Accounts, Journal Entries, Customer/Vendor,
Sales Invoices, Bills, Payments, Bank Accounts.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class ChartOfAccount(BaseEntity):
    """
    General Ledger account node (§6.1).
    Supports hierarchical (group/leaf) chart of accounts per company.
    """

    class AccountType(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    account_number = models.CharField(max_length=30, blank=True, db_index=True)
    account_name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    is_group = models.BooleanField(default=False)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_chart_of_accounts"
        verbose_name = "Chart of Account"
        verbose_name_plural = "Chart of Accounts"

    def __str__(self) -> str:
        if self.account_number:
            return f"{self.account_number} — {self.account_name}"
        return self.account_name


class CostCenter(BaseEntity):
    """Cross-cutting dimension for departmental / project cost reporting (§6.1)."""

    name = models.CharField(max_length=150)
    cost_center_number = models.CharField(max_length=20, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    is_group = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_cost_centers"

    def __str__(self) -> str:
        return self.name


class Customer(BaseEntity):
    """AR customer master (§6.1). May be linked to a CRM Account."""

    class CustomerType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        COMPANY = "company", "Company"

    customer_name = models.CharField(max_length=255, db_index=True)
    customer_type = models.CharField(
        max_length=20, choices=CustomerType.choices, default=CustomerType.COMPANY
    )
    tax_id = models.CharField(max_length=50, blank=True)
    credit_limit = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    payment_terms = models.CharField(max_length=50, blank=True, help_text="e.g. Net 30")
    default_currency = models.CharField(max_length=3, default="USD")
    billing_address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    # Soft link to CRM Account — no Django FK to avoid cross-app coupling
    crm_account_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_customers"

    def __str__(self) -> str:
        return self.customer_name


class Vendor(BaseEntity):
    """AP vendor master (§6.1)."""

    vendor_name = models.CharField(max_length=255, db_index=True)
    vendor_type = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    payment_terms = models.CharField(max_length=50, blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    billing_address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_vendors"

    def __str__(self) -> str:
        return self.vendor_name


class JournalEntry(BaseEntity):
    """
    A double-entry bookkeeping entry (§6.1).
    Lines must balance (sum of debits == sum of credits).
    """

    class EntryType(models.TextChoices):
        JOURNAL = "journal", "Journal Entry"
        OPENING = "opening", "Opening Entry"
        DEPRECIATION = "depreciation", "Depreciation"
        BANK_RECONCILIATION = "bank_reconciliation", "Bank Reconciliation"
        INTER_COMPANY = "inter_company", "Inter-Company Entry"
        REVERSAL = "reversal", "Reversal"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    entry_type = models.CharField(max_length=30, choices=EntryType.choices, default=EntryType.JOURNAL)
    posting_date = models.DateField(db_index=True)
    reference = models.CharField(max_length=100, blank=True)
    narration = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_debit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_credit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    # Voucher linkage
    voucher_type = models.CharField(max_length=50, blank=True)
    voucher_no = models.CharField(max_length=100, blank=True, db_index=True)
    is_reversed = models.BooleanField(default=False)
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reversals"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submitted_journal_entries",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_journal_entries"
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"

    def __str__(self) -> str:
        return f"JE/{self.posting_date}/{self.pk}"


class JournalEntryLine(BaseEntity):
    """One debit or credit leg of a JournalEntry (§6.1)."""

    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name="journal_lines")
    cost_center = models.ForeignKey(
        CostCenter, null=True, blank=True, on_delete=models.SET_NULL, related_name="journal_lines"
    )
    debit_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    credit_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    # Party (customer/vendor/employee) for AR/AP lines
    party_type = models.CharField(max_length=30, blank=True, help_text="Customer / Vendor / Employee")
    party_id = models.UUIDField(null=True, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_journal_entry_lines"

    def __str__(self) -> str:
        if self.debit_amount:
            return f"Dr {self.account} {self.debit_amount}"
        return f"Cr {self.account} {self.credit_amount}"


class SalesInvoice(BaseEntity):
    """
    A customer invoice (§6.1 AR).
    Automatically posts a JournalEntry on submission.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PAID = "paid", "Paid"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=50, blank=True, db_index=True)
    posting_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    outstanding_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    # GL entry created on submit
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_invoices"
    )
    # Cross-app soft link: originating Sales Order
    sales_order_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_sales_invoices"
        verbose_name = "Sales Invoice"
        verbose_name_plural = "Sales Invoices"

    def __str__(self) -> str:
        return self.invoice_number or f"INV-{self.pk}"


class SalesInvoiceItem(BaseEntity):
    """A line item on a SalesInvoice."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="items")
    # Cross-app soft link to Warehouse Item
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100, blank=True)
    item_description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    income_account = models.ForeignKey(
        ChartOfAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales_invoice_items",
    )

    class Meta(BaseEntity.Meta):
        db_table = "accounting_sales_invoice_items"

    def __str__(self) -> str:
        return f"{self.item_description} × {self.qty}"


class PurchaseBill(BaseEntity):
    """A vendor bill / AP invoice (§6.1)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PAID = "paid", "Paid"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")
    bill_number = models.CharField(max_length=50, blank=True)
    vendor_invoice_number = models.CharField(max_length=100, blank=True, help_text="Vendor's own invoice ref")
    posting_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    outstanding_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_bills"
    )
    purchase_order_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_purchase_bills"
        verbose_name = "Purchase Bill"
        verbose_name_plural = "Purchase Bills"

    def __str__(self) -> str:
        return self.bill_number or f"BILL-{self.pk}"


class Payment(BaseEntity):
    """A receipt from a customer or payment to a vendor (§6.1, §11)."""

    class PaymentType(models.TextChoices):
        RECEIVE = "receive", "Receive"
        PAY = "pay", "Pay"
        INTERNAL_TRANSFER = "internal_transfer", "Internal Transfer"

    class PartyType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        VENDOR = "vendor", "Vendor"

    class Mode(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CARD = "card", "Card"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    party_type = models.CharField(max_length=20, choices=PartyType.choices)
    party_id = models.UUIDField(db_index=True)
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=6, default=1)
    mode_of_payment = models.CharField(max_length=20, choices=Mode.choices, default=Mode.BANK_TRANSFER)
    reference_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    gateway_reference = models.CharField(max_length=200, blank=True, help_text="Payment gateway transaction ID")
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )

    class Meta(BaseEntity.Meta):
        db_table = "accounting_payments"

    def __str__(self) -> str:
        return f"{self.payment_type} {self.amount} {self.currency} [{self.payment_date}]"


# ---------------------------------------------------------------------------
# New models added in full implementation (§6.1)
# ---------------------------------------------------------------------------


class PurchaseBillItem(BaseEntity):
    """Line item on a PurchaseBill."""

    bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=19, decimal_places=4, default=1)
    rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    expense_account = models.ForeignKey(
        ChartOfAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="purchase_bill_items",
    )

    class Meta(BaseEntity.Meta):
        db_table = "accounting_purchase_bill_items"

    def __str__(self) -> str:
        return f"{self.description} × {self.qty}"


class BankAccount(BaseEntity):
    """A company bank account used for reconciliation (§6.1 Banking)."""

    class BankAccountType(models.TextChoices):
        SAVINGS = "savings", "Savings"
        CURRENT = "current", "Current"
        OVERDRAFT = "overdraft", "Overdraft"

    account_name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=100, blank=True, help_text="Masked account number")
    iban = models.CharField(max_length=34, blank=True)
    swift_bic = models.CharField(max_length=11, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    bank_account_type = models.CharField(
        max_length=20, choices=BankAccountType.choices, default=BankAccountType.CURRENT
    )
    linked_gl_account = models.ForeignKey(
        ChartOfAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bank_accounts",
    )
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_bank_accounts"
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"

    def __str__(self) -> str:
        return f"{self.account_name} ({self.bank_name})"


class BankTransaction(BaseEntity):
    """A single transaction on a BankAccount feed (§6.1 Banking)."""

    class TransactionType(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="transactions")
    transaction_date = models.DateField(db_index=True)
    description = models.CharField(max_length=500)
    debit_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    credit_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    running_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    reference = models.CharField(max_length=100, blank=True)
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    is_reconciled = models.BooleanField(default=False)
    reconciled_je = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reconciled_bank_transactions",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_bank_transactions"
        verbose_name = "Bank Transaction"
        verbose_name_plural = "Bank Transactions"

    def __str__(self) -> str:
        return f"{self.transaction_date} {self.description} {self.debit_amount or self.credit_amount}"


class FiscalYear(BaseEntity):
    """A fiscal/financial year for period-close control (§6.1)."""

    year_name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_fiscal_years"
        verbose_name = "Fiscal Year"
        verbose_name_plural = "Fiscal Years"

    def __str__(self) -> str:
        return self.year_name


class AccountingPeriod(BaseEntity):
    """A sub-period of a FiscalYear (e.g. a month or quarter)."""

    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods")
    period_name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_periods"
        verbose_name = "Accounting Period"
        verbose_name_plural = "Accounting Periods"

    def __str__(self) -> str:
        return f"{self.fiscal_year} / {self.period_name}"


class TaxRule(BaseEntity):
    """A tax rate / rule applicable to transactions (§6.1 Tax engine)."""

    class TaxType(models.TextChoices):
        VAT = "vat", "VAT"
        GST = "gst", "GST"
        SALES_TAX = "sales_tax", "Sales Tax"
        WITHHOLDING = "withholding", "Withholding Tax"
        OTHER = "other", "Other"

    tax_name = models.CharField(max_length=100)
    tax_type = models.CharField(max_length=20, choices=TaxType.choices)
    rate = models.DecimalField(max_digits=5, decimal_places=4, help_text="e.g. 0.1000 for 10%")
    jurisdiction = models.CharField(max_length=100, blank=True)
    account = models.ForeignKey(
        ChartOfAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tax_rules",
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_tax_rules"
        verbose_name = "Tax Rule"
        verbose_name_plural = "Tax Rules"

    def __str__(self) -> str:
        return f"{self.tax_name} ({self.rate * 100:.2f}%)"


class PaymentAllocation(BaseEntity):
    """Links a Payment to a specific SalesInvoice or PurchaseBill (§6.1 AR/AP)."""

    class InvoiceType(models.TextChoices):
        SALES_INVOICE = "SalesInvoice", "Sales Invoice"
        PURCHASE_BILL = "PurchaseBill", "Purchase Bill"

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices)
    invoice_id = models.UUIDField(db_index=True)
    allocated_amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    allocation_date = models.DateField()

    class Meta(BaseEntity.Meta):
        db_table = "accounting_payment_allocations"
        verbose_name = "Payment Allocation"
        verbose_name_plural = "Payment Allocations"

    def __str__(self) -> str:
        return f"{self.payment_id} → {self.invoice_type}/{self.invoice_id} {self.allocated_amount}"


class Budget(BaseEntity):
    """A budget plan for a fiscal year / cost centre (§6.1 Budgeting)."""

    class Status(models.TextChoices):
        DRAFT = "Draft", "Draft"
        APPROVED = "Approved", "Approved"
        ACTIVE = "Active", "Active"
        CLOSED = "Closed", "Closed"

    budget_name = models.CharField(max_length=255)
    fiscal_year = models.ForeignKey(
        FiscalYear, null=True, blank=True, on_delete=models.SET_NULL, related_name="budgets"
    )
    cost_center = models.ForeignKey(
        CostCenter, null=True, blank=True, on_delete=models.SET_NULL, related_name="budgets"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    total_budgeted = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_budgets"
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"

    def __str__(self) -> str:
        return self.budget_name


class BudgetEntry(BaseEntity):
    """A single account line in a Budget (quarterly breakdowns)."""

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="entries")
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name="budget_entries")
    q1_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    q2_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    q3_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    q4_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "accounting_budget_entries"
        verbose_name = "Budget Entry"
        verbose_name_plural = "Budget Entries"

    @property
    def annual_amount(self):
        return self.q1_amount + self.q2_amount + self.q3_amount + self.q4_amount

    def __str__(self) -> str:
        return f"{self.budget} / {self.account}"
