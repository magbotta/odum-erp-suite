"""
Cash and bank-teller drivers.

Cash payments don't need an external API call — the gateway's record_cash()
method handles them directly.  These drivers exist to satisfy the driver
interface for any caller that routes through initiate() rather than record_cash(),
and to provide a reusable parse_webhook() for bank-notification webhooks
(e.g., Ghana Interbank Payment System GHIPPS confirmations or bank USSD debit
confirmations from Consolidated Bank Ghana / GCB / Access Bank).

Driver names:
  "cash"           — in-person cash collection (teller, field collector)
  "bank_transfer"  — bank-push / GHIPPS / RTGS confirmation via webhook
"""
import json
import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from core.payments_gateway.gateway import (
    PaymentDriver,
    PaymentRequest,
    PaymentResult,
    register_driver,
)

logger = logging.getLogger(__name__)


class CashTellerDriver(PaymentDriver):
    """
    Cash collection driver.

    initiate() is a no-op — cash is collected by a human teller or field
    agent and recorded immediately as confirmed.  Use PaymentGateway.record_cash()
    instead for the normal cash path.
    """

    name = "cash"

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        """
        Record a cash payment synchronously (no external round-trip).
        Generates a local receipt reference.
        """
        receipt_ref = "CASH-{0}".format(uuid.uuid4().hex[:8].upper())
        logger.info(
            "[STUB] Cash teller receipt: %s amount=%s %s for doc=%s",
            receipt_ref, request.amount, request.currency,
            request.payable_document_id,
        )
        return PaymentResult(
            success=True,
            provider_tx_id=receipt_ref,
            gateway_reference="",
            status="confirmed",
            message="Cash payment recorded. Receipt: {0}".format(receipt_ref),
        )

    def parse_webhook(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        # Cash has no inbound webhook; return None so the gateway ignores it.
        return None


class BankTransferDriver(PaymentDriver):
    """
    Bank transfer / GHIPPS / RTGS driver.

    initiate() sends a payment request to the bank's outbound collections API
    (stub).  parse_webhook() handles the bank's inbound confirmation callback,
    which typically arrives minutes or hours after initiation.

    Webhook payload (generic bank notification shape):
    {
        "bank_ref": "GCB-20240101-XYZ",
        "external_ref": "<our payable_document_id>",
        "amount": "500.00",
        "currency": "GHS",
        "debit_account": "0123456789",
        "status": "SUCCESS",            # or FAILED / PENDING
        "value_date": "2024-01-01"
    }
    """

    name = "bank_transfer"

    _STATUS_MAP: Dict[str, str] = {
        "SUCCESS": "confirmed",
        "FAILED": "failed",
        "PENDING": "pending",
        "REVERSED": "reversed",
    }

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        bank_ref = "BKTX-{0}".format(uuid.uuid4().hex[:10].upper())
        logger.info(
            "[STUB] Bank transfer initiate: ref=%s account=%s amount=%s %s",
            bank_ref, request.payer_phone, request.amount, request.currency,
        )
        return PaymentResult(
            success=True,
            provider_tx_id=bank_ref,
            gateway_reference="",
            status="pending",
            message="Bank transfer instruction sent; awaiting settlement confirmation.",
        )

    def parse_webhook(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Bank transfer webhook: invalid JSON — %s", exc)
            return None

        if "bank_ref" not in data:
            return None

        bank_status = data.get("status", "PENDING")
        internal_status = self._STATUS_MAP.get(bank_status, "pending")

        return {
            "provider_tx_id": data["bank_ref"],
            "status": internal_status,
            "amount": Decimal(str(data.get("amount", "0"))),
            "currency": data.get("currency", "GHS"),
            "payer_phone": data.get("debit_account", ""),
            "payable_document_id": data.get("external_ref", ""),
            "payable_document_type": data.get("payable_document_type", ""),
            "revenue_type": data.get("revenue_type", ""),
            "raw": data,
        }


def register_all() -> None:
    """Register cash and bank-transfer drivers with the default gateway registry."""
    register_driver("cash", CashTellerDriver())
    register_driver("bank_transfer", BankTransferDriver())
