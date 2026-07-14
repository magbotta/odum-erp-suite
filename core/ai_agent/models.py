"""Data models for the Agentic AI & Human Handoff layer (ADR-0001)."""
from __future__ import annotations

import uuid

from django.db import models


class AutonomyTier(models.TextChoices):
    SUGGEST_ONLY = "suggest_only", "Suggest Only (human always acts)"
    AUTO_REVERSIBLE = "auto_execute_reversible", "Auto-Execute Reversible"
    AUTO_WITH_REVIEW = "auto_execute_with_review", "Auto-Execute with Review"
    FULLY_AUTONOMOUS = "fully_autonomous", "Fully Autonomous"


class AgentDefinition(models.Model):
    """
    Declarative configuration for one agent type.

    allowed_actions example:
      [{"entity": "SalesInvoice", "actions": ["read", "write_note"]},
       {"entity": "Lead", "actions": ["read", "write"]}]

    autonomy_config example:
      {"SalesInvoice:read": "auto_execute_reversible",
       "SalesInvoice:write_note": "auto_execute_with_review",
       "Lead:write": "auto_execute_reversible"}

    handoff_triggers example:
      {"dollar_threshold": 1000, "vip_accounts": true,
       "regulated_actions": ["write_off", "aml_flag"]}

    step_script example (structured mode):
      [{"type": "query", "entity": "SalesInvoice", "action": "read",
        "filter": {"status": "overdue", "days_past_due__gte": 30}},
       {"type": "llm_draft", "template": "dunning_email"},
       {"type": "write", "entity": "SalesInvoice", "action": "write_note"}]
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    goal_template = models.TextField(
        help_text="Goal with {variable} placeholders resolved at run time"
    )
    allowed_actions = models.JSONField(
        default=list,
        help_text="List of {entity, actions[]} objects the agent may touch",
    )
    allowed_mcp_tools = models.JSONField(
        default=list,
        help_text="List of {server_url, tool_name, description} MCP tools",
    )
    autonomy_config = models.JSONField(
        default=dict,
        help_text="Map of 'Entity:action' -> AutonomyTier",
    )
    confidence_threshold = models.FloatField(
        default=0.80,
        help_text="Agent pauses for human review if confidence drops below this",
    )
    handoff_triggers = models.JSONField(
        default=dict,
        help_text="Policy boundaries that force handoff regardless of confidence",
    )
    max_steps = models.IntegerField(
        default=30,
        help_text="Hard ceiling on steps per run; handoff if exceeded",
    )
    rate_limit_per_hour = models.IntegerField(
        default=10,
        help_text="Max runs per hour per company",
    )
    planning_mode = models.CharField(
        max_length=20,
        choices=[("structured", "Structured script"), ("llm", "LLM-driven planning")],
        default="structured",
    )
    step_script = models.JSONField(
        null=True, blank=True,
        help_text="Structured step list used when planning_mode=structured",
    )
    configured_by_id = models.UUIDField(
        help_text="OdumUser UUID who created/owns this agent definition",
    )
    service_account_id = models.UUIDField(
        null=True, blank=True,
        help_text="OdumUser UUID acting as the agent's RBAC identity for all writes",
    )
    company_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Null = platform-wide; set to scope to one company",
    )
    is_active = models.BooleanField(default=True)
    is_paused = models.BooleanField(
        default=False,
        help_text="Kill switch: pauses all new + in-flight runs for this agent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "odum_ai_agent"
        db_table = "odum_agent_definitions"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def is_action_allowed(self, entity: str, action: str) -> bool:
        for entry in (self.allowed_actions or []):
            if entry.get("entity") == entity and action in entry.get("actions", []):
                return True
        return False

    def get_autonomy_tier(self, entity: str, action: str) -> str:
        key = "{0}:{1}".format(entity, action)
        return (self.autonomy_config or {}).get(key, AutonomyTier.SUGGEST_ONLY)


class AgentRun(models.Model):
    """One execution instance of an AgentDefinition."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        AWAITING_HUMAN = "awaiting_human", "Awaiting Human"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        KILLED = "killed", "Killed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        AgentDefinition,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    goal = models.TextField(help_text="Resolved goal for this run")
    context = models.JSONField(
        default=dict,
        help_text="Input context supplied at trigger time; also accumulates rejections",
    )
    data_gathered = models.JSONField(
        default=dict,
        help_text="Facts/records accumulated during the run",
    )
    triggered_by_id = models.UUIDField(
        help_text="OdumUser UUID who triggered this run",
    )
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    kill_requested = models.BooleanField(
        default=False,
        help_text="Set to True to signal the running task to stop at next iteration",
    )
    step_count = models.IntegerField(default=0)
    current_script_index = models.IntegerField(
        default=0,
        help_text="Tracks position in step_script for structured mode",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "odum_ai_agent"
        db_table = "odum_agent_runs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent", "status"]),
            models.Index(fields=["company_id", "status"]),
        ]

    def __str__(self) -> str:
        return "Run {0} ({1}) — {2}".format(str(self.id)[:8], self.agent.slug, self.status)

    def is_terminal(self) -> bool:
        return self.status in (self.Status.COMPLETED, self.Status.FAILED, self.Status.KILLED)

    @property
    def pending_handoff(self):
        return self.handoffs.filter(status="pending").first()


class AgentStep(models.Model):
    """One atomic action within an AgentRun."""

    class StepType(models.TextChoices):
        QUERY = "query", "Query (read data)"
        WRITE = "write", "Write (mutate data)"
        MCP_TOOL = "mcp_tool", "External MCP Tool"
        LLM_CALL = "llm_call", "LLM Call (draft / score / plan)"
        POLICY_CHECK = "policy_check", "Policy Check"
        HANDOFF_TRIGGER = "handoff_trigger", "Handoff Trigger"

    class StepStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        EXECUTED = "executed", "Executed"
        SKIPPED = "skipped", "Skipped"
        HANDED_OFF = "handed_off", "Handed Off"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    step_number = models.IntegerField()
    step_type = models.CharField(max_length=20, choices=StepType.choices)
    description = models.TextField()
    entity = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=50, blank=True)
    payload = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    autonomy_tier = models.CharField(
        max_length=40, choices=AutonomyTier.choices, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=StepStatus.choices, default=StepStatus.PENDING
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        app_label = "odum_ai_agent"
        db_table = "odum_agent_steps"
        ordering = ["run", "step_number"]

    def __str__(self) -> str:
        return "Step {0} [{1}] in {2}".format(self.step_number, self.step_type, self.run_id)


class AgentHandoffRequest(models.Model):
    """
    The human-review inbox entry.  Created whenever the agent pauses for human input.
    For AUTO_WITH_REVIEW steps this is a post-hoc review; for SUGGEST_ONLY and
    policy-boundary triggers the run is suspended until resolution.
    """

    class TriggerReason(models.TextChoices):
        LOW_CONFIDENCE = "low_confidence", "Low Confidence"
        POLICY_BOUNDARY = "policy_boundary", "Policy Boundary Exceeded"
        MISSING_DATA = "missing_data", "Missing or Conflicting Data"
        EXECUTION_ERROR = "execution_error", "Execution Error"
        STOP_CONDITION = "stop_condition", "Stop Condition Reached"
        REQUIRES_APPROVAL = "requires_approval", "Action Requires Approval (suggest_only tier)"
        MAX_STEPS = "max_steps", "Maximum Step Count Reached"
        KILL_REQUESTED = "kill_requested", "Operator Kill Switch Activated"
        REVIEW_QUEUE = "review_queue", "Post-hoc Review (auto_execute_with_review)"

    class HandoffStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved As Proposed"
        EDITED_APPROVED = "edited_approved", "Approved With Edits"
        REJECTED = "rejected", "Rejected"
        TAKEN_OVER = "taken_over", "Human Took Over"
        EXPIRED = "expired", "Expired"
        ACKNOWLEDGED = "acknowledged", "Acknowledged (review queue)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="handoffs")
    step = models.OneToOneField(
        AgentStep,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="handoff",
    )
    trigger_reason = models.CharField(
        max_length=30, choices=TriggerReason.choices, db_index=True
    )
    trigger_detail = models.TextField()
    proposed_action = models.JSONField(
        null=True, blank=True,
        help_text="The action the agent proposed to take next",
    )
    proposed_reasoning = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    data_gathered = models.JSONField(
        default=dict,
        help_text="Snapshot of run.data_gathered at handoff time",
    )
    record_links = models.JSONField(
        default=list,
        help_text="[{entity, id, label, api_url}] links to underlying records",
    )
    assigned_to_id = models.UUIDField(
        null=True, blank=True,
        help_text="If set, only this user should resolve; else any user with the right role",
    )
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=HandoffStatus.choices,
        default=HandoffStatus.PENDING,
        db_index=True,
    )
    resolved_by_id = models.UUIDField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    edited_payload = models.JSONField(
        null=True, blank=True,
        help_text="Human's edited version of proposed_action",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "odum_ai_agent"
        db_table = "odum_agent_handoffs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_id", "status"]),
            models.Index(fields=["run", "status"]),
        ]

    def __str__(self) -> str:
        return "Handoff {0} [{1}] — {2}".format(
            str(self.id)[:8], self.trigger_reason, self.status
        )

    @property
    def is_suspending(self) -> bool:
        """True if this handoff blocks the run until resolved."""
        return self.trigger_reason not in (
            self.TriggerReason.REVIEW_QUEUE,
        )
