"""Asset hooks: depreciation schedule generation and GL posting (§6.2)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.asset_management.models import Asset, AssetDepreciationSchedule


def generate_depreciation_schedule(asset: "Asset") -> None:
    """
    Builds AssetDepreciationSchedule rows using:
    - straight_line: equal amounts per period
    - declining_balance: fixed rate on reducing book value
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from apps.asset_management.models import AssetDepreciationSchedule

    # Clear any unposted rows before regenerating
    AssetDepreciationSchedule.objects.filter(asset=asset, is_posted=False).delete()

    method = asset.depreciation_method or "straight_line"
    start = asset.depreciation_start_date or asset.purchase_date
    useful_years = asset.useful_life_years or 5
    total_months = useful_years * 12
    cost = asset.purchase_price
    salvage = asset.salvage_value or Decimal("0")
    depreciable_amount = cost - salvage

    if depreciable_amount <= 0 or total_months <= 0:
        return

    accumulated = Decimal("0")
    book_value = cost
    rows = []

    if method == "straight_line":
        monthly_dep = (depreciable_amount / total_months).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for i in range(total_months):
            schedule_date = start + relativedelta(months=i + 1)
            # Last period: use remainder to avoid rounding drift
            if i == total_months - 1:
                dep = cost - salvage - accumulated
            else:
                dep = min(monthly_dep, cost - salvage - accumulated)
            if dep <= 0:
                break
            accumulated += dep
            book_value = cost - accumulated
            rows.append(
                AssetDepreciationSchedule(
                    asset=asset,
                    schedule_date=schedule_date,
                    depreciation_amount=dep,
                    accumulated_depreciation=accumulated,
                    book_value_after=max(book_value, salvage),
                    company_id=asset.company_id,
                )
            )

    elif method == "declining_balance":
        # Double Declining Balance: rate = 2 / useful_years applied to book value
        annual_rate = Decimal("2") / Decimal(str(useful_years))
        monthly_rate = annual_rate / 12
        for i in range(total_months):
            schedule_date = start + relativedelta(months=i + 1)
            dep = (book_value * monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            # Don't depreciate below salvage value
            dep = min(dep, book_value - salvage)
            if dep <= 0:
                break
            accumulated += dep
            book_value -= dep
            rows.append(
                AssetDepreciationSchedule(
                    asset=asset,
                    schedule_date=schedule_date,
                    depreciation_amount=dep,
                    accumulated_depreciation=accumulated,
                    book_value_after=book_value,
                    company_id=asset.company_id,
                )
            )

    AssetDepreciationSchedule.objects.bulk_create(rows)

    # Keep current_value in sync
    asset.current_value = book_value
    asset.save(update_fields=["current_value"])


def post_depreciation(schedule_row: "AssetDepreciationSchedule") -> None:
    """Post a single depreciation period to the GL as a JournalEntry (§6.2)."""
    from apps.accounting.models import JournalEntry, JournalEntryLine

    if schedule_row.is_posted:
        return

    asset = schedule_row.asset
    category = asset.category

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=schedule_row.schedule_date,
        reference=f"DEP/{asset.asset_code}/{schedule_row.schedule_date}",
        narration=f"Depreciation for {asset.asset_name} [{schedule_row.schedule_date}]",
        status="Draft",
        currency="USD",
        company_id=asset.company_id,
    )

    dep = schedule_row.depreciation_amount

    # Debit depreciation expense
    JournalEntryLine.objects.create(
        journal_entry=je,
        account_id=category.depreciation_expense_account_id,
        debit_amount=dep,
        credit_amount=Decimal("0"),
        currency="USD",
        company_id=asset.company_id,
    )
    # Credit accumulated depreciation
    JournalEntryLine.objects.create(
        journal_entry=je,
        account_id=category.accumulated_depreciation_account_id,
        debit_amount=Decimal("0"),
        credit_amount=dep,
        currency="USD",
        company_id=asset.company_id,
    )

    je.status = "Submitted"
    je.save(update_fields=["status"])

    schedule_row.is_posted = True
    schedule_row.journal_entry_id = je.id
    schedule_row.save(update_fields=["is_posted", "journal_entry_id"])

    # Mark fully depreciated when nothing remains above salvage
    asset.current_value -= dep
    if asset.current_value <= asset.salvage_value:
        asset.fully_depreciated = True
    asset.save(update_fields=["current_value", "fully_depreciated"])
