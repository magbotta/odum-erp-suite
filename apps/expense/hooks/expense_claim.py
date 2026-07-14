"""Hooks for ExpenseClaim: policy validation, GL posting, reimbursement."""
from __future__ import annotations

from decimal import Decimal


def submit_claim(claim) -> None:
    """
    On submit: auto-number, run policy checks on every line, aggregate totals,
    then flip status to submitted.  Policy violations are flagged but do NOT
    block submission — they are surfaced to the approver for a decision.
    """
    from core.numbering.service import get_next_number

    if not claim.claim_number:
        claim.claim_number = get_next_number("EXP", claim.company_id)
        claim.save(update_fields=["claim_number"])

    _run_policy_checks(claim)
    _aggregate_totals(claim)


def _run_policy_checks(claim) -> None:
    """Flag each line that breaches its category or policy limits."""
    policy = claim.policy
    any_violation = False

    for line in claim.lines.select_related("category").all():
        violations = []
        cat = line.category

        # Receipt threshold check
        receipt_threshold = cat.requires_receipt_above or Decimal("0")
        if receipt_threshold > 0 and line.amount > receipt_threshold and not line.receipt_attached:
            violations.append(
                "Receipt required for {} > {:.2f}".format(cat.name, receipt_threshold)
            )

        # Per-claim limit (category default, overridden by policy rule)
        per_claim_limit = _policy_rule_value(policy, cat, "per_claim_limit") or cat.per_claim_limit
        if per_claim_limit > 0 and line.amount > per_claim_limit:
            violations.append(
                "{} claim limit is {:.2f}; submitted {:.2f}".format(
                    cat.name, per_claim_limit, line.amount
                )
            )

        if violations:
            line.policy_violation = True
            line.violation_reason = "; ".join(violations)
            any_violation = True
        else:
            line.policy_violation = False
            line.violation_reason = ""

        line.amount_in_company_currency = (
            line.amount * (line.exchange_rate or Decimal("1"))
        ).quantize(Decimal("0.01"))
        line.sanctioned_amount = line.amount_in_company_currency
        line.save(update_fields=[
            "policy_violation", "violation_reason",
            "amount_in_company_currency", "sanctioned_amount",
        ])

    claim.has_policy_violations = any_violation
    claim.save(update_fields=["has_policy_violations"])


def _policy_rule_value(policy, category, field: str) -> Decimal:
    """Return the policy-rule override value for a field, or 0 if none."""
    if policy is None:
        return Decimal("0")
    from apps.expense.models import ExpensePolicyRule
    try:
        rule = ExpensePolicyRule.objects.get(policy=policy, category=category)
        return getattr(rule, field) or Decimal("0")
    except ExpensePolicyRule.DoesNotExist:
        return Decimal("0")


def _aggregate_totals(claim) -> None:
    """Sum line amounts into claim totals."""
    lines = list(claim.lines.all())
    total = sum(l.amount_in_company_currency for l in lines)
    sanctioned = sum(l.sanctioned_amount for l in lines)
    claim.total_claimed_amount = total
    claim.total_sanctioned_amount = sanctioned
    claim.save(update_fields=["total_claimed_amount", "total_sanctioned_amount"])


def approve_claim(claim, approver_id=None) -> None:
    """Approve a submitted claim; optionally override sanctioned amounts first."""
    from django.utils import timezone

    claim.status = "approved"
    claim.approved_by_id = approver_id
    claim.approved_at = timezone.now()
    claim.save(update_fields=["status", "approved_by_id", "approved_at"])


def reject_claim(claim, reason: str = "", approver_id=None) -> None:
    """Reject a submitted claim with a mandatory reason."""
    from django.utils import timezone

    claim.status = "rejected"
    claim.rejection_reason = reason
    claim.approved_by_id = approver_id
    claim.approved_at = timezone.now()
    claim.save(update_fields=["status", "rejection_reason", "approved_by_id", "approved_at"])


def reimburse_claim(claim, payment_reference: str = "", reimbursed_at=None) -> None:
    """
    Mark an approved claim as reimbursed and post to GL via Accounting journal entry.
    Cross-app: creates a JournalEntry (Dr Expense account, Cr Payable/Employee).
    """
    import datetime

    from django.utils import timezone

    today = reimbursed_at or datetime.date.today()
    claim.status = "reimbursed"
    claim.reimbursed_at = today
    claim.payment_reference = payment_reference
    claim.save(update_fields=["status", "reimbursed_at", "payment_reference"])

    _post_to_gl(claim, today)


def _post_to_gl(claim, posting_date) -> None:
    """
    Create a JournalEntry in Accounting to record the expense reimbursement.
    One debit line per expense category (aggregated), one credit (employee payable).
    Skips silently if no GL accounts are mapped on any category — GL accounts
    are configured by the accountant on each ExpenseCategory after setup.
    """
    try:
        from apps.accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
    except ImportError:
        return

    from collections import defaultdict
    by_account_id = defaultdict(Decimal)
    for line in claim.lines.select_related("category").all():
        if line.category.gl_account_id:
            by_account_id[line.category.gl_account_id] += line.sanctioned_amount

    if not by_account_id:
        # No GL accounts configured on categories — skip GL posting
        return

    # Resolve ChartOfAccount objects (FK is non-nullable on JournalEntryLine)
    account_objs = {
        str(a.pk): a
        for a in ChartOfAccount.objects.filter(pk__in=by_account_id.keys())
    }
    if not account_objs:
        return

    from core.numbering.service import get_next_number

    je = JournalEntry.objects.create(
        reference=get_next_number("JV", claim.company_id),
        posting_date=posting_date,
        entry_type="journal",
        narration="Expense reimbursement: {}".format(claim.claim_number),
        total_debit=claim.total_sanctioned_amount,
        total_credit=claim.total_sanctioned_amount,
        status="submitted",
        voucher_type="ExpenseClaim",
        voucher_no=claim.claim_number,
        company_id=claim.company_id,
    )

    for acct_id, amount in by_account_id.items():
        acct_obj = account_objs.get(str(acct_id))
        if acct_obj is None:
            continue
        JournalEntryLine.objects.create(
            entry=je,
            account=acct_obj,
            debit_amount=amount,
            credit_amount=Decimal("0"),
            party_type="Employee",
            party_id=claim.employee_id,
            description=claim.claim_number,
            company_id=claim.company_id,
        )
