"""
Core Payment Gateway abstraction — §11.

Every module that needs to receive a payment (Accounting AR, POS, Website checkout,
Microfinance repayment, Government revenue collection) calls the PaymentGateway API
rather than integrating a processor SDK directly.

Architecture:
  PaymentGateway
    .initiate(request: PaymentRequest) -> PaymentResult
    .handle_webhook(provider: str, raw_body: bytes, headers: dict) -> WebhookResult
    .record_cash(request: CashPaymentRequest) -> PaymentResult

Drivers are registered by name.  The gateway dispatches to the appropriate driver.

Idempotency:
  Every payment attempt is keyed by (provider, provider_tx_id) to prevent double-posting
  from retried webhooks.  The idempotency check happens at the gateway level, not per-driver.

Audit:
  Every call to initiate/handle_webhook/record_cash logs a PaymentEvent record.
  These events are what the Government IGF report and any reconciliation report query.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DRIVER_REGISTRY: Dict[str, "PaymentDriver"] = {}


def register_driver(name: str, driver: "PaymentDriver") -> None:
    _DRIVER_REGISTRY[name] = driver


def get_driver(name: str) -> "PaymentDriver":
    if name not in _DRIVER_REGISTRY:
        raise ValueError("No payment driver registered for provider '{0}'.".format(name))
    return _DRIVER_REGISTRY[name]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PaymentRequest:
    """Initiate a payment against a payable document."""
    provider: str                       # e.g. "mtn_momo", "airteltigo", "vodafone_cash"
    amount: Decimal
    currency: str
    payer_phone: str                    # MSISDN / account identifier for the payer
    payable_document_id: str            # UUID of the document being paid (bill, invoice…)
    payable_document_type: str          # e.g. "GovernmentRevenueBill", "SalesInvoice"
    revenue_type: str                   # e.g. "property_rate", "permit_fee", "market_toll"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None  # caller-supplied; auto-generated if omitted


@dataclass
class CashPaymentRequest:
    """Record a cash or bank-teller payment (no gateway round-trip required)."""
    amount: Decimal
    currency: str
    payable_document_id: str
    payable_document_type: str
    revenue_type: str
    collector_id: str                   # UUID of the cashier/field collector
    receipt_number: Optional[str] = None
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentResult:
    success: bool
    provider_tx_id: Optional[str]
    gateway_reference: str              # internal reference (PaymentEvent.id)
    status: str                         # "pending", "confirmed", "failed"
    message: str = ""
    idempotent_duplicate: bool = False  # True if this exact payment was already processed


@dataclass
class WebhookResult:
    processed: bool
    idempotent_duplicate: bool
    payment_result: Optional[PaymentResult]
    message: str = ""


# ---------------------------------------------------------------------------
# Driver interface
# ---------------------------------------------------------------------------

class PaymentDriver:
    """Base class for payment drivers.  Subclass and register to add a provider."""

    name: str = "base"

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        raise NotImplementedError

    def parse_webhook(self, raw_body: bytes, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Parse an inbound provider webhook into a normalized dict.
        Returns None if the payload is not a payment-confirmation event.
        Required keys in the returned dict:
          - provider_tx_id (str)
          - status (str): "confirmed" | "failed" | "pending"
          - amount (Decimal)
          - currency (str)
          - payer_phone (str)
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

class PaymentGateway:

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        """Initiate an outbound payment request (e.g. push mobile money prompt)."""
        from .models import PaymentEvent

        driver = get_driver(request.provider)
        ikey = request.idempotency_key or self._make_idempotency_key(request)

        # Idempotency check
        existing = PaymentEvent.objects.filter(idempotency_key=ikey).first()
        if existing:
            return PaymentResult(
                success=True,
                provider_tx_id=existing.provider_tx_id,
                gateway_reference=str(existing.id),
                status=existing.status,
                message="Duplicate request — returning existing result.",
                idempotent_duplicate=True,
            )

        try:
            result = driver.initiate(request)
        except Exception as exc:
            logger.exception("Payment initiation failed for provider %s", request.provider)
            result = PaymentResult(
                success=False,
                provider_tx_id=None,
                gateway_reference="",
                status="failed",
                message=str(exc),
            )

        event = PaymentEvent.objects.create(
            provider=request.provider,
            provider_tx_id=result.provider_tx_id,
            idempotency_key=ikey,
            payable_document_id=request.payable_document_id,
            payable_document_type=request.payable_document_type,
            revenue_type=request.revenue_type,
            amount=request.amount,
            currency=request.currency,
            payer_reference=request.payer_phone,
            status=result.status,
            direction="inbound",
            raw_request=dict(vars(request), amount=str(request.amount)),
            raw_response={"message": result.message, "provider_tx_id": result.provider_tx_id},
        )
        result.gateway_reference = str(event.id)
        return result

    def handle_webhook(
        self, provider: str, raw_body: bytes, headers: Dict[str, str]
    ) -> WebhookResult:
        """Process an inbound provider webhook confirming a payment."""
        from .models import PaymentEvent

        driver = get_driver(provider)

        try:
            parsed = driver.parse_webhook(raw_body, headers)
        except Exception as exc:
            logger.exception("Webhook parse failed for provider %s", provider)
            return WebhookResult(
                processed=False,
                idempotent_duplicate=False,
                payment_result=None,
                message="Parse error: {0}".format(exc),
            )

        if parsed is None:
            return WebhookResult(
                processed=False,
                idempotent_duplicate=False,
                payment_result=None,
                message="Not a payment confirmation event.",
            )

        provider_tx_id = parsed["provider_tx_id"]
        ikey = "{0}:{1}".format(provider, provider_tx_id)

        # Idempotency check — the critical guard against double-posting
        existing = PaymentEvent.objects.filter(
            provider=provider,
            provider_tx_id=provider_tx_id,
            status="confirmed",
        ).first()
        if existing:
            return WebhookResult(
                processed=False,
                idempotent_duplicate=True,
                payment_result=PaymentResult(
                    success=True,
                    provider_tx_id=provider_tx_id,
                    gateway_reference=str(existing.id),
                    status="confirmed",
                    idempotent_duplicate=True,
                ),
                message="Duplicate webhook — already confirmed.",
            )

        # Look up or create the payment event (may have been created at initiation)
        pending = PaymentEvent.objects.filter(
            provider=provider,
            provider_tx_id=provider_tx_id,
        ).exclude(status="confirmed").first()

        if pending:
            pending.status = parsed["status"]
            pending.save(update_fields=["status"])
            event = pending
        else:
            event = PaymentEvent.objects.create(
                provider=provider,
                provider_tx_id=provider_tx_id,
                idempotency_key=ikey,
                payable_document_id=parsed.get("payable_document_id", ""),
                payable_document_type=parsed.get("payable_document_type", ""),
                revenue_type=parsed.get("revenue_type", ""),
                amount=parsed.get("amount", Decimal("0")),
                currency=parsed.get("currency", ""),
                payer_reference=parsed.get("payer_phone", ""),
                status=parsed["status"],
                direction="inbound",
                raw_request={},
                raw_response=parsed,
            )

        result = PaymentResult(
            success=parsed["status"] == "confirmed",
            provider_tx_id=provider_tx_id,
            gateway_reference=str(event.id),
            status=parsed["status"],
        )

        return WebhookResult(
            processed=True,
            idempotent_duplicate=False,
            payment_result=result,
        )

    def record_cash(self, request: CashPaymentRequest) -> PaymentResult:
        """Record a cash or bank-teller payment directly (no gateway round-trip)."""
        from .models import PaymentEvent
        import uuid as _uuid

        ikey = "cash:{0}:{1}".format(
            request.payable_document_id,
            request.receipt_number or _uuid.uuid4().hex,
        )

        existing = PaymentEvent.objects.filter(idempotency_key=ikey).first()
        if existing:
            return PaymentResult(
                success=True,
                provider_tx_id=None,
                gateway_reference=str(existing.id),
                status="confirmed",
                idempotent_duplicate=True,
            )

        event = PaymentEvent.objects.create(
            provider="cash",
            provider_tx_id=None,
            idempotency_key=ikey,
            payable_document_id=request.payable_document_id,
            payable_document_type=request.payable_document_type,
            revenue_type=request.revenue_type,
            amount=request.amount,
            currency=request.currency,
            payer_reference=str(request.collector_id),
            status="confirmed",
            direction="inbound",
            raw_request={"receipt_number": request.receipt_number, "notes": request.notes},
            raw_response={"collector_id": str(request.collector_id)},
        )

        return PaymentResult(
            success=True,
            provider_tx_id=None,
            gateway_reference=str(event.id),
            status="confirmed",
        )

    @staticmethod
    def _make_idempotency_key(request: PaymentRequest) -> str:
        payload = "{0}:{1}:{2}:{3}".format(
            request.provider, request.payable_document_id,
            request.amount, request.currency,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# Module-level default gateway instance
default_gateway = PaymentGateway()
