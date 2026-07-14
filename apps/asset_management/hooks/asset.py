"""Asset hooks: depreciation, revaluation, disposal, GL posting (§6.2)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.asset_management.models import Asset, AssetDepreciationSchedule


def generate_depreciation_schedule(asset: "Asset") -> None:
    """
    Builds AssetDepreciationSchedule rows using:
    - straight_line: equal monthly amounts
    - declining_balance: double-declining rate on reducing book value
    Clears any unposted rows before regenerating.
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from apps.asset_management.models import AssetDepreciationSchedule

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
            dep = cost - salvage - accumulated if i == total_months - 1 else min(monthly_dep, cost - salvage - accumulated)
            if dep <= 0:
                break
            accumulated += dep
            book_value = cost - accumulated
            rows.append(AssetDepreciationSchedule(
                asset=asset,
                schedule_date=schedule_date,
                depreciation_amount=dep,
                accumulated_depreciation=accumulated,
                book_value_after=max(book_value, salvage),
                company_id=asset.company_id,
            ))

    elif method == "declining_balance":
        annual_rate = Decimal("2") / Decimal(str(useful_years))
        monthly_rate = annual_rate / 12
        for i in range(total_months):
            schedule_date = start + relativedelta(months=i + 1)
            dep = (book_value * monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            dep = min(dep, book_value - salvage)
            if dep <= 0:
                break
            accumulated += dep
            book_value -= dep
            rows.append(AssetDepreciationSchedule(
                asset=asset,
                schedule_date=schedule_date,
                depreciation_amount=dep,
                accumulated_depreciation=accumulated,
                book_value_after=book_value,
                company_id=asset.company_id,
            ))

    AssetDepreciationSchedule.objects.bulk_create(rows)

    asset.current_value = book_value
    asset.accumulated_depreciation = Decimal("0")  # reset; actual is sum of posted rows
    asset.save(update_fields=["current_value", "accumulated_depreciation"])


def post_depreciation(schedule_row: "AssetDepreciationSchedule") -> None:
    """
    Post a single depreciation period to the GL as a JournalEntry (§6.2).
    Dr  Depreciation Expense
    Cr  Accumulated Depreciation
    Skips gracefully if GL accounts are not configured.
    """
    if schedule_row.is_posted:
        return

    asset = schedule_row.asset
    category = asset.category

    try:
        from apps.accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
    except ImportError:
        return

    # Resolve account objects — skip if not configured
    expense_acct = None
    accum_acct = None
    if category.depreciation_expense_account_id:
        expense_acct = ChartOfAccount.objects.filter(
            id=category.depreciation_expense_account_id, is_deleted=False
        ).first()
    if category.accumulated_depreciation_account_id:
        accum_acct = ChartOfAccount.objects.filter(
            id=category.accumulated_depreciation_account_id, is_deleted=False
        ).first()

    if not expense_acct or not accum_acct:
        # Fallback: find any expense and contra-asset accounts for the company
        expense_acct = ChartOfAccount.objects.filter(
            account_type="expense", is_active=True, company_id=asset.company_id
        ).first()
        accum_acct = ChartOfAccount.objects.filter(
            account_type="asset", is_active=True, company_id=asset.company_id
        ).first()

    if not expense_acct or not accum_acct:
        return  # No GL configured — skip silently

    dep = schedule_row.depreciation_amount

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=schedule_row.schedule_date,
        reference="DEP/{}/{}".format(asset.asset_code, schedule_row.schedule_date),
        narration="Depreciation: {} [{}]".format(asset.asset_name, schedule_row.schedule_date),
        status="submitted",
        company_id=asset.company_id,
    )
    JournalEntryLine.objects.create(
        entry=je,
        account=expense_acct,
        debit_amount=dep,
        credit_amount=Decimal("0"),
        description="Depreciation expense — {}".format(asset.asset_name),
        company_id=asset.company_id,
    )
    JournalEntryLine.objects.create(
        entry=je,
        account=accum_acct,
        debit_amount=Decimal("0"),
        credit_amount=dep,
        description="Accumulated depreciation — {}".format(asset.asset_name),
        company_id=asset.company_id,
    )

    schedule_row.is_posted = True
    schedule_row.journal_entry_id = je.id
    schedule_row.save(update_fields=["is_posted", "journal_entry_id"])

    asset.current_value = max(asset.current_value - dep, asset.salvage_value)
    asset.accumulated_depreciation += dep
    if asset.current_value <= asset.salvage_value:
        asset.fully_depreciated = True
    asset.save(update_fields=["current_value", "accumulated_depreciation", "fully_depreciated"])


def post_due_depreciation(asset: "Asset", as_of_date=None) -> int:
    """Post all unposted depreciation rows up to as_of_date (default: today). Returns count posted."""
    import datetime
    from apps.asset_management.models import AssetDepreciationSchedule

    if as_of_date is None:
        as_of_date = datetime.date.today()

    rows = AssetDepreciationSchedule.objects.filter(
        asset=asset,
        is_posted=False,
        schedule_date__lte=as_of_date,
        is_deleted=False,
    ).order_by("schedule_date")

    count = 0
    for row in rows:
        post_depreciation(row)
        count += 1
    return count


def revalue_asset(asset: "Asset", new_value: Decimal, revaluation_date, reason: str = "") -> None:
    """
    Record an impairment or upward revaluation and post to GL (§6.2).
    Regenerates the remaining depreciation schedule from the new value.
    """
    import datetime
    from apps.asset_management.models import AssetRevaluation

    if isinstance(revaluation_date, str):
        revaluation_date = datetime.date.fromisoformat(revaluation_date)

    previous_value = asset.current_value
    adjustment = new_value - previous_value
    rtype = (
        AssetRevaluation.RevaluationType.REVALUATION
        if adjustment >= 0
        else AssetRevaluation.RevaluationType.IMPAIRMENT
    )

    rev = AssetRevaluation.objects.create(
        asset=asset,
        revaluation_date=revaluation_date,
        revaluation_type=rtype,
        previous_value=previous_value,
        new_value=new_value,
        adjustment_amount=abs(adjustment),
        reason=reason,
        company_id=asset.company_id,
    )

    # Update asset book value and regenerate schedule from new value
    asset.current_value = new_value
    asset.purchase_price = new_value + asset.accumulated_depreciation  # restate cost basis
    asset.depreciation_start_date = revaluation_date
    if new_value <= asset.salvage_value:
        asset.fully_depreciated = True
    asset.save(update_fields=["current_value", "purchase_price", "depreciation_start_date", "fully_depreciated"])

    generate_depreciation_schedule(asset)

    # GL posting (skip gracefully if no accounts)
    try:
        _post_revaluation_to_gl(rev, asset)
    except Exception:
        pass


def _post_revaluation_to_gl(rev, asset) -> None:
    from decimal import Decimal
    try:
        from apps.accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
    except ImportError:
        return

    asset_acct = ChartOfAccount.objects.filter(
        account_type="asset", is_active=True, company_id=asset.company_id
    ).first()
    pl_acct = ChartOfAccount.objects.filter(
        account_type="expense" if rev.revaluation_type == "impairment" else "income",
        is_active=True, company_id=asset.company_id
    ).first()
    if not asset_acct or not pl_acct:
        return

    adj = rev.adjustment_amount
    is_impairment = rev.revaluation_type == "impairment"

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=rev.revaluation_date,
        reference="REV/{}/{}".format(asset.asset_code, rev.revaluation_date),
        narration="{}: {} [{}]".format(
            rev.get_revaluation_type_display(), asset.asset_name, rev.revaluation_date
        ),
        status="submitted",
        company_id=asset.company_id,
    )

    if is_impairment:
        JournalEntryLine.objects.create(entry=je, account=pl_acct,
            debit_amount=adj, credit_amount=Decimal("0"),
            description="Impairment loss — {}".format(asset.asset_name), company_id=asset.company_id)
        JournalEntryLine.objects.create(entry=je, account=asset_acct,
            debit_amount=Decimal("0"), credit_amount=adj,
            description="Asset write-down — {}".format(asset.asset_name), company_id=asset.company_id)
    else:
        JournalEntryLine.objects.create(entry=je, account=asset_acct,
            debit_amount=adj, credit_amount=Decimal("0"),
            description="Asset revaluation — {}".format(asset.asset_name), company_id=asset.company_id)
        JournalEntryLine.objects.create(entry=je, account=pl_acct,
            debit_amount=Decimal("0"), credit_amount=adj,
            description="Revaluation surplus — {}".format(asset.asset_name), company_id=asset.company_id)

    rev.journal_entry_id = je.id
    rev.is_posted = True
    rev.save(update_fields=["journal_entry_id", "is_posted"])


def dispose_asset(asset: "Asset", disposal_date, disposal_amount: Decimal, reason: str = "") -> None:
    """
    Record disposal (sale or scrap) of an asset (§6.2).
    Posts a disposal GL entry recognising gain or loss.
    """
    import datetime
    from apps.asset_management.models import Asset as A

    if isinstance(disposal_date, str):
        disposal_date = datetime.date.fromisoformat(disposal_date)

    asset.disposal_date = disposal_date
    asset.disposal_amount = disposal_amount
    asset.disposal_reason = reason
    asset.status = A.Status.SOLD if disposal_amount > 0 else A.Status.SCRAPPED
    asset.save(update_fields=["disposal_date", "disposal_amount", "disposal_reason", "status"])

    try:
        _post_disposal_to_gl(asset, disposal_date, disposal_amount)
    except Exception:
        pass


def _post_disposal_to_gl(asset, disposal_date, disposal_amount) -> None:
    from decimal import Decimal
    try:
        from apps.accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
    except ImportError:
        return

    asset_acct = ChartOfAccount.objects.filter(
        account_type="asset", is_active=True, company_id=asset.company_id
    ).first()
    income_acct = ChartOfAccount.objects.filter(
        account_type="income", is_active=True, company_id=asset.company_id
    ).first()
    expense_acct = ChartOfAccount.objects.filter(
        account_type="expense", is_active=True, company_id=asset.company_id
    ).first()
    if not asset_acct or not income_acct or not expense_acct:
        return

    book_value = asset.current_value
    proceeds = disposal_amount
    gain_loss = proceeds - book_value

    je = JournalEntry.objects.create(
        entry_type="journal",
        posting_date=disposal_date,
        reference="DISP/{}/{}".format(asset.asset_code, disposal_date),
        narration="Disposal of {} on {}".format(asset.asset_name, disposal_date),
        status="submitted",
        company_id=asset.company_id,
    )

    # Dr Cash/Proceeds (modelled as income account in demo; real impl would use a cash/bank account)
    if proceeds > 0:
        JournalEntryLine.objects.create(entry=je, account=income_acct,
            debit_amount=proceeds, credit_amount=Decimal("0"),
            description="Disposal proceeds — {}".format(asset.asset_name), company_id=asset.company_id)

    # Cr Asset at cost
    JournalEntryLine.objects.create(entry=je, account=asset_acct,
        debit_amount=Decimal("0"), credit_amount=asset.purchase_price,
        description="Remove asset at cost — {}".format(asset.asset_name), company_id=asset.company_id)

    # Dr Accumulated depreciation
    if asset.accumulated_depreciation > 0:
        JournalEntryLine.objects.create(entry=je, account=asset_acct,
            debit_amount=asset.accumulated_depreciation, credit_amount=Decimal("0"),
            description="Remove accum. depreciation — {}".format(asset.asset_name), company_id=asset.company_id)

    # Gain or loss
    if gain_loss > 0:
        JournalEntryLine.objects.create(entry=je, account=income_acct,
            debit_amount=Decimal("0"), credit_amount=gain_loss,
            description="Gain on disposal — {}".format(asset.asset_name), company_id=asset.company_id)
    elif gain_loss < 0:
        JournalEntryLine.objects.create(entry=je, account=expense_acct,
            debit_amount=abs(gain_loss), credit_amount=Decimal("0"),
            description="Loss on disposal — {}".format(asset.asset_name), company_id=asset.company_id)


def transfer_asset(asset: "Asset", to_location: str, movement_date,
                   to_custodian_id=None, to_custodian_name: str = "", purpose: str = "") -> None:
    """Record a location/custodian transfer and update the asset record."""
    import datetime
    from apps.asset_management.models import AssetMovement

    if isinstance(movement_date, str):
        movement_date = datetime.date.fromisoformat(movement_date)

    AssetMovement.objects.create(
        asset=asset,
        movement_date=movement_date,
        from_location=asset.location,
        to_location=to_location,
        from_custodian_id=asset.custodian_employee_id,
        from_custodian_name=asset.custodian_name,
        to_custodian_id=to_custodian_id,
        to_custodian_name=to_custodian_name,
        purpose=purpose,
        company_id=asset.company_id,
    )
    asset.location = to_location
    if to_custodian_id:
        asset.custodian_employee_id = to_custodian_id
        asset.custodian_name = to_custodian_name
    asset.save(update_fields=["location", "custodian_employee_id", "custodian_name"])


def complete_audit(audit) -> None:
    """
    Finalise a physical audit: count found/missing lines and update totals.
    """
    from django.utils import timezone
    from apps.asset_management.models import AssetAudit, AssetAuditLine

    lines = AssetAuditLine.objects.filter(audit=audit, is_deleted=False)
    found = lines.filter(finding_status=AssetAuditLine.FindingStatus.FOUND).count()
    missing = lines.filter(finding_status=AssetAuditLine.FindingStatus.MISSING).count()

    audit.total_assets_found = found
    audit.total_assets_missing = missing
    audit.total_assets_expected = found + missing
    audit.status = AssetAudit.Status.COMPLETED
    audit.completed_at = timezone.now()
    audit.save(update_fields=[
        "total_assets_found", "total_assets_missing", "total_assets_expected",
        "status", "completed_at",
    ])
