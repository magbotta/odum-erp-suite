"""
Unit tests for autonomy-tier enforcement.

Verifies:
  - SUGGEST_ONLY actions always produce a handoff, never execute
  - HIGH_RISK actions are floored at auto_execute_with_review (not auto_execute_reversible or fully_autonomous)
  - AUTO_WITH_REVIEW actions execute AND produce a review-queue handoff
  - Actions not in the allow-list raise PolicyViolation
"""
import uuid
from unittest.mock import patch

from django.test import TestCase

from core.ai_agent.models import (
    AgentDefinition,
    AgentHandoffRequest,
    AgentRun,
    AgentStep,
    AutonomyTier,
)
from core.ai_agent.permission_guard import PermissionGuard, PolicyViolation, HIGH_RISK_ACTIONS


def _make_agent(**overrides):
    defaults = dict(
        slug="tier-test-{0}".format(uuid.uuid4().hex[:6]),
        name="Tier Test Agent",
        goal_template="goal",
        allowed_actions=[
            {"entity": "Lead", "actions": ["read", "update_score", "update_status", "submit"]},
            {"entity": "SalesInvoice", "actions": ["read", "write_note", "write_off"]},
        ],
        autonomy_config={},
        confidence_threshold=0.50,
        handoff_triggers={},
        max_steps=20,
        rate_limit_per_hour=10,
        planning_mode="structured",
        step_script=[],
        configured_by_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return AgentDefinition.objects.create(**defaults)


class PermissionGuardAllowListTest(TestCase):

    def test_action_not_in_allowlist_raises(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "Lead", "actions": ["read"]}]
        )
        guard = PermissionGuard(agent)
        with self.assertRaises(PolicyViolation):
            guard.validate_action("Lead", "delete")

    def test_entity_not_in_allowlist_raises(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "Lead", "actions": ["read"]}]
        )
        guard = PermissionGuard(agent)
        with self.assertRaises(PolicyViolation):
            guard.validate_action("SalesInvoice", "read")

    def test_allowed_action_returns_tier(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "Lead", "actions": ["read"]}],
            autonomy_config={"Lead:read": "auto_execute_reversible"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("Lead", "read")
        self.assertEqual(tier, AutonomyTier.AUTO_REVERSIBLE)


class HighRiskFloorTest(TestCase):

    def test_submit_cannot_be_auto_reversible(self):
        """'submit' is a high-risk action; auto_execute_reversible must be floored up."""
        agent = _make_agent(
            autonomy_config={"Lead:submit": "auto_execute_reversible"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("Lead", "submit")
        # Must be suggest_only (the floor is auto_with_review, but auto_execute_reversible
        # is below that, so the guard upgrades to suggest_only per _apply_high_risk_floor)
        self.assertEqual(tier, AutonomyTier.SUGGEST_ONLY)

    def test_write_off_cannot_be_fully_autonomous(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "SalesInvoice", "actions": ["write_off"]}],
            autonomy_config={"SalesInvoice:write_off": "fully_autonomous"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("SalesInvoice", "write_off")
        self.assertEqual(tier, AutonomyTier.SUGGEST_ONLY)

    def test_send_email_cannot_be_auto_reversible(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "Lead", "actions": ["read", "send_email"]}],
            autonomy_config={"Lead:send_email": "auto_execute_reversible"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("Lead", "send_email")
        self.assertEqual(tier, AutonomyTier.SUGGEST_ONLY)

    def test_non_high_risk_action_can_be_auto_reversible(self):
        agent = _make_agent(
            autonomy_config={"Lead:update_score": "auto_execute_reversible"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("Lead", "update_score")
        self.assertEqual(tier, AutonomyTier.AUTO_REVERSIBLE)

    def test_non_high_risk_action_can_be_fully_autonomous(self):
        agent = _make_agent(
            autonomy_config={"Lead:update_score": "fully_autonomous"},
        )
        guard = PermissionGuard(agent)
        tier = guard.validate_action("Lead", "update_score")
        self.assertEqual(tier, AutonomyTier.FULLY_AUTONOMOUS)


class SuggestOnlyExecutionTest(TestCase):

    def _make_run(self, agent):
        return AgentRun.objects.create(
            agent=agent, goal="goal", context={}, data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )

    def test_suggest_only_never_executes(self):
        """SUGGEST_ONLY action must produce a handoff without calling _execute_write."""
        agent = _make_agent(
            step_script=[{
                "type": "write", "entity": "Lead", "action": "update_status",
                "description": "update status", "payload": {}, "confidence": 0.92,
            }],
            autonomy_config={"Lead:update_status": "suggest_only"},
        )
        run = self._make_run(agent)

        from core.ai_agent.executor import AgentRunExecutor
        from core.ai_agent.model_gateway import NullGateway
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        write_called = []
        with patch.object(executor, "_execute_write", side_effect=lambda *a, **kw: write_called.append(1) or {}):
            executor.execute()

        self.assertEqual(len(write_called), 0, "_execute_write must not be called for suggest_only")
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)
        handoff = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REQUIRES_APPROVAL,
        ).first()
        self.assertIsNotNone(handoff)

    def test_auto_with_review_executes_and_creates_review_entry(self):
        """AUTO_WITH_REVIEW must execute AND produce a review-queue handoff."""
        agent = _make_agent(
            step_script=[{
                "type": "write", "entity": "Lead", "action": "update_status",
                "description": "update status", "payload": {}, "confidence": 0.92,
            }],
            autonomy_config={"Lead:update_status": "auto_execute_with_review"},
        )
        run = self._make_run(agent)

        from core.ai_agent.executor import AgentRunExecutor
        from core.ai_agent.model_gateway import NullGateway
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        write_called = []
        with patch.object(executor, "_execute_write", side_effect=lambda *a, **kw: write_called.append(1) or {"updated": True}):
            executor.execute()

        self.assertEqual(len(write_called), 1, "_execute_write must be called for auto_execute_with_review")
        review_entry = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REVIEW_QUEUE,
        ).first()
        self.assertIsNotNone(review_entry)
        # Run should NOT be suspended — it keeps going after a review-queue entry
        # (the run has only one step so it may complete)

    def test_mcp_tool_not_in_allowlist_raises_policy_violation(self):
        agent = _make_agent(
            allowed_mcp_tools=[
                {"server_url": "http://carrier.local", "tool_name": "track_shipment", "description": "track"},
            ],
        )
        guard = PermissionGuard(agent)
        with self.assertRaises(PolicyViolation):
            guard.validate_mcp_tool("http://other.server", "steal_data")

    def test_mcp_tool_in_allowlist_passes(self):
        agent = _make_agent(
            allowed_mcp_tools=[
                {"server_url": "http://carrier.local", "tool_name": "track_shipment", "description": "track"},
            ],
        )
        guard = PermissionGuard(agent)
        # Should not raise
        guard.validate_mcp_tool("http://carrier.local", "track_shipment")
