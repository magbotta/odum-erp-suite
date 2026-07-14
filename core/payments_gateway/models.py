"""
PaymentEvent — the universal audit log for every payment processed through the gateway.

Every payment, regardless of channel (mobile money, cash, bank transfer), creates
a PaymentEvent.  This is what reconciliation reports, IGF reports, and the audit
trail query.

There is one table; revenue_type and payable_document_type give the classification.
"""
from __future__ import annotations

from django.db import models

from core.metadata_engine.base_entity import BaseEntity


class PaymentEvent(BaseEntity):
    """
    A single payment event, confirmed or otherwise.
    Created at initiation (status=pending) and updated on confirmation,
    OR created directly from a webhook when we didn't initiate the call.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound (collection)"
        OUTBOUND = "outbound", "Outbound (disbursement)"

    provider = models.CharField(
        max_length=50,
        help_text="Driver name: mtn_momo, airteltigo, vodafone_cash, cash, bank_transfer",
        db_index=True,
    )
    provider_tx_id = models.CharField(
        max_length=255, blank=True, null=True, db_index=True,
        help_text="Provider's own transaction ID (used for idempotency on webhooks).",
    )
    idempotency_key = models.CharField(
        max_length=255, db_index=True,
        help_text="Computed key used to prevent duplicate processing.",
    )

    # What this payment is against
    payable_document_id = models.CharField(max_length=36, db_index=True)
    payable_document_type = models.CharField(
        max_length=100,
        help_text="Model name: GovernmentRevenueBill, SalesInvoice, LoanAccount…",
        db_index=True,
    )
    revenue_type = models.CharField(
        max_length=100, db_index=True,
        help_text="Classification: property_rate, permit_fee, market_toll, service_charge, sales, loan_repayment…",
    )

    # Money
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, default="GHS")
    payer_reference = models.CharField(
        max_length=255, blank=True,
        help_text="Phone number, account number, or collector ID.",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    direction = models.CharField(
        max_length=10, choices=Direction.choices, default=Direction.INBOUND
    )

    # GL posting soft link (set after accounting journal entry is created)
    journal_entry_id = models.CharField(max_length=36, blank=True, null=True, db_index=True)

    # Raw payloads for audit/debugging
    raw_request = models.JSONField(default=dict)
    raw_response = models.JSONField(default=dict)

    class Meta(BaseEntity.Meta):
        db_table = "payments_events"
        indexes = [
            models.Index(fields=["provider", "provider_tx_id"], name="pay_evt_provider_tx_idx"),
            models.Index(fields=["payable_document_type", "payable_document_id"], name="pay_evt_doc_idx"),
            models.Index(fields=["revenue_type", "status"], name="pay_evt_rev_type_idx"),
        ]

    def __str__(self) -> str:
        return "{0} / {1} {2} {3} ({4})".format(
            self.provider, self.amount, self.currency,
            self.payable_document_type, self.status,
        )
