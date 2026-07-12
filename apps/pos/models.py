"""
POS / Retail models (§7.2): terminals, sessions, transactions, offline queue.
Built on Sales (order creation), Warehouse (stock), Accounting (cash reconciliation).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounting.models import Customer
from apps.warehouse.models import Item, Warehouse
from core.metadata_engine.base_entity import BaseEntity


# ---------------------------------------------------------------------------
# Store & Terminal configuration
# ---------------------------------------------------------------------------

class Store(BaseEntity):
    """A retail location that owns one or more POS terminals (§7.2)."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, blank=True, db_index=True)
    address = models.TextField(blank=True)
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pos_stores",
        help_text="Default warehouse for stock deductions at this store",
    )
    is_active = models.BooleanField(default=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_stores"

    def __str__(self) -> str:
        return self.name


class POSTerminal(BaseEntity):
    """
    A single POS till / terminal registered to a Store (§7.2).
    Tracks hardware configuration and current session state.
    """

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="terminals")
    terminal_id = models.CharField(max_length=50, unique=True, db_index=True,
                                   help_text="Physical terminal identifier (e.g. TILL-01)")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    # Printer / drawer config stored as JSON for the Device Bridge (§7.2)
    device_config = models.JSONField(default=dict, blank=True,
                                     help_text="Hardware device configuration for this terminal")

    class Meta(BaseEntity.Meta):
        db_table = "pos_terminals"

    def __str__(self) -> str:
        return f"{self.store} / {self.name}"


# ---------------------------------------------------------------------------
# POS Session (till open/close)
# ---------------------------------------------------------------------------

class POSSession(BaseEntity):
    """
    A till session: opened by a cashier, closed at end of shift with cash reconciliation.
    One session per terminal per shift (§7.2).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSING = "closing", "Closing (Reconciliation)"
        CLOSED = "closed", "Closed"

    terminal = models.ForeignKey(POSTerminal, on_delete=models.PROTECT, related_name="sessions")
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pos_sessions"
    )
    session_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    closing_cash_expected = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    closing_cash_actual = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    cash_difference = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_sales = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    total_returns = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # Cross-app: GL journal entry for daily reconciliation posting
    journal_entry_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_sessions"

    def __str__(self) -> str:
        return self.session_number or f"SESSION/{self.pk}"


# ---------------------------------------------------------------------------
# POS Transaction (a sale, return, or exchange at the till)
# ---------------------------------------------------------------------------

class POSTransaction(BaseEntity):
    """
    A single sales transaction (or return) processed at a POS terminal (§7.2).
    Immediately deducts stock from Warehouse on completion.
    """

    class TransactionType(models.TextChoices):
        SALE = "sale", "Sale"
        RETURN = "return", "Return"
        EXCHANGE = "exchange", "Exchange"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft / In Progress"
        COMPLETED = "completed", "Completed"
        VOIDED = "voided", "Voided"
        SYNCED = "synced", "Synced"  # offline transaction that has been synced

    session = models.ForeignKey(POSSession, on_delete=models.PROTECT, related_name="transactions")
    transaction_number = models.CharField(max_length=50, blank=True, db_index=True)
    transaction_type = models.CharField(
        max_length=20, choices=TransactionType.choices, default=TransactionType.SALE
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pos_transactions",
    )
    net_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    discount_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    paid_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    change_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    # For returns: the original sale being returned against
    return_against_id = models.UUIDField(null=True, blank=True)
    # Cross-app: created Sales Order / Invoice IDs
    sales_order_id = models.UUIDField(null=True, blank=True)
    sales_invoice_id = models.UUIDField(null=True, blank=True)
    # Offline support: captured offline, to be synced
    is_offline = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_transactions"

    def __str__(self) -> str:
        return self.transaction_number or f"POS/{self.pk}"


class POSTransactionItem(BaseEntity):
    """A line item in a POS transaction."""

    transaction = models.ForeignKey(
        POSTransaction, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="pos_transaction_items")
    qty = models.DecimalField(max_digits=19, decimal_places=4)
    rate = models.DecimalField(max_digits=19, decimal_places=4)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    # Serial / batch for tracked items
    serial_no = models.CharField(max_length=100, blank=True)
    batch_no = models.CharField(max_length=100, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_transaction_items"

    def __str__(self) -> str:
        return f"{self.transaction} — {self.item} × {self.qty}"


class POSPayment(BaseEntity):
    """
    One payment tender line on a POS transaction.
    A single sale can be split across multiple payment methods (§11).
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        GIFT_CARD = "gift_card", "Gift Card"
        STORE_CREDIT = "store_credit", "Store Credit"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"

    transaction = models.ForeignKey(
        POSTransaction, on_delete=models.CASCADE, related_name="payments"
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # For card / mobile money: the processor's reference / confirmation token
    gateway_reference = models.CharField(max_length=255, blank=True)
    # Mobile money: recipient number
    mobile_number = models.CharField(max_length=20, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_payments"

    def __str__(self) -> str:
        return f"{self.transaction} / {self.payment_method} {self.amount}"


# ---------------------------------------------------------------------------
# Offline Queue (§7.2)
# ---------------------------------------------------------------------------

class POSOfflineQueue(BaseEntity):
    """
    Transactions captured while a terminal has no connectivity.
    Replayed in FIFO order on reconnect; idempotency_key prevents duplicate processing.
    """

    class SyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    terminal = models.ForeignKey(
        POSTerminal, on_delete=models.CASCADE, related_name="offline_queue"
    )
    idempotency_key = models.CharField(max_length=100, unique=True, db_index=True,
                                       help_text="Client-generated key; prevents duplicate replay")
    payload = models.JSONField(help_text="Full transaction payload captured offline")
    captured_at = models.DateTimeField()
    sync_status = models.CharField(
        max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    synced_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    # Set once the offline transaction is created in the DB
    created_transaction_id = models.UUIDField(null=True, blank=True)

    class Meta(BaseEntity.Meta):
        db_table = "pos_offline_queue"
        ordering = ["captured_at"]

    def __str__(self) -> str:
        return f"OFFLINE/{self.idempotency_key} [{self.sync_status}]"
