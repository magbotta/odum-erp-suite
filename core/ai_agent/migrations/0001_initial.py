from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AgentDefinition",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("slug", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=200)),
                ("goal_template", models.TextField(help_text="Goal with {variable} placeholders resolved at run time")),
                ("allowed_actions", models.JSONField(default=list, help_text="List of {entity, actions[]} objects the agent may touch")),
                ("allowed_mcp_tools", models.JSONField(default=list, help_text="List of {server_url, tool_name, description} MCP tools")),
                ("autonomy_config", models.JSONField(default=dict, help_text="Map of 'Entity:action' -> AutonomyTier")),
                ("confidence_threshold", models.FloatField(default=0.8, help_text="Agent pauses for human review if confidence drops below this")),
                ("handoff_triggers", models.JSONField(default=dict, help_text="Policy boundaries that force handoff regardless of confidence")),
                ("max_steps", models.IntegerField(default=30, help_text="Hard ceiling on steps per run; handoff if exceeded")),
                ("rate_limit_per_hour", models.IntegerField(default=10, help_text="Max runs per hour per company")),
                ("planning_mode", models.CharField(choices=[("structured", "Structured script"), ("llm", "LLM-driven planning")], default="structured", max_length=20)),
                ("step_script", models.JSONField(blank=True, help_text="Structured step list used when planning_mode=structured", null=True)),
                ("configured_by_id", models.UUIDField(help_text="OdumUser UUID who created/owns this agent definition")),
                ("service_account_id", models.UUIDField(blank=True, help_text="OdumUser UUID acting as the agent’s RBAC identity for all writes", null=True)),
                ("company_id", models.UUIDField(blank=True, db_index=True, help_text="Null = platform-wide; set to scope to one company", null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("is_paused", models.BooleanField(default=False, help_text="Kill switch: pauses all new + in-flight runs for this agent")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"app_label": "odum_ai_agent", "db_table": "odum_agent_definitions", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="AgentRun",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("awaiting_human", "Awaiting Human"), ("completed", "Completed"), ("failed", "Failed"), ("killed", "Killed")], db_index=True, default="pending", max_length=20)),
                ("goal", models.TextField(help_text="Resolved goal for this run")),
                ("context", models.JSONField(default=dict, help_text="Input context supplied at trigger time; also accumulates rejections")),
                ("data_gathered", models.JSONField(default=dict, help_text="Facts/records accumulated during the run")),
                ("triggered_by_id", models.UUIDField(help_text="OdumUser UUID who triggered this run")),
                ("company_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("kill_requested", models.BooleanField(default=False, help_text="Set to True to signal the running task to stop at next iteration")),
                ("step_count", models.IntegerField(default=0)),
                ("current_script_index", models.IntegerField(default=0, help_text="Tracks position in step_script for structured mode")),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="runs", to="odum_ai_agent.agentdefinition")),
            ],
            options={"app_label": "odum_ai_agent", "db_table": "odum_agent_runs", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="agentrun",
            index=models.Index(fields=["agent", "status"], name="odum_agent_runs_agent_status_idx"),
        ),
        migrations.AddIndex(
            model_name="agentrun",
            index=models.Index(fields=["company_id", "status"], name="odum_agent_runs_company_status_idx"),
        ),
        migrations.CreateModel(
            name="AgentStep",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("step_number", models.IntegerField()),
                ("step_type", models.CharField(choices=[("query", "Query (read data)"), ("write", "Write (mutate data)"), ("mcp_tool", "External MCP Tool"), ("llm_call", "LLM Call (draft / score / plan)"), ("policy_check", "Policy Check"), ("handoff_trigger", "Handoff Trigger")], max_length=20)),
                ("description", models.TextField()),
                ("entity", models.CharField(blank=True, max_length=100)),
                ("action", models.CharField(blank=True, max_length=50)),
                ("payload", models.JSONField(blank=True, null=True)),
                ("result", models.JSONField(blank=True, null=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("autonomy_tier", models.CharField(blank=True, choices=[("suggest_only", "Suggest Only (human always acts)"), ("auto_execute_reversible", "Auto-Execute Reversible"), ("auto_execute_with_review", "Auto-Execute with Review"), ("fully_autonomous", "Fully Autonomous")], max_length=40, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("executed", "Executed"), ("skipped", "Skipped"), ("handed_off", "Handed Off"), ("failed", "Failed")], default="pending", max_length=20)),
                ("executed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="odum_ai_agent.agentrun")),
            ],
            options={"app_label": "odum_ai_agent", "db_table": "odum_agent_steps", "ordering": ["run", "step_number"]},
        ),
        migrations.CreateModel(
            name="AgentHandoffRequest",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("trigger_reason", models.CharField(choices=[("low_confidence", "Low Confidence"), ("policy_boundary", "Policy Boundary Exceeded"), ("missing_data", "Missing or Conflicting Data"), ("execution_error", "Execution Error"), ("stop_condition", "Stop Condition Reached"), ("requires_approval", "Action Requires Approval (suggest_only tier)"), ("max_steps", "Maximum Step Count Reached"), ("kill_requested", "Operator Kill Switch Activated"), ("review_queue", "Post-hoc Review (auto_execute_with_review)")], db_index=True, max_length=30)),
                ("trigger_detail", models.TextField()),
                ("proposed_action", models.JSONField(blank=True, help_text="The action the agent proposed to take next", null=True)),
                ("proposed_reasoning", models.TextField(blank=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("data_gathered", models.JSONField(default=dict, help_text="Snapshot of run.data_gathered at handoff time")),
                ("record_links", models.JSONField(default=list, help_text="[{entity, id, label, api_url}] links to underlying records")),
                ("assigned_to_id", models.UUIDField(blank=True, help_text="If set, only this user should resolve; else any user with the right role", null=True)),
                ("company_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved As Proposed"), ("edited_approved", "Approved With Edits"), ("rejected", "Rejected"), ("taken_over", "Human Took Over"), ("expired", "Expired"), ("acknowledged", "Acknowledged (review queue)")], db_index=True, default="pending", max_length=20)),
                ("resolved_by_id", models.UUIDField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolution_notes", models.TextField(blank=True)),
                ("edited_payload", models.JSONField(blank=True, help_text="Human’s edited version of proposed_action", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="handoffs", to="odum_ai_agent.agentrun")),
                ("step", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="handoff", to="odum_ai_agent.agentstep")),
            ],
            options={"app_label": "odum_ai_agent", "db_table": "odum_agent_handoffs", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="agenthandoffrequest",
            index=models.Index(fields=["company_id", "status"], name="odum_handoffs_company_status_idx"),
        ),
        migrations.AddIndex(
            model_name="agenthandoffrequest",
            index=models.Index(fields=["run", "status"], name="odum_handoffs_run_status_idx"),
        ),
    ]
