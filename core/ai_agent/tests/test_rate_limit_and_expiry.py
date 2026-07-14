"""
Tests for two safety mechanisms defined in ADR-0001 but previously unenforced:

  1. AgentDefinition.rate_limit_per_hour — caps how many runs /runs can trigger
     per company per rolling hour.
  2. AgentHandoffRequest expiry — expire_stale_handoffs() now respects an
     explicit expires_at, and fails the orphaned AgentRun when a suspending
     handoff expires unresolved.
"""
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from core.ai_agent.models import AgentDefinition, AgentHandoffRequest, AgentRun

COMPANY_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
COMPANY_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


def _make_agent(**overrides):
    defaults = dict(
        slug="rl-test-{0}".format(uuid.uuid4().hex[:6]),
        name="Rate Limit Test Agent",
        goal_template="goal",
        allowed_actions=[{"entity": "Lead", "actions": ["read"]}],
        autonomy_config={"Lead:read": "auto_execute_reversible"},
        confidence_threshold=0.50,
        handoff_triggers={},
        max_steps=5,
        rate_limit_per_hour=2,
        planning_mode="structured",
        step_script=[],
        configured_by_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return AgentDefinition.objects.create(**defaults)


class RateLimitTest(TestCase):

    def test_trigger_allowed_under_limit(self):
        agent = _make_agent(rate_limit_per_hour=2)
        from core.ai_agent.api import trigger_agent_run, TriggerRunIn

        request = MagicMock()
        request.user.id = uuid.uuid4()
        request.GET = {"company_id": str(COMPANY_A)}
        request.headers = {}

        with patch("core.ai_agent.api.execute_agent_run") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            result = trigger_agent_run(request, TriggerRunIn(agent_id=str(agent.id), context={}))

        self.assertEqual(AgentRun.objects.filter(agent=agent).count(), 1)
        self.assertEqual(result["status"], AgentRun.Status.PENDING)

    def test_trigger_rejected_once_limit_reached(self):
        agent = _make_agent(rate_limit_per_hour=2)
        from core.ai_agent.api import trigger_agent_run, TriggerRunIn
        from ninja.errors import HttpError

        request = MagicMock()
        request.user.id = uuid.uuid4()
        request.GET = {"company_id": str(COMPANY_A)}
        request.headers = {}

        with patch("core.ai_agent.api.execute_agent_run") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            trigger_agent_run(request, TriggerRunIn(agent_id=str(agent.id), context={}))
            trigger_agent_run(request, TriggerRunIn(agent_id=str(agent.id), context={}))

            with self.assertRaises(HttpError) as ctx:
                trigger_agent_run(request, TriggerRunIn(agent_id=str(agent.id), context={}))

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(AgentRun.objects.filter(agent=agent).count(), 2)

    def test_rate_limit_is_scoped_per_company(self):
        """Company B's runs must not count against Company A's quota."""
        agent = _make_agent(rate_limit_per_hour=1)
        from core.ai_agent.api import trigger_agent_run, TriggerRunIn

        request_a = MagicMock()
        request_a.user.id = uuid.uuid4()
        request_a.GET = {"company_id": str(COMPANY_A)}
        request_a.headers = {}

        request_b = MagicMock()
        request_b.user.id = uuid.uuid4()
        request_b.GET = {"company_id": str(COMPANY_B)}
        request_b.headers = {}

        with patch("core.ai_agent.api.execute_agent_run") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            trigger_agent_run(request_a, TriggerRunIn(agent_id=str(agent.id), context={}))
            # Company B should still be allowed even though A is now at quota
            result_b = trigger_agent_run(request_b, TriggerRunIn(agent_id=str(agent.id), context={}))

        self.assertEqual(result_b["status"], AgentRun.Status.PENDING)

    def test_old_runs_outside_window_dont_count(self):
        agent = _make_agent(rate_limit_per_hour=1)
        stale_run = AgentRun.objects.create(
            agent=agent, goal="old", context={}, data_gathered={},
            triggered_by_id=uuid.uuid4(), company_id=COMPANY_A,
        )
        AgentRun.objects.filter(pk=stale_run.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )

        from core.ai_agent.api import trigger_agent_run, TriggerRunIn

        request = MagicMock()
        request.user.id = uuid.uuid4()
        request.GET = {"company_id": str(COMPANY_A)}
        request.headers = {}

        with patch("core.ai_agent.api.execute_agent_run") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-1")
            result = trigger_agent_run(request, TriggerRunIn(agent_id=str(agent.id), context={}))

        self.assertEqual(result["status"], AgentRun.Status.PENDING)


class HandoffExpiryTest(TestCase):

    def setUp(self):
        self.agent = _make_agent()
        self.run = AgentRun.objects.create(
            agent=self.agent, goal="test", context={}, data_gathered={},
            triggered_by_id=uuid.uuid4(), company_id=COMPANY_A,
            status=AgentRun.Status.AWAITING_HUMAN,
        )

    def test_explicit_expires_at_takes_precedence_over_default_window(self):
        """A handoff created 1 hour ago with expires_at in the past should expire,
        even though it's well inside the 7-day default window."""
        handoff = AgentHandoffRequest.objects.create(
            run=self.run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REQUIRES_APPROVAL,
            trigger_detail="test",
            company_id=COMPANY_A,
            status=AgentHandoffRequest.HandoffStatus.PENDING,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        from core.ai_agent.tasks import expire_stale_handoffs
        expire_stale_handoffs()

        handoff.refresh_from_db()
        self.assertEqual(handoff.status, AgentHandoffRequest.HandoffStatus.EXPIRED)

    def test_suspending_handoff_expiry_fails_the_run(self):
        handoff = AgentHandoffRequest.objects.create(
            run=self.run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REQUIRES_APPROVAL,
            trigger_detail="test",
            company_id=COMPANY_A,
            status=AgentHandoffRequest.HandoffStatus.PENDING,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        from core.ai_agent.tasks import expire_stale_handoffs
        expire_stale_handoffs()

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, AgentRun.Status.FAILED)
        self.assertIn("expired", self.run.failure_reason.lower())

    def test_review_queue_handoff_expiry_does_not_touch_run(self):
        """REVIEW_QUEUE handoffs never suspend the run, so expiry shouldn't fail it."""
        self.run.status = AgentRun.Status.COMPLETED
        self.run.save(update_fields=["status"])

        handoff = AgentHandoffRequest.objects.create(
            run=self.run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REVIEW_QUEUE,
            trigger_detail="test",
            company_id=COMPANY_A,
            status=AgentHandoffRequest.HandoffStatus.PENDING,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        from core.ai_agent.tasks import expire_stale_handoffs
        expire_stale_handoffs()

        handoff.refresh_from_db()
        self.assertEqual(handoff.status, AgentHandoffRequest.HandoffStatus.EXPIRED)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, AgentRun.Status.COMPLETED)

    def test_no_expires_at_falls_back_to_seven_day_default(self):
        recent = AgentHandoffRequest.objects.create(
            run=self.run,
            trigger_reason=AgentHandoffRequest.TriggerReason.REQUIRES_APPROVAL,
            trigger_detail="recent, no expires_at set",
            company_id=COMPANY_A,
            status=AgentHandoffRequest.HandoffStatus.PENDING,
        )

        from core.ai_agent.tasks import expire_stale_handoffs
        expire_stale_handoffs()

        recent.refresh_from_db()
        self.assertEqual(recent.status, AgentHandoffRequest.HandoffStatus.PENDING)

        AgentHandoffRequest.objects.filter(pk=recent.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        expire_stale_handoffs()

        recent.refresh_from_db()
        self.assertEqual(recent.status, AgentHandoffRequest.HandoffStatus.EXPIRED)
