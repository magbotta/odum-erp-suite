"""
Collections / Dunning Agent definition.

Goal: scan overdue Sales Invoices, draft dunning emails, write activity notes.
Hand off before any write-off action or when invoice amount > threshold.

Runs in structured mode (step_script) for reliable behaviour with small local models.
"""
from __future__ import annotations

COLLECTIONS_AGENT_SLUG = "collections_dunning"

STEP_SCRIPT = [
    # Step 1: query overdue invoices
    {
        "type": "query",
        "entity": "SalesInvoice",
        "action": "read",
        "filter": {"status": "overdue"},
        "description": "Fetch all overdue sales invoices for the company",
        "confidence": 1.0,
    },
    # Step 2: policy check — are any above the handoff threshold?
    # (The executor evaluates each matching record; threshold in handoff_triggers)
    {
        "type": "policy_check",
        "check_type": "dollar_threshold",
        "amount_field": "grand_total",
        "description": "Check if any overdue invoice exceeds the policy dollar threshold",
        "confidence": 1.0,
    },
    # Step 3: draft a dunning email for each overdue invoice
    {
        "type": "llm_call",
        "template": "dunning_email",
        "context": {
            "tone": "professional but firm",
            "include_payment_link": True,
        },
        "description": "Draft dunning email text for overdue invoices",
        "confidence": 0.90,
    },
    # Step 4: write the drafted email as an activity note on each invoice
    # (auto_execute_with_review — human reviews the note before actual send)
    {
        "type": "write",
        "entity": "SalesInvoice",
        "action": "write_note",
        "payload": {},  # populated at runtime from llm_draft_dunning_email result
        "description": "Create activity note with drafted dunning email on the invoice",
        "confidence": 0.90,
    },
]

HANDOFF_TRIGGERS = {
    "dollar_threshold": 1000,          # hand off if any invoice > $1000
    "regulated_actions": ["write_off", "bad_debt"],
    "vip_accounts": True,
}

AUTONOMY_CONFIG = {
    "SalesInvoice:read": "auto_execute_reversible",
    "SalesInvoice:write_note": "auto_execute_with_review",
    # write_off is NOT listed here — it is a regulated_action and would
    # also hit the high-risk floor in PermissionGuard → suggest_only
}

ALLOWED_ACTIONS = [
    {"entity": "SalesInvoice", "actions": ["read", "write_note"]},
]


def get_seed_data(configured_by_id, company_id=None):
    """Return kwargs for AgentDefinition.objects.create() or get_or_create()."""
    return {
        "slug": COLLECTIONS_AGENT_SLUG,
        "name": "Collections & Dunning Agent",
        "goal_template": "Review all overdue sales invoices for company, draft dunning communications, and escalate high-value accounts for human follow-up.",
        "allowed_actions": ALLOWED_ACTIONS,
        "allowed_mcp_tools": [],
        "autonomy_config": AUTONOMY_CONFIG,
        "confidence_threshold": 0.80,
        "handoff_triggers": HANDOFF_TRIGGERS,
        "max_steps": 20,
        "rate_limit_per_hour": 5,
        "planning_mode": "structured",
        "step_script": STEP_SCRIPT,
        "configured_by_id": configured_by_id,
        "service_account_id": None,
        "company_id": company_id,
        "is_active": True,
        "is_paused": False,
    }
