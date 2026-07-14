"""
Stub mobile money drivers for West African MNOs.

These stubs simulate realistic API behaviour — method signatures, payload shapes,
and webhook structures match each provider's published integration documentation —
but make no real network calls.  Replace the `_call_provider_api()` body with an
actual HTTP request when a live integration is needed.

Providers:
  - MTN Mobile Money (Ghana)    → driver name "mtn_momo"
  - AirtelTigo Money (Ghana)    → driver name "airteltigo"
  - Vodafone Cash (Ghana)       → driver name "vodafone_cash"
"""
import hashlib
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _normalize_msisdn(phone: str, country_code: str = "233") -> str:
    """Strip leading + or 00, ensure country code prefix."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = phone[2:]
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = country_code + phone[1:]
    return phone


def _stub_tx_id(prefix: str, ref: str) -> str:
    """Generate a deterministic-looking transaction ID for the stub."""
    digest = hashlib.sha256(("{0}:{1}".format(prefix, ref)).encode()).hexdigest()[:16].upper()
    return "{0}-{1}".format(prefix, digest)


# ---------------------------------------------------------------------------
# MTN Mobile Money (Ghana)
# ---------------------------------------------------------------------------

class MTNMoMoDriver(PaymentDriver):
    """
    Stub driver for MTN Mobile Money Ghana Collections API (v1).

    Real API:  POST /collection/v1_0/requesttopay
    Webhook:   POST to a registered callback URL on transaction completion.

    Webhook payload (what the provider POSTs to Ochre):
    {
        "referenceId": "<uuid>",
        "externalId": "<our payable_document_id>",
        "amount": "100.00",
        "currency": "GHS",
        "payer": {"partyIdType": "MSISDN", "partyId": "233241234567"},
        "status": "SUCCESSFUL",         # or FAILED
        "reason": ""
    }
    """

    name = "mtn_momo"

    # Map provider status → internal status
    _STATUS_MAP: Dict[str, str] = {
        "SUCCESSFUL": "confirmed",
        "FAILED": "failed",
        "PENDING": "pending",
    }

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        msisdn = _normalize_msisdn(request.payer_phone)
        reference_id = str(uuid.uuid4())

        payload = {
            "amount": str(request.amount),
            "currency": request.currency,
            "externalId": request.payable_document_id,
            "payer": {"partyIdType": "MSISDN", "partyId": msisdn},
            "payerMessage": request.description or "Payment",
            "payeeNote": request.payable_document_type,
            "referenceId": reference_id,
        }

        # --- stub: simulates a successful prompt dispatch ---
        logger.info(
            "[STUB] MTN MoMo requesttopay: ref=%s msisdn=%s amount=%s %s",
            reference_id, msisdn, request.amount, request.currency,
        )
        provider_response = {
            "status": "PENDING",
            "referenceId": reference_id,
            "message": "Prompt sent to {0}".format(msisdn),
        }
        # ---------------------------------------------------

        tx_id = _stub_tx_id("MTNGH", reference_id)
        return PaymentResult(
            success=True,
            provider_tx_id=tx_id,
            gateway_reference="",
            status="pending",
            message="MTN MoMo prompt sent; awaiting USSD confirmation.",
        )

    def parse_webhook(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse an MTN MoMo callback webhook.

        Expected header: X-Callback-Url, Authorization: Bearer <token>
        Expected body (JSON): see class docstring.
        """
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("MTN MoMo webhook: invalid JSON — %s", exc)
            return None

        if "referenceId" not in data:
            return None

        mtn_status = data.get("status", "PENDING")
        internal_status = self._STATUS_MAP.get(mtn_status, "pending")
        amount_str = data.get("amount", "0")

        return {
            "provider_tx_id": _stub_tx_id("MTNGH", data["referenceId"]),
            "status": internal_status,
            "amount": Decimal(str(amount_str)),
            "currency": data.get("currency", "GHS"),
            "payer_phone": (data.get("payer") or {}).get("partyId", ""),
            "payable_document_id": data.get("externalId", ""),
            "payable_document_type": data.get("payeeNote", ""),
            "revenue_type": data.get("revenue_type", ""),
            "raw": data,
        }


# ---------------------------------------------------------------------------
# AirtelTigo Money (Ghana)
# ---------------------------------------------------------------------------

class AirtelTigoDriver(PaymentDriver):
    """
    Stub driver for AirtelTigo Money Ghana (Direct Pay API).

    Real API:  POST /merchant/v1/payments/
    Webhook:   POST callback on status change.

    Webhook payload:
    {
        "transaction": {
            "id": "AT-<hex>",
            "message": "SUCCESS",
            "status_code": "TS",             # TS = success, TF = failure
            "airtel_money_id": "CI231234567"
        },
        "externalId": "<our document id>",
        "amount": "50.00",
        "currency": "GHS",
        "msisdn": "0271234567"
    }
    """

    name = "airteltigo"

    _STATUS_MAP: Dict[str, str] = {
        "TS": "confirmed",
        "TF": "failed",
        "TP": "pending",
    }

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        msisdn = _normalize_msisdn(request.payer_phone)
        reference = str(uuid.uuid4())

        payload = {
            "reference": reference,
            "subscriber": {"country": "GH", "currency": request.currency, "msisdn": msisdn},
            "transaction": {
                "amount": str(request.amount),
                "country": "GH",
                "currency": request.currency,
                "id": reference,
            },
        }

        logger.info(
            "[STUB] AirtelTigo payment initiate: ref=%s msisdn=%s amount=%s",
            reference, msisdn, request.amount,
        )

        tx_id = _stub_tx_id("AT", reference)
        return PaymentResult(
            success=True,
            provider_tx_id=tx_id,
            gateway_reference="",
            status="pending",
            message="AirtelTigo prompt sent; awaiting PIN confirmation.",
        )

    def parse_webhook(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("AirtelTigo webhook: invalid JSON — %s", exc)
            return None

        tx = data.get("transaction", {})
        if not tx.get("id"):
            return None

        status_code = tx.get("status_code", "TP")
        internal_status = self._STATUS_MAP.get(status_code, "pending")

        return {
            "provider_tx_id": _stub_tx_id("AT", tx["id"]),
            "status": internal_status,
            "amount": Decimal(str(data.get("amount", "0"))),
            "currency": data.get("currency", "GHS"),
            "payer_phone": data.get("msisdn", ""),
            "payable_document_id": data.get("externalId", ""),
            "payable_document_type": data.get("payable_document_type", ""),
            "revenue_type": data.get("revenue_type", ""),
            "raw": data,
        }


# ---------------------------------------------------------------------------
# Vodafone Cash (Ghana)
# ---------------------------------------------------------------------------

class VodafoneCashDriver(PaymentDriver):
    """
    Stub driver for Vodafone Cash Ghana Merchant Collections API.

    Real API:  POST /api/v1/collect
    Webhook:   POST callback JSON.

    Webhook payload:
    {
        "token": "<transaction token>",
        "status": "approved",           # or "declined", "pending"
        "transaction_id": "VF-<hex>",
        "msisdn": "0201234567",
        "amount": "200.00",
        "currency": "GHS",
        "external_reference": "<our document id>"
    }
    """

    name = "vodafone_cash"

    _STATUS_MAP: Dict[str, str] = {
        "approved": "confirmed",
        "declined": "failed",
        "pending": "pending",
    }

    def initiate(self, request: PaymentRequest) -> PaymentResult:
        msisdn = _normalize_msisdn(request.payer_phone)
        reference = str(uuid.uuid4())

        payload = {
            "amount": str(request.amount),
            "msisdn": msisdn,
            "external_reference": request.payable_document_id,
            "description": request.description or "Payment",
        }

        logger.info(
            "[STUB] Vodafone Cash collect: ref=%s msisdn=%s amount=%s",
            reference, msisdn, request.amount,
        )

        tx_id = _stub_tx_id("VF", reference)
        return PaymentResult(
            success=True,
            provider_tx_id=tx_id,
            gateway_reference="",
            status="pending",
            message="Vodafone Cash prompt sent; awaiting USSD PIN.",
        )

    def parse_webhook(
        self, raw_body: bytes, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Vodafone Cash webhook: invalid JSON — %s", exc)
            return None

        if "transaction_id" not in data:
            return None

        vf_status = data.get("status", "pending")
        internal_status = self._STATUS_MAP.get(vf_status, "pending")

        return {
            "provider_tx_id": data["transaction_id"],
            "status": internal_status,
            "amount": Decimal(str(data.get("amount", "0"))),
            "currency": data.get("currency", "GHS"),
            "payer_phone": data.get("msisdn", ""),
            "payable_document_id": data.get("external_reference", ""),
            "payable_document_type": data.get("payable_document_type", ""),
            "revenue_type": data.get("revenue_type", ""),
            "raw": data,
        }


# ---------------------------------------------------------------------------
# Auto-registration
# ---------------------------------------------------------------------------

def register_all() -> None:
    """Register all mobile money drivers with the default gateway registry."""
    register_driver("mtn_momo", MTNMoMoDriver())
    register_driver("airteltigo", AirtelTigoDriver())
    register_driver("vodafone_cash", VodafoneCashDriver())
