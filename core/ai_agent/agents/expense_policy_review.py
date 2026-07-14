"""
Expense Policy Review Agent.

Goal: surface expense claims already flagged with a policy violation by the
deterministic check in apps.expense.hooks.expense_claim.submit_claim()
(over-limit lines, missing receipts — §6.11), draft a plain-language summary
of those violations for the approver, and escalate high-value flagged claims
for mandatory human review before they can be approved.

This agent does not re-run the policy math itself — that stays a deterministic
hook so it's auditable and always-on regardless of whether AI is enabled. The
agent's job is purely the human-assistance layer: turning a handful of
per-line `violation_reason` strings into one summary an approver can act on
quickly, and making sure the highest-dollar violations don't slip through
without a human decision.

Runs in structured mode (step_script) for reliable behaviour with small local
models — see ADR-0001 Open Question 1.
"""
from __future__ import annotations

EXPENSE_POLICY_AGENT_SLUG = "expense_policy_review"

STEP_SCRIPT = [
    # Step 1: query submitted claims already flagged with a violation
    {
        "type": "query",
        "entity": "ExpenseClaim",
        "action": "read",
        "filter": {"status": "submitted", "has_policy_violations": True},
        "description": "Fetch submitted expense claims flagged with a policy violation",
        "confidence": 1.0,
    },
    # Step 2: draft a plain-language summary of the violations for the approver
    {
        "type": "llm_call",
        "template": "expense_violation_summary",
        "context": {
            "tone": "concise, factual",
        },
        "description": "Draft a summary of policy violations for the approver",
        "confidence": 0.90,
    },
    # Step 3: write the summary as an activity note on the claim
    # (auto_execute_with_review — approver sees the note before deciding)
    {
        "type": "write",
        "entity": "ExpenseClaim",
        "action": "write_note",
        "payload": {},  # populated at runtime from llm_draft_expense_violation_summary result
        "description": "Attach violation summary note to the claim for the approver",
        "confidence": 0.90,
    },
    # Step 4: escalate high-value violating claims for mandatory human review
    {
        "type": "policy_check",
        "check_type": "dollar_threshold",
        "description": "Check if the claim's total exceeds the auto-escalation threshold",
        "confidence": 1.0,
    },
]

HANDOFF_TRIGGERS = {
    "dollar_threshold": 500,   # hand off if a flagged claim totals > $500
    "regulated_actions": [],
}

AUTONOMY_CONFIG = {
    "ExpenseClaim:read": "auto_execute_reversible",
    "ExpenseClaim:write_note": "auto_execute_with_review",
}

ALLOWED_ACTIONS = [
    {"entity": "ExpenseClaim", "actions": ["read", "write_note"]},
]


def get_seed_data(configured_by_id, company_id=None):
    """Return kwargs for AgentDefinition.objects.create() or get_or_create()."""
    return {
        "slug": EXPENSE_POLICY_AGENT_SLUG,
        "name": "Expense Policy Review Agent",
        "goal_template": "Review submitted expense claims flagged with policy violations, draft a summary for the approver, and escalate high-value claims for mandatory review.",
        "allowed_actions": ALLOWED_ACTIONS,
        "allowed_mcp_tools": [],
        "autonomy_config": AUTONOMY_CONFIG,
        "confidence_threshold": 0.80,
        "handoff_triggers": HANDOFF_TRIGGERS,
        "max_steps": 20,
        "rate_limit_per_hour": 10,
        "planning_mode": "structured",
        "step_script": STEP_SCRIPT,
        "configured_by_id": configured_by_id,
        "service_account_id": None,
        "company_id": company_id,
        "is_active": True,
        "is_paused": False,
    }
