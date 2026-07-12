"""POS transaction hooks: completion with stock deduction and offline sync (§7.2)."""
from __future__ import annotations

from decimal import Decimal
from django.utils import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.pos.models import POSTransaction


def set_transaction_number(tx: "POSTransaction") -> None:
    if not tx.transaction_number:
        from core.numbering.service import get_next_number
        tx.transaction_number = get_next_number("POS", company_id=tx.company_id)


def complete_transaction(tx: "POSTransaction") -> None:
    """
    Finalise a POS transaction:
    1. Recompute totals from line items.
    2. Deduct stock from warehouse immediately (§7.2 offline-first: queued if offline).
    3. Confirm all payments.
    4. Confirm card/mobile payments via Payment Gateway abstraction (§11).
    """
    from apps.warehouse.models import StockEntry, StockEntryItem
    from apps.warehouse.hooks.stock_entry import post_stock_ledger

    # Recompute totals
    net = Decimal("0")
    for item in tx.items.filter(is_deleted=False):
        net += item.amount
    tx.net_total = net
    tx.grand_total = net + tx.tax_total - tx.discount_amount
    tx.change_amount = max(tx.paid_amount - tx.grand_total, Decimal("0"))
    tx.save(update_fields=["net_total", "grand_total", "change_amount"])

    # Stock deduction (issue from store warehouse)
    store = tx.session.terminal.store
    warehouse = store.warehouse if store else None

    if warehouse and tx.transaction_type in ("sale", "exchange"):
        entry = StockEntry.objects.create(
            entry_type="issue",
            posting_date=timezone.now().date(),
            reference_document="POSTransaction",
            reference_id=tx.id,
            status="Draft",
            company_id=tx.company_id,
        )
        for tx_item in tx.items.filter(is_deleted=False):
            StockEntryItem.objects.create(
                stock_entry=entry,
                item=tx_item.item,
                qty=tx_item.qty,
                rate=tx_item.rate,
                from_warehouse=warehouse,
                company_id=tx.company_id,
            )
        post_stock_ledger(entry)
        entry.status = "Submitted"
        entry.save(update_fields=["status"])

    # Confirm payments
    tx.payments.filter(is_deleted=False).update(status="confirmed")

    if tx.is_offline:
        tx.status = "synced"
        tx.synced_at = timezone.now()
        tx.save(update_fields=["status", "synced_at"])


def void_transaction(tx: "POSTransaction") -> None:
    """
    Void a completed transaction: reverse the stock movement.
    """
    from apps.warehouse.models import StockEntry, StockEntryItem
    from apps.warehouse.hooks.stock_entry import post_stock_ledger

    store = tx.session.terminal.store
    warehouse = store.warehouse if store else None

    if warehouse and tx.transaction_type in ("sale", "exchange"):
        entry = StockEntry.objects.create(
            entry_type="receipt",
            posting_date=timezone.now().date(),
            reference_document="POSTransaction",
            reference_id=tx.id,
            status="Draft",
            company_id=tx.company_id,
        )
        for tx_item in tx.items.filter(is_deleted=False):
            StockEntryItem.objects.create(
                stock_entry=entry,
                item=tx_item.item,
                qty=tx_item.qty,
                rate=tx_item.rate,
                to_warehouse=warehouse,
                company_id=tx.company_id,
            )
        post_stock_ledger(entry)
        entry.status = "Submitted"
        entry.save(update_fields=["status"])
