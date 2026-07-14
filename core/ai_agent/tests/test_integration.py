"""
Integration test: full agent run from trigger through to human resolution.

Uses the Lead Qualification agent definition (structured mode, NullGateway).
The NullGateway returns is_complete=True which lets us test the happy path
without a running Ollama instance.

For a more realistic integration test, swap NullGateway for a MockGateway
that returns predetermined step plans for each iteration.
"""
import uuid
from unittest.mock import patch

from django.test import TestCase

from core.ai_agent.agents.lead_qualification import get_seed_data as lead_data
from core.ai_agent.model_gateway import NullGateway
from core.ai_agent.models import (
    AgentDefinition,
    AgentHandoffRequest,
    AgentRun,
    AgentStep,
    AutonomyTier,
)


COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_lead_agent():
    data = lead_data(configured_by_id=uuid.uuid4(), company_id=COMPANY_ID)
    slug = data.pop("slug", "lead_qualification")
    AgentDefinition.objects.filter(slug=slug).delete()
    return AgentDefinition.objects.create(slug=slug, **data)


class FullRunIntegrationTest(TestCase):
    """
    Simulates a complete structured-mode run where the agent completes all steps.
    NullGateway is used; _execute_query and _execute_write are mocked to avoid
    needing actual CRM data.
    """

    def setUp(self):
        self.agent = _make_lead_agent()

    def test_run_completes_when_all_steps_succeed(self):
        run = AgentRun.objects.create(
            agent=self.agent,
            goal="Score new leads",
            context={},
            data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        # Mock all external I/O
        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}), \
             patch.object(executor, "_execute_write", return_value={"done": True}), \
             patch.object(executor, "gateway") as mock_gw:

            mock_gw.draft_text.return_value = "Score: 75\nReasoning: Strong BANT fit"

            executor.execute()

        run.refresh_from_db()
        # Structured script has 5 steps; no handoff triggers fire (no amounts, no regulated actions)
        self.assertEqual(run.status, AgentRun.Status.COMPLETED)
        self.assertFalse(run.failure_reason)

    def test_steps_are_created_and_logged(self):
        run = AgentRun.objects.create(
            agent=self.agent,
            goal="Score new leads",
            context={},
            data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}), \
             patch.object(executor, "_execute_write", return_value={"done": True}), \
             patch.object(executor, "gateway") as mock_gw:

            mock_gw.draft_text.return_value = "LLM output"
            executor.execute()

        steps = AgentStep.objects.filter(run=run).order_by("step_number")
        self.assertGreater(steps.count(), 0)
        # All non-handoff steps should be executed or completed
        for step in steps:
            self.assertIn(step.status, [AgentStep.StepStatus.EXECUTED, AgentStep.StepStatus.HANDED_OFF])


class HandoffResolutionIntegrationTest(TestCase):
    """
    Tests the complete handoff → resolution → re-queue cycle.
    """

    def setUp(self):
        self.agent = _make_lead_agent()

    def _run_until_handoff(self):
        """Create a run that will hit a policy handoff."""
        # Override the agent to trigger a dollar_threshold handoff
        self.agent.handoff_triggers = {"dollar_threshold": 0}  # everything > $0 triggers
        self.agent.save()
        self.agent.step_script = [
            {"type": "write", "entity": "Lead", "action": "update_score",
             "description": "score", "payload": {"amount": 100}, "confidence": 0.95}
        ]
        self.agent.save()

        run = AgentRun.objects.create(
            agent=self.agent,
            goal="test",
            context={},
            data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())
        with patch.object(executor, "_execute_write", return_value={"scored": True}):
            executor.execute()

        run.refresh_from_db()
        return run

    def test_reject_stores_learning_signal_in_context(self):
        run = self._run_until_handoff()
        self.assertEqual(run.status, AgentRun.Status.AWAITING_HUMAN)

        handoff = AgentHandoffRequest.objects.get(run=run)
        from core.ai_agent.handoff import resolve_handoff

        with patch("core.ai_agent.handoff.execute_agent_run") as mock_task:
            resolve_handoff(handoff, "rejected", uuid.uuid4(), notes="Not appropriate")
            mock_task.delay.assert_called_once_with(str(run.id))

        run.refresh_from_db()
        rejections = run.context.get("rejections", [])
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0]["reason"], "Not appropriate")

    def test_approve_re_queues_run(self):
        run = self._run_until_handoff()
        handoff = AgentHandoffRequest.objects.get(run=run)

        from core.ai_agent.handoff import resolve_handoff
        with patch("core.ai_agent.handoff.execute_agent_run") as mock_task:
            resolve_handoff(handoff, "approved", uuid.uuid4(), notes="Looks good")
            mock_task.delay.assert_called_once_with(str(run.id))

        handoff.refresh_from_db()
        self.assertEqual(handoff.status, "approved")

    def test_take_over_kills_run(self):
        run = self._run_until_handoff()
        handoff = AgentHandoffRequest.objects.get(run=run)

        from core.ai_agent.handoff import resolve_handoff
        with patch("core.ai_agent.handoff.execute_agent_run"):
            resolve_handoff(handoff, "taken_over", uuid.uuid4())

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.KILLED)
        handoff.refresh_from_db()
        self.assertEqual(handoff.status, "taken_over")

    def test_edit_approve_stores_edited_payload(self):
        run = self._run_until_handoff()
        handoff = AgentHandoffRequest.objects.get(run=run)

        from core.ai_agent.handoff import resolve_handoff
        edited = {"entity": "Lead", "action": "update_score", "payload": {"score": 80}}
        with patch("core.ai_agent.handoff.execute_agent_run"):
            resolve_handoff(handoff, "edited_approved", uuid.uuid4(), edited_payload=edited)

        handoff.refresh_from_db()
        self.assertEqual(handoff.status, "edited_approved")
        self.assertEqual(handoff.edited_payload, edited)

    def test_handoff_data_gathered_snapshot(self):
        """Handoff packet must include the data gathered up to that point."""
        self.agent.data_gathered = {}
        run = AgentRun.objects.create(
            agent=self.agent,
            goal="test",
            context={},
            data_gathered={"previously_gathered": {"key": "value"}},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        self.agent.handoff_triggers = {"dollar_threshold": 0}
        self.agent.step_script = [
            {"type": "write", "entity": "Lead", "action": "update_score",
             "description": "score", "payload": {"amount": 100}, "confidence": 0.95}
        ]
        self.agent.save()

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())
        with patch.object(executor, "_execute_write", return_value={"scored": True}):
            executor.execute()

        handoff = AgentHandoffRequest.objects.filter(run=run).first()
        self.assertIsNotNone(handoff)
        self.assertIn("previously_gathered", handoff.data_gathered)
