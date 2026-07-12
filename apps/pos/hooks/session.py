"""POS session hooks: open/close with GL reconciliation posting (§7.2)."""
from __future__ import annotations

from decimal import Decimal
from django.utils import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.pos.models import POSSession


def set_session_number(session: "POSSession") -> None:
    if not session.session_number:
        from core.numbering.service import get_next_number
        session.session_number = get_next_number("POS-SESSION", company_id=session.company_id)


def begin_close(session: "POSSession") -> None:
    """Tally session totals from all completed transactions before closing."""
    from apps.pos.models import POSTransaction

    completed = POSTransaction.objects.filter(
        session=session,
        status__in=["completed", "synced"],
        is_deleted=False,
    )
    total_sales = Decimal("0")
    total_returns = Decimal("0")
    total_cash = session.opening_cash

    for tx in completed:
        if tx.transaction_type == "sale":
            total_sales += tx.grand_total
        elif tx.transaction_type == "return":
            total_returns += tx.grand_total

        for payment in tx.payments.filter(status="confirmed", is_deleted=False):
            if payment.payment_method == "cash":
                if tx.transaction_type == "sale":
                    total_cash += payment.amount
                else:
                    total_cash -= payment.amount

    session.total_sales = total_sales
    session.total_returns = total_returns
    session.closing_cash_expected = total_cash
    session.save(update_fields=["total_sales", "total_returns", "closing_cash_expected"])


def close_session(session: "POSSession") -> None:
    """Finalize the session: record difference and post to GL."""
    from apps.accounting.models import JournalEntry, JournalEntryLine
    from core.numbering.service import get_next_number

    session.cash_difference = session.closing_cash_actual - session.closing_cash_expected
    session.closed_at = timezone.now()
    session.save(update_fields=["cash_difference", "closed_at"])

    # GL posting: Dr Cash/Till, Cr Sales Revenue
    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=session.closed_at.date(),
        reference=session.session_number,
        narration=f"POS session close: {session.session_number}",
        status="Submitted",
        currency=session.currency,
        company_id=session.company_id,
    )

    net_revenue = session.total_sales - session.total_returns

    if net_revenue != 0:
        JournalEntryLine.objects.create(
            journal_entry=je,
            account_id=_sentinel("pos_cash_account"),
            debit_amount=max(net_revenue, Decimal("0")),
            credit_amount=max(-net_revenue, Decimal("0")),
            currency=session.currency,
            company_id=session.company_id,
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account_id=_sentinel("pos_revenue_account"),
            debit_amount=max(-net_revenue, Decimal("0")),
            credit_amount=max(net_revenue, Decimal("0")),
            currency=session.currency,
            company_id=session.company_id,
        )

    session.journal_entry_id = je.id
    session.save(update_fields=["journal_entry_id"])


def _sentinel(key: str):
    import uuid
    _MAP = {
        "pos_cash_account": "00000000-0000-0000-0000-000000000020",
        "pos_revenue_account": "00000000-0000-0000-0000-000000000021",
    }
    return uuid.UUID(_MAP.get(key, "00000000-0000-0000-0000-000000000099"))
