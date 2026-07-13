"""CRM quote hooks (§6.3)."""
from __future__ import annotations


def recalculate_totals(quote) -> None:
    """Recompute subtotal and grand_total from line items before save."""
    if not quote.pk:
        return
    try:
        line_total = sum(
            item.line_total for item in quote.items.filter(is_deleted=False)
        )
    except Exception:
        return
    quote.subtotal = line_total
    quote.grand_total = line_total - (quote.discount_amount or 0) + (quote.tax_amount or 0)
