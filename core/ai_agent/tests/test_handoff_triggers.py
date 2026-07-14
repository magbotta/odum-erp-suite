"""
Unit tests for handoff trigger logic.

Tests that the executor creates a handoff (and suspends the run) under each
trigger condition, without needing a real LLM or real entity records.
"""
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.ai_agent.models import (
    AgentDefinition,
    AgentHandoffRequest,
    AgentRun,
    AgentStep,
)


def _make_agent(**overrides):
    defaults = dict(
        slug="test-agent-{0}".format(uuid.uuid4().hex[:6]),
        name="Test Agent",
        goal_template="Test goal",
        allowed_actions=[{"entity": "Lead", "actions": ["read", "update_score"]}],
        autonomy_config={"Lead:read": "auto_execute_reversible", "Lead:update_score": "auto_execute_reversible"},
        confidence_threshold=0.80,
        handoff_triggers={"dollar_threshold": 1000},
        max_steps=30,
        rate_limit_per_hour=10,
        planning_mode="structured",
        step_script=[
            {"type": "query", "entity": "Lead", "action": "read",
             "filter": {}, "description": "read leads", "confidence": 1.0}
        ],
        configured_by_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return AgentDefinition.objects.create(**defaults)


def _make_run(agent, **overrides):
    defaults = dict(
        agent=agent,
        goal="test goal",
        context={},
        data_gathered={},
        triggered_by_id=uuid.uuid4(),
        company_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    defaults.update(overrides)
    return AgentRun.objects.create(**defaults)


class LowConfidenceTriggerTest(TestCase):

    def test_handoff_created_when_confidence_below_threshold(self):
        agent = _make_agent(
            confidence_threshold=0.80,
            step_script=[
                {"type": "write", "entity": "Lead", "action": "update_score",
                 "description": "score lead", "confidence": 0.60}  # below 0.80
            ],
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor

        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_plan_structured", return_value={
            "step": {
                "type": "write", "entity": "Lead", "action": "update_score",
                "description": "score lead", "payload": {},
            },
            "reasoning": "score the lead",
            "confidence": 0.60,
            "is_complete": False,
        }):
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)

        handoff = AgentHandoffRequest.objects.filter(run=run).first()
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff.trigger_reason, AgentHandoffRequest.TriggerReason.LOW_CONFIDENCE)

    def test_no_handoff_when_confidence_meets_threshold(self):
        """Confidence == threshold should NOT trigger a handoff."""
        agent = _make_agent(
            confidence_threshold=0.80,
            step_script=[
                {"type": "query", "entity": "Lead", "action": "read",
                 "filter": {}, "description": "read leads", "confidence": 0.80}
            ],
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor

        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}):
            executor.execute()

        # No suspending handoff — run should complete (script has only one query step)
        run.refresh_from_db()
        suspending_handoffs = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.LOW_CONFIDENCE,
        )
        self.assertEqual(suspending_handoffs.count(), 0)


class DollarThresholdTriggerTest(TestCase):

    def test_handoff_created_when_amount_exceeds_threshold(self):
        agent = _make_agent(
            handoff_triggers={"dollar_threshold": 500},
            step_script=[
                {"type": "write", "entity": "Lead", "action": "update_score",
                 "description": "score", "payload": {"amount": 1500}, "confidence": 0.95}
            ],
            autonomy_config={"Lead:update_score": "auto_execute_reversible"},
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor

        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_write", return_value={"scored": True}):
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)
        handoff = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
        ).first()
        self.assertIsNotNone(handoff)

    def test_no_handoff_when_amount_under_threshold(self):
        agent = _make_agent(
            handoff_triggers={"dollar_threshold": 5000},
            step_script=[
                {"type": "write", "entity": "Lead", "action": "update_score",
                 "description": "score", "payload": {"amount": 200}, "confidence": 0.95},
                {"type": "query", "entity": "Lead", "action": "read",
                 "filter": {}, "description": "verify", "confidence": 1.0},
            ],
            autonomy_config={"Lead:update_score": "auto_execute_reversible",
                             "Lead:read": "auto_execute_reversible"},
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_write", return_value={"scored": True}), \
             patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}):
            executor.execute()

        run.refresh_from_db()
        boundary_handoffs = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
        )
        self.assertEqual(boundary_handoffs.count(), 0)


class RegulatedActionTriggerTest(TestCase):

    def test_regulated_action_triggers_handoff(self):
        agent = _make_agent(
            allowed_actions=[{"entity": "SalesInvoice", "actions": ["read", "write_off"]}],
            autonomy_config={"SalesInvoice:write_off": "auto_execute_reversible"},
            handoff_triggers={"regulated_actions": ["write_off"]},
            step_script=[
                {"type": "write", "entity": "SalesInvoice", "action": "write_off",
                 "description": "write off invoice", "payload": {}, "confidence": 0.92}
            ],
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_write", return_value={"done": True}):
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)
        handoff = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
        ).first()
        self.assertIsNotNone(handoff)
        self.assertIn("regulated", handoff.trigger_detail.lower())


class MaxStepsTriggerTest(TestCase):

    def test_max_steps_triggers_handoff(self):
        """Agent with max_steps=2 that never completes should be handed off."""
        agent = _make_agent(
            max_steps=2,
            step_script=[
                {"type": "query", "entity": "Lead", "action": "read",
                 "filter": {}, "description": "step 1", "confidence": 1.0},
                {"type": "query", "entity": "Lead", "action": "read",
                 "filter": {}, "description": "step 2", "confidence": 1.0},
                {"type": "query", "entity": "Lead", "action": "read",
                 "filter": {}, "description": "step 3 — beyond max", "confidence": 1.0},
            ],
        )
        run = _make_run(agent)

        from core.ai_agent.model_gateway import NullGateway
        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}):
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)
        handoff = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.MAX_STEPS,
        ).first()
        self.assertIsNotNone(handoff)
