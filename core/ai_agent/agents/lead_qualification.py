"""
Lead Qualification Agent definition.

Goal: score and route unqualified inbound CRM Leads.
Auto-updates lead score (reversible). Hands off once a deal crosses the
configured value threshold or score reaches the "hot" threshold.

Runs in structured mode for reliable behaviour with small local models.
"""
from __future__ import annotations

LEAD_QUAL_AGENT_SLUG = "lead_qualification"

STEP_SCRIPT = [
    # Step 1: query unscored/new leads
    {
        "type": "query",
        "entity": "Lead",
        "action": "read",
        "filter": {"status": "new"},
        "description": "Fetch all new/unqualified leads for scoring",
        "confidence": 1.0,
    },
    # Step 2: score each lead against BANT criteria using LLM
    {
        "type": "llm_call",
        "template": "lead_bant_score",
        "context": {
            "criteria": "Budget, Authority, Need, Timeline (BANT)",
            "output_format": "score 0-100 with reasoning",
        },
        "description": "Score each lead against BANT qualification criteria",
        "confidence": 0.85,
    },
    # Step 3: write score back to the Lead record
    # (auto_execute_reversible — scoring is non-destructive and undoable)
    {
        "type": "write",
        "entity": "Lead",
        "action": "update_score",
        "description": "Write qualification score to lead record",
        "confidence": 0.95,
    },
    # Step 4: check if any lead exceeds deal-value threshold → handoff
    {
        "type": "policy_check",
        "check_type": "dollar_threshold",
        "amount_field": "estimated_value",
        "description": "Check if any lead's estimated value exceeds the handoff threshold",
        "confidence": 1.0,
    },
    # Step 5: for low-scoring leads, update status to disqualified
    # (auto_execute_with_review — status change goes to review queue)
    {
        "type": "write",
        "entity": "Lead",
        "action": "update_status",
        "payload": {"status": "disqualified", "score_threshold": 20},
        "description": "Mark leads scoring < 20 as disqualified (post-hoc review)",
        "confidence": 0.85,
    },
]

HANDOFF_TRIGGERS = {
    "dollar_threshold": 5000,        # hand off if estimated deal > $5000
    "regulated_actions": [],
}

AUTONOMY_CONFIG = {
    "Lead:read": "auto_execute_reversible",
    "Lead:update_score": "auto_execute_reversible",     # scoring is reversible
    "Lead:update_status": "auto_execute_with_review",   # status change = review queue
    "Lead:assign": "suggest_only",                      # assignment is human decision
}

ALLOWED_ACTIONS = [
    {"entity": "Lead", "actions": ["read", "update_score", "update_status"]},
]


def get_seed_data(configured_by_id, company_id=None):
    """Return kwargs for AgentDefinition.objects.create() or get_or_create()."""
    return {
        "slug": LEAD_QUAL_AGENT_SLUG,
        "name": "Lead Qualification Agent",
        "goal_template": "Score and qualify all new inbound leads for the company using BANT criteria. Update scores, disqualify low-quality leads, and escalate high-value opportunities for sales team assignment.",
        "allowed_actions": ALLOWED_ACTIONS,
        "allowed_mcp_tools": [],
        "autonomy_config": AUTONOMY_CONFIG,
        "confidence_threshold": 0.75,
        "handoff_triggers": HANDOFF_TRIGGERS,
        "max_steps": 25,
        "rate_limit_per_hour": 10,
        "planning_mode": "structured",
        "step_script": STEP_SCRIPT,
        "configured_by_id": configured_by_id,
        "service_account_id": None,
        "company_id": company_id,
        "is_active": True,
        "is_paused": False,
    }
