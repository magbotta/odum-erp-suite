"""
Tests for the Expense Policy Review Agent (core/ai_agent/agents/expense_policy_review.py).

Covers:
  - get_seed_data() produces a well-formed AgentDefinition payload
  - PermissionGuard allows exactly the two actions this agent needs (read, write_note)
    and nothing else
  - A full structured-mode run completes end-to-end (query -> llm_call -> write -> policy_check)
  - seed_agents management command registers all three example agents, including this one
"""
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.ai_agent.agents.expense_policy_review import (
    EXPENSE_POLICY_AGENT_SLUG,
    get_seed_data,
)
from core.ai_agent.model_gateway import NullGateway
from core.ai_agent.models import AgentDefinition, AgentRun, AgentStep
from core.ai_agent.permission_guard import PermissionGuard, PolicyViolation

COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_expense_agent():
    data = get_seed_data(configured_by_id=uuid.uuid4(), company_id=COMPANY_ID)
    slug = data.pop("slug")
    AgentDefinition.objects.filter(slug=slug).delete()
    return AgentDefinition.objects.create(slug=slug, **data)


class SeedDataShapeTest(TestCase):

    def test_seed_data_has_expected_slug_and_structured_mode(self):
        data = get_seed_data(configured_by_id=uuid.uuid4())
        self.assertEqual(data["slug"], EXPENSE_POLICY_AGENT_SLUG)
        self.assertEqual(data["planning_mode"], "structured")
        self.assertTrue(data["step_script"])

    def test_allowed_actions_scoped_to_expense_claim_only(self):
        data = get_seed_data(configured_by_id=uuid.uuid4())
        entities = {a["entity"] for a in data["allowed_actions"]}
        self.assertEqual(entities, {"ExpenseClaim"})


class ExpensePolicyPermissionGuardTest(TestCase):

    def setUp(self):
        self.agent = _make_expense_agent()

    def test_read_is_allowed(self):
        guard = PermissionGuard(self.agent)
        tier = guard.validate_action("ExpenseClaim", "read")
        self.assertEqual(tier, "auto_execute_reversible")

    def test_write_note_is_allowed(self):
        guard = PermissionGuard(self.agent)
        tier = guard.validate_action("ExpenseClaim", "write_note")
        self.assertEqual(tier, "auto_execute_with_review")

    def test_status_change_actions_are_not_allowed(self):
        """This agent is read + write_note only — it must never approve/reject claims itself."""
        guard = PermissionGuard(self.agent)
        with self.assertRaises(PolicyViolation):
            guard.validate_action("ExpenseClaim", "update_status")

    def test_other_entities_are_not_allowed(self):
        guard = PermissionGuard(self.agent)
        with self.assertRaises(PolicyViolation):
            guard.validate_action("SalesInvoice", "read")


class ExpensePolicyFullRunTest(TestCase):

    def setUp(self):
        self.agent = _make_expense_agent()

    def test_run_completes_through_all_four_steps(self):
        run = AgentRun.objects.create(
            agent=self.agent,
            goal="Review flagged expense claims",
            context={},
            data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        from core.ai_agent.executor import AgentRunExecutor
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}), \
             patch.object(executor, "_execute_write", return_value={"written": True}), \
             patch.object(executor, "gateway") as mock_gw:

            mock_gw.draft_text.return_value = "2 claims flagged: missing receipt, over per-claim limit."
            executor.execute()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRun.Status.COMPLETED)
        self.assertFalse(run.failure_reason)

        steps = list(AgentStep.objects.filter(run=run).order_by("step_number"))
        self.assertEqual(len(steps), 4)
        self.assertEqual(steps[0].step_type, AgentStep.StepType.QUERY)
        self.assertEqual(steps[1].step_type, AgentStep.StepType.LLM_CALL)
        self.assertEqual(steps[2].step_type, AgentStep.StepType.WRITE)
        self.assertEqual(steps[2].autonomy_tier, "auto_execute_with_review")
        self.assertEqual(steps[3].step_type, AgentStep.StepType.POLICY_CHECK)

    def test_write_step_produces_review_queue_entry(self):
        """write_note is auto_execute_with_review, so it must post a review-queue handoff
        without suspending the run."""
        run = AgentRun.objects.create(
            agent=self.agent,
            goal="Review flagged expense claims",
            context={},
            data_gathered={},
            triggered_by_id=uuid.uuid4(),
            company_id=COMPANY_ID,
        )

        from core.ai_agent.executor import AgentRunExecutor
        from core.ai_agent.models import AgentHandoffRequest
        executor = AgentRunExecutor(run_id=str(run.id), gateway=NullGateway())

        with patch.object(executor, "_execute_query", return_value={"records": [], "count": 0}), \
             patch.object(executor, "_execute_write", return_value={"written": True}), \
             patch.object(executor, "gateway") as mock_gw:

            mock_gw.draft_text.return_value = "Summary text"
            executor.execute()

        review_entry = AgentHandoffRequest.objects.filter(
            run=run, trigger_reason=AgentHandoffRequest.TriggerReason.REVIEW_QUEUE,
        ).first()
        self.assertIsNotNone(review_entry)
        run.refresh_from_db()
        # Run kept going past the review-queue entry and completed
        self.assertEqual(run.status, AgentRun.Status.COMPLETED)


class SeedAgentsCommandTest(TestCase):

    def test_seed_agents_registers_all_three_agents(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(
            email="admin@odum-erp.io", password="pw", is_superuser=True, is_staff=True,
        )

        call_command("seed_agents")

        slugs = set(AgentDefinition.objects.values_list("slug", flat=True))
        self.assertIn("collections_dunning", slugs)
        self.assertIn("lead_qualification", slugs)
        self.assertIn(EXPENSE_POLICY_AGENT_SLUG, slugs)

    def test_seed_agents_is_idempotent(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(
            email="admin@odum-erp.io", password="pw", is_superuser=True, is_staff=True,
        )

        call_command("seed_agents")
        call_command("seed_agents")

        self.assertEqual(
            AgentDefinition.objects.filter(slug=EXPENSE_POLICY_AGENT_SLUG).count(), 1
        )
