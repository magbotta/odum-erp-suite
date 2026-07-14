"""
Tests proving the kill switch halts in-flight runs and routes them to handoff.

Covers:
  1. AgentDefinition.is_paused = True → executor detects on next iteration → handoff + killed
  2. AgentRun.kill_requested = True → executor detects on next iteration → handoff + killed
  3. Platform-wide kill via /admin/kill-all → all running runs receive kill_requested
"""
import uuid
from unittest.mock import patch, call

from django.test import TestCase

from core.ai_agent.model_gateway import NullGateway
from core.ai_agent.models import (
    AgentDefinition,
    AgentHandoffRequest,
    AgentRun,
    AgentStep,
)


COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_multi_step_agent(**overrides):
    """Agent with two query steps so the loop iterates before completing."""
    defaults = dict(
        slug="kill-test-{0}".format(uuid.uuid4().hex[:6]),
        name="Kill Test Agent",
        goal_template="goal",
        allowed_actions=[{"entity": "Lead", "actions": ["read"]}],
        autonomy_config={"Lead:read": "auto_execute_reversible"},
        confidence_threshold=0.50,
        handoff_triggers={},
        max_steps=30,
        rate_limit_per_hour=10,
        planning_mode="structured",
        step_script=[
            {"type": "query", "entity": "Lead", "action": "read",
             "filter": {}, "description": "step 1", "confidence": 1.0},
            {"type": "query", "entity": "Lead", "action": "read",
             "filter": {}, "description": "step 2", "confidence": 1.0},
        ],
        configured_by_id=uuid.uuid4(),
        is_paused=False,
    )
    defaults.update(overrides)
    return AgentDefinition.objects.create(**defaults)


def _make_run(agent):
    return AgentRun.objects.create(
        agent=agent,
        goal="test kill switch",
        context={},
        data_gathered={},
        triggered_by_id=uuid.uuid4(),
        company_id=COMPANY_ID,
    )


class KillRequestedTest(TestCase):
    """
    Sets kill_requested=True on the run BEFORE execution begins.
    The executor must detect this on the first iteration, create a
    KILL_REQUESTED handoff, and mark the run as KILLED.
    """

    def test_kill_requested_on_run_halts_and_creates_handoff(self):
        agent = _make_multi_step_agent()
        run = _make_run(agent)
        AgentRun.objects.filter(pk=run.pk).update(kill_requested=True)

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        query_called = []
        with patch.object(executor, "_execute_query", side_effect=lambda *a, **kw: query_called.append(1) or {}):
            executor.execute()

        # No query step should have executed
        self.assertEqual(len(query_called), 0)

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.KILLED)

        handoff = AgentHandoffRequest.objects.filter(run=run).first()
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff.trigger_reason, AgentHandoffRequest.TriggerReason.KILL_REQUESTED)

    def test_kill_on_second_iteration_stops_after_first_step(self):
        """
        Kill set mid-run: executor completes step 1, then detects kill on step 2.
        """
        agent = _make_multi_step_agent()
        run = _make_run(agent)
        call_count = [0]

        def fake_query(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # After first step completes, set kill_requested
                AgentRun.objects.filter(pk=run.pk).update(kill_requested=True)
            return {"records": [], "count": 0}

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())
        with patch.object(executor, "_execute_query", side_effect=fake_query):
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.KILLED)
        # First step executed, second was not
        self.assertEqual(call_count[0], 1)

        handoff = AgentHandoffRequest.objects.filter(
            run=run,
            trigger_reason=AgentHandoffRequest.TriggerReason.KILL_REQUESTED,
        ).first()
        self.assertIsNotNone(handoff)


class AgentPausedTest(TestCase):
    """
    Sets agent.is_paused=True BEFORE execution begins.
    The executor must detect this on the first iteration and halt.
    """

    def test_paused_agent_creates_kill_handoff(self):
        agent = _make_multi_step_agent(is_paused=True)
        run = _make_run(agent)

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        query_called = []
        with patch.object(executor, "_execute_query", side_effect=lambda *a, **kw: query_called.append(1) or {}):
            executor.execute()

        self.assertEqual(len(query_called), 0)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.KILLED)

        handoff = AgentHandoffRequest.objects.filter(run=run).first()
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff.trigger_reason, AgentHandoffRequest.TriggerReason.KILL_REQUESTED)


class PlatformKillSwitchAPITest(TestCase):
    """
    Tests the /admin/kill-all endpoint signals all in-flight runs.
    Does not test Celery revocation (that's tested by asserting revoke_agent_run_task.delay is called).
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_user(
            email="killswitch-admin@test.local",
            password="password123",
            is_staff=True,
            is_superuser=True,
        )

    def test_kill_all_sets_kill_requested_on_all_running_runs(self):
        agent1 = _make_multi_step_agent()
        agent2 = _make_multi_step_agent()

        run1 = AgentRun.objects.create(
            agent=agent1, goal="run1", context={}, data_gathered={},
            triggered_by_id=self.admin.id, company_id=COMPANY_ID,
            status=AgentRun.Status.RUNNING,
        )
        run2 = AgentRun.objects.create(
            agent=agent2, goal="run2", context={}, data_gathered={},
            triggered_by_id=self.admin.id, company_id=COMPANY_ID,
            status=AgentRun.Status.RUNNING,
        )

        from core.ai_agent.api import kill_all_agents
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.user = self.admin

        with patch("core.ai_agent.api.revoke_agent_run_task") as mock_revoke:
            result = kill_all_agents(mock_request)

        self.assertTrue(result["ok"])

        run1.refresh_from_db()
        run2.refresh_from_db()
        self.assertTrue(run1.kill_requested)
        self.assertTrue(run2.kill_requested)

        # All definitions should be paused
        paused_count = AgentDefinition.objects.filter(is_paused=True).count()
        total_count = AgentDefinition.objects.count()
        self.assertEqual(paused_count, total_count)

    def test_kill_all_non_staff_forbidden(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        regular = User.objects.create_user(
            email="regular-{0}@test.local".format(uuid.uuid4().hex[:4]),
            password="pw",
            is_staff=False,
        )
        from core.ai_agent.api import kill_all_agents
        from ninja.errors import HttpError
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.user = regular

        with self.assertRaises(HttpError) as ctx:
            kill_all_agents(mock_request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_kill_all_leaves_completed_runs_untouched(self):
        agent = _make_multi_step_agent()
        completed_run = AgentRun.objects.create(
            agent=agent, goal="done", context={}, data_gathered={},
            triggered_by_id=self.admin.id, company_id=COMPANY_ID,
            status=AgentRun.Status.COMPLETED,
        )

        from core.ai_agent.api import kill_all_agents
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.user = self.admin

        with patch("core.ai_agent.api.revoke_agent_run_task"):
            kill_all_agents(mock_request)

        completed_run.refresh_from_db()
        # Completed run should NOT have kill_requested set
        self.assertFalse(completed_run.kill_requested)
        self.assertEqual(completed_run.status, AgentRun.Status.COMPLETED)
