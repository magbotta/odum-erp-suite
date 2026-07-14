"""
AgentRunExecutor — the core execution engine.

Follows ADR-0001's execution loop:
  plan → validate → check tier → execute → audit log → check triggers → repeat

Designed to be instantiated inside a Celery task, with the ModelGateway injected
so tests can substitute a NullGateway or MockGateway without touching settings.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .mcp_client import MCPClient, MCPToolError
from .model_gateway import ModelGateway, get_model_gateway
from .models import AgentDefinition, AgentHandoffRequest, AgentRun, AgentStep, AutonomyTier
from .permission_guard import PermissionGuard, PolicyViolation

logger = logging.getLogger(__name__)


class AgentRunExecutor:
    """
    Executes one AgentRun.

    Usage (inside Celery task):
        executor = AgentRunExecutor(run_id, gateway=get_model_gateway())
        executor.execute()
    """

    def __init__(self, run_id: str, gateway: Optional[ModelGateway] = None):
        self.run_id = run_id
        self._gateway = gateway  # injected; resolved lazily if None

    @property
    def gateway(self) -> ModelGateway:
        if self._gateway is None:
            self._gateway = get_model_gateway()
        return self._gateway

    @gateway.setter
    def gateway(self, value: ModelGateway) -> None:
        self._gateway = value

    @gateway.deleter
    def gateway(self) -> None:
        self._gateway = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """Main entry point. Idempotent on terminal runs."""
        try:
            run = AgentRun.objects.select_related("agent").get(id=self.run_id)
        except AgentRun.DoesNotExist:
            logger.error("AgentRunExecutor: run %s not found", self.run_id)
            return

        if run.is_terminal():
            logger.info("AgentRunExecutor: run %s already terminal (%s)", self.run_id, run.status)
            return

        agent = run.agent

        # Mark as running
        AgentRun.objects.filter(pk=run.pk).update(
            status=AgentRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        run.status = AgentRun.Status.RUNNING

        guard = PermissionGuard(agent)
        mcp = MCPClient(agent.allowed_mcp_tools or [])

        try:
            self._run_loop(run, agent, guard, mcp)
        except Exception as exc:
            logger.exception("AgentRunExecutor: unhandled error in run %s", self.run_id)
            AgentRun.objects.filter(pk=run.pk).update(
                status=AgentRun.Status.FAILED,
                completed_at=timezone.now(),
                failure_reason=str(exc),
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self, run: AgentRun, agent: AgentDefinition, guard: PermissionGuard, mcp: MCPClient) -> None:
        from .handoff import create_handoff  # local import avoids circular: tasks→executor→handoff→tasks
        for _iteration in range(agent.max_steps + 1):
            # Reload from DB to pick up kill_requested / is_paused signals
            run.refresh_from_db()
            agent.refresh_from_db()

            if run.kill_requested or agent.is_paused:
                reason = (
                    AgentHandoffRequest.TriggerReason.KILL_REQUESTED
                    if run.kill_requested else AgentHandoffRequest.TriggerReason.KILL_REQUESTED
                )
                detail = "Agent paused by operator kill switch" if agent.is_paused else "Run killed by operator request"
                step = self._create_step(run, AgentStep.StepType.HANDOFF_TRIGGER, detail)
                create_handoff(run, step, reason, detail)
                AgentRun.objects.filter(pk=run.pk).update(
                    status=AgentRun.Status.KILLED,
                    completed_at=timezone.now(),
                )
                return

            if run.step_count >= agent.max_steps:
                step = self._create_step(run, AgentStep.StepType.HANDOFF_TRIGGER, "Max steps reached")
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.MAX_STEPS,
                    "Agent reached maximum step count ({0}).".format(agent.max_steps),
                )
                return

            # Plan next step
            planned = self._plan_next_step(run, agent)
            if planned is None:
                # Structured mode: no more steps in script
                AgentRun.objects.filter(pk=run.pk).update(
                    status=AgentRun.Status.COMPLETED,
                    completed_at=timezone.now(),
                )
                logger.info("AgentRunExecutor: run %s completed (script exhausted)", self.run_id)
                return

            is_complete = planned.get("is_complete", False)
            if is_complete:
                AgentRun.objects.filter(pk=run.pk).update(
                    status=AgentRun.Status.COMPLETED,
                    completed_at=timezone.now(),
                )
                logger.info("AgentRunExecutor: run %s completed", self.run_id)
                return

            step_spec = planned.get("step") or {}
            reasoning = planned.get("reasoning", "")
            confidence = float(planned.get("confidence", 1.0))

            step_type = self._resolve_step_type(step_spec.get("type", "query"))
            entity = step_spec.get("entity", "")
            action = step_spec.get("action", "")
            description = step_spec.get("description", "{0} on {1}".format(action, entity))

            # Create the step record
            step = self._create_step(run, step_type, description, entity=entity, action=action)
            step.payload = step_spec.get("payload") or step_spec.get("filter") or {}
            step.confidence = confidence
            step.save(update_fields=["payload", "confidence"])

            # Low-confidence check BEFORE executing
            if step_type not in (AgentStep.StepType.QUERY, AgentStep.StepType.POLICY_CHECK):
                if confidence < agent.confidence_threshold:
                    create_handoff(
                        run, step,
                        AgentHandoffRequest.TriggerReason.LOW_CONFIDENCE,
                        "Confidence {0:.0%} is below threshold {1:.0%}. Proposed: {2}".format(
                            confidence, agent.confidence_threshold, description
                        ),
                        proposed_action=step_spec,
                        proposed_reasoning=reasoning,
                        confidence=confidence,
                    )
                    return

            # Validate action (allow-list + RBAC + high-risk floor)
            if step_type in (AgentStep.StepType.QUERY, AgentStep.StepType.WRITE):
                try:
                    tier = guard.validate_action(entity, action, run.company_id)
                except PolicyViolation as exc:
                    step.status = AgentStep.StepStatus.FAILED
                    step.error_message = str(exc)
                    step.save(update_fields=["status", "error_message"])
                    create_handoff(
                        run, step,
                        AgentHandoffRequest.TriggerReason.EXECUTION_ERROR,
                        "Policy violation: {0}".format(exc),
                        proposed_action=step_spec,
                    )
                    return
            elif step_type == AgentStep.StepType.MCP_TOOL:
                server_url = step_spec.get("server_url", "")
                tool_name = step_spec.get("tool_name", "")
                try:
                    guard.validate_mcp_tool(server_url, tool_name)
                except PolicyViolation as exc:
                    step.status = AgentStep.StepStatus.FAILED
                    step.error_message = str(exc)
                    step.save(update_fields=["status", "error_message"])
                    create_handoff(run, step, AgentHandoffRequest.TriggerReason.EXECUTION_ERROR, str(exc))
                    return
                tier = AutonomyTier.AUTO_WITH_REVIEW
            else:
                tier = AutonomyTier.AUTO_REVERSIBLE  # LLM calls, policy checks

            step.autonomy_tier = tier
            step.save(update_fields=["autonomy_tier"])

            # Regulated-action check: fires before tier dispatch so it takes
            # precedence even when the high-risk floor has elevated the tier.
            regulated = (agent.handoff_triggers or {}).get("regulated_actions", [])
            if action in regulated:
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
                    "Action '{0}' is a regulated action requiring human approval".format(action),
                    proposed_action=step_spec,
                    proposed_reasoning=reasoning,
                    confidence=confidence,
                )
                return

            # SUGGEST_ONLY — hand off without executing
            if tier == AutonomyTier.SUGGEST_ONLY:
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.REQUIRES_APPROVAL,
                    "Action '{0}' on {1} requires human approval (suggest_only tier).".format(action, entity),
                    proposed_action=step_spec,
                    proposed_reasoning=reasoning,
                    confidence=confidence,
                )
                return

            # Execute the step
            result, error = self._execute_step(step, run, agent, mcp, step_spec)
            step.result = result
            step.status = AgentStep.StepStatus.EXECUTED if not error else AgentStep.StepStatus.FAILED
            step.executed_at = timezone.now()
            step.error_message = error or ""
            step.save(update_fields=["result", "status", "executed_at", "error_message"])

            # Write audit log entry for write operations
            if step_type == AgentStep.StepType.WRITE and not error:
                self._emit_audit_log(run, agent, step)

            if error:
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.EXECUTION_ERROR,
                    "Step failed: {0}".format(error),
                    proposed_action=step_spec,
                )
                return

            # Advance script index for structured mode
            AgentRun.objects.filter(pk=run.pk).update(
                step_count=run.step_count + 1,
                current_script_index=run.current_script_index + 1,
                data_gathered=run.data_gathered,
            )
            run.step_count += 1
            run.current_script_index += 1

            # AUTO_WITH_REVIEW — create review queue entry but keep running
            if tier == AutonomyTier.AUTO_WITH_REVIEW:
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.REVIEW_QUEUE,
                    "Post-hoc review: agent executed '{0}' on {1}".format(action, entity),
                    proposed_action=step_spec,
                    proposed_reasoning=reasoning,
                    confidence=confidence,
                    is_review_queue=True,
                )

            # Policy-boundary trigger check after executing
            if self._check_policy_triggers(run, agent, step, step_spec, reasoning, confidence):
                return

        # Exhausted max_steps iterations (shouldn't reach here due to step_count check above)
        step = self._create_step(run, AgentStep.StepType.HANDOFF_TRIGGER, "Max iterations exhausted")
        create_handoff(run, step, AgentHandoffRequest.TriggerReason.MAX_STEPS, "Max iterations exhausted")

    # ------------------------------------------------------------------
    # Step planning
    # ------------------------------------------------------------------

    def _plan_next_step(self, run: AgentRun, agent: AgentDefinition) -> Optional[Dict[str, Any]]:
        """Return the next step spec, or None if no more steps."""
        if agent.planning_mode == "structured":
            return self._plan_structured(run, agent)
        return self._plan_llm(run, agent)

    def _plan_structured(self, run: AgentRun, agent: AgentDefinition) -> Optional[Dict[str, Any]]:
        script = agent.step_script or []
        idx = run.current_script_index
        if idx >= len(script):
            return {"is_complete": True}
        step_spec = script[idx]
        return {
            "step": step_spec,
            "reasoning": "Structured step {0}/{1}".format(idx + 1, len(script)),
            "confidence": step_spec.get("confidence", 1.0),
            "is_complete": False,
        }

    def _plan_llm(self, run: AgentRun, agent: AgentDefinition) -> Optional[Dict[str, Any]]:
        history = list(
            run.steps.values("step_type", "description", "status").order_by("step_number")
        )
        result = self.gateway.plan_next_step(
            goal=run.goal,
            history=history,
            data_gathered=run.data_gathered,
            allowed_actions=agent.allowed_actions,
        )
        if not result:
            return {"is_complete": True}
        return result

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        step: AgentStep,
        run: AgentRun,
        agent: AgentDefinition,
        mcp: MCPClient,
        step_spec: Dict[str, Any],
    ):
        """
        Execute step_spec and return (result_dict, error_string|None).
        Never raises — callers expect (result, error) tuple.
        """
        step_type = step.step_type
        try:
            if step_type == AgentStep.StepType.QUERY:
                result = self._execute_query(step.entity, step_spec, run)
                # Merge useful data into run.data_gathered
                self._merge_data_gathered(run, step.entity, result)
                return result, None

            elif step_type == AgentStep.StepType.WRITE:
                result = self._execute_write(step.entity, step.action, step_spec, run, agent)
                return result, None

            elif step_type == AgentStep.StepType.LLM_CALL:
                template = step_spec.get("template", "generic_draft")
                context = {**run.data_gathered, **step_spec.get("context", {})}
                text = self.gateway.draft_text(template, context)
                result = {"draft": text, "template": template}
                self._merge_data_gathered(run, "llm_draft_{0}".format(template), result)
                return result, None

            elif step_type == AgentStep.StepType.MCP_TOOL:
                server_url = step_spec.get("server_url", "")
                tool_name = step_spec.get("tool_name", "")
                arguments = step_spec.get("arguments", {})
                result = mcp.call(server_url, tool_name, arguments)
                if result.get("error"):
                    return result, result["error"]
                self._merge_data_gathered(run, "mcp_{0}".format(tool_name), result)
                return result, None

            elif step_type == AgentStep.StepType.POLICY_CHECK:
                result = self._execute_policy_check(step_spec, run, agent)
                return result, None

            else:
                return {}, "Unknown step type: {0}".format(step_type)

        except MCPToolError as exc:
            return {}, str(exc)
        except Exception as exc:
            logger.exception("AgentRunExecutor: step execution error in run %s", run.id)
            return {}, str(exc)

    def _execute_query(self, entity: str, step_spec: Dict[str, Any], run: AgentRun) -> Dict[str, Any]:
        """
        Execute a read query against an entity using the metadata engine.
        Falls back to empty result if entity model can't be found.
        """
        from django.apps import apps

        filters = step_spec.get("filter", {})
        # Add company scoping
        if run.company_id:
            filters.setdefault("company_id", str(run.company_id))
        filters["is_deleted"] = filters.get("is_deleted", False)

        model = _find_model(entity)
        if model is None:
            return {"records": [], "count": 0, "note": "Entity model not found: {0}".format(entity)}

        qs = model.objects.filter(**filters)[:50]  # cap at 50 records per query
        records = []
        for obj in qs:
            record = {"id": str(obj.pk)}
            for field in obj._meta.get_fields():
                if hasattr(field, "attname"):
                    val = getattr(obj, field.attname, None)
                    if isinstance(val, uuid.UUID):
                        val = str(val)
                    record[field.name] = val
            records.append(record)

        return {"records": records, "count": len(records)}

    def _execute_write(
        self,
        entity: str,
        action: str,
        step_spec: Dict[str, Any],
        run: AgentRun,
        agent: AgentDefinition,
    ) -> Dict[str, Any]:
        """
        Execute a write operation.
        Currently supports: write_note (creates an activity/note on a record).
        Additional write actions should be added here as the platform grows.
        """
        payload = step_spec.get("payload", {})
        record_id = payload.get("record_id") or step_spec.get("record_id")

        if action == "write_note":
            return self._write_note(entity, record_id, payload, run, agent)

        if action == "update_score":
            return self._update_score(entity, record_id, payload, run, agent)

        if action == "update_status":
            return self._update_status(entity, record_id, payload, run, agent)

        return {"note": "Write action '{0}' registered (no-op in current implementation)".format(action)}

    def _write_note(self, entity: str, record_id, payload: dict, run: AgentRun, agent: AgentDefinition) -> Dict[str, Any]:
        """Write an activity note to an entity record."""
        note_text = payload.get("note") or payload.get("draft", "")
        if not note_text:
            return {"error": "No note text provided"}

        model = _find_model(entity)
        if model is None or not record_id:
            return {"note": note_text, "entity": entity, "record_id": str(record_id)}

        try:
            obj = model.objects.get(pk=record_id)
            # Store note in custom_fields if entity has it
            if hasattr(obj, "custom_fields"):
                notes = obj.custom_fields.get("agent_notes", [])
                notes.append({
                    "run_id": str(run.id),
                    "agent": agent.slug,
                    "note": note_text,
                    "at": timezone.now().isoformat(),
                })
                obj.custom_fields["agent_notes"] = notes
                obj.save(update_fields=["custom_fields", "updated_at"])
                return {"written": True, "record_id": str(record_id), "entity": entity}
        except Exception as exc:
            return {"error": str(exc), "entity": entity, "record_id": str(record_id)}

        return {"note": note_text, "entity": entity, "record_id": str(record_id)}

    def _update_score(self, entity: str, record_id, payload: dict, run: AgentRun, agent: AgentDefinition) -> Dict[str, Any]:
        score = payload.get("score", 0)
        model = _find_model(entity)
        if model and record_id:
            try:
                obj = model.objects.get(pk=record_id)
                if hasattr(obj, "lead_score"):
                    obj.lead_score = score
                    obj.save(update_fields=["lead_score", "updated_at"])
                elif hasattr(obj, "custom_fields"):
                    obj.custom_fields["ai_score"] = score
                    obj.custom_fields["ai_score_reasoning"] = payload.get("reasoning", "")
                    obj.save(update_fields=["custom_fields", "updated_at"])
                return {"scored": True, "record_id": str(record_id), "score": score}
            except Exception as exc:
                return {"error": str(exc)}
        return {"score": score, "record_id": str(record_id)}

    def _update_status(self, entity: str, record_id, payload: dict, run: AgentRun, agent: AgentDefinition) -> Dict[str, Any]:
        new_status = payload.get("status", "")
        model = _find_model(entity)
        if model and record_id and new_status:
            try:
                obj = model.objects.get(pk=record_id)
                if hasattr(obj, "status"):
                    obj.status = new_status
                    obj.save(update_fields=["status", "updated_at"])
                    return {"updated": True, "record_id": str(record_id), "status": new_status}
            except Exception as exc:
                return {"error": str(exc)}
        return {"status": new_status, "record_id": str(record_id)}

    def _execute_policy_check(self, step_spec: Dict[str, Any], run: AgentRun, agent: AgentDefinition) -> Dict[str, Any]:
        """Evaluate a policy condition and return {passed: bool, detail: str}."""
        check_type = step_spec.get("check_type", "")
        triggers = agent.handoff_triggers or {}

        if check_type == "dollar_threshold":
            threshold = triggers.get("dollar_threshold", float("inf"))
            amount = step_spec.get("amount", 0)
            passed = float(amount) <= float(threshold)
            return {"passed": passed, "amount": amount, "threshold": threshold}

        if check_type == "vip_account":
            entity_id = step_spec.get("entity_id")
            # Simplified: check custom_fields for vip flag
            passed = True
            if entity_id:
                model = _find_model(step_spec.get("entity", ""))
                if model:
                    try:
                        obj = model.objects.get(pk=entity_id)
                        vip = getattr(obj, "is_vip", False) or (
                            hasattr(obj, "custom_fields") and obj.custom_fields.get("vip", False)
                        )
                        passed = not vip
                        return {"passed": passed, "is_vip": vip}
                    except Exception:
                        pass
            return {"passed": passed}

        return {"passed": True, "note": "Unknown check type: {0}".format(check_type)}

    # ------------------------------------------------------------------
    # Handoff trigger evaluation
    # ------------------------------------------------------------------

    def _check_policy_triggers(
        self,
        run: AgentRun,
        agent: AgentDefinition,
        step: AgentStep,
        step_spec: Dict[str, Any],
        reasoning: str,
        confidence: float,
    ) -> bool:
        """
        Evaluate policy-boundary triggers.
        Returns True if a handoff was created (caller should return).
        """
        from .handoff import create_handoff
        triggers = agent.handoff_triggers or {}

        # Dollar threshold check
        dollar_threshold = triggers.get("dollar_threshold")
        if dollar_threshold is not None:
            amount = step_spec.get("payload", {}).get("amount", 0)
            if amount and float(amount) > float(dollar_threshold):
                create_handoff(
                    run, step,
                    AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
                    "Amount {0} exceeds policy threshold {1}".format(amount, dollar_threshold),
                    proposed_action=step_spec,
                    proposed_reasoning=reasoning,
                    confidence=confidence,
                )
                return True

        # Regulated action check
        regulated = triggers.get("regulated_actions", [])
        if step.action in regulated:
            create_handoff(
                run, step,
                AgentHandoffRequest.TriggerReason.POLICY_BOUNDARY,
                "Action '{0}' is a regulated action requiring human approval".format(step.action),
                proposed_action=step_spec,
                proposed_reasoning=reasoning,
                confidence=confidence,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_step(
        self,
        run: AgentRun,
        step_type: str,
        description: str,
        entity: str = "",
        action: str = "",
    ) -> AgentStep:
        step = AgentStep.objects.create(
            run=run,
            step_number=run.step_count + 1,
            step_type=step_type,
            description=description,
            entity=entity,
            action=action,
            status=AgentStep.StepStatus.PENDING,
        )
        return step

    def _merge_data_gathered(self, run: AgentRun, key: str, value: Any) -> None:
        run.data_gathered[key] = value
        AgentRun.objects.filter(pk=run.pk).update(data_gathered=run.data_gathered)

    def _emit_audit_log(self, run: AgentRun, agent: AgentDefinition, step: AgentStep) -> None:
        from core.audit.models import AuditLog
        AuditLog.objects.create(
            entity=step.entity,
            entity_id=step.payload.get("record_id", "") if step.payload else "",
            action=step.action,
            user=None,
            company_id=run.company_id,
            origin=AuditLog.Origin.AI,
            after=step.result,
            diff={},
            agent_run_id=run.id,
            agent_slug=agent.slug,
        )

    @staticmethod
    def _resolve_step_type(type_str: str) -> str:
        mapping = {
            "query": AgentStep.StepType.QUERY,
            "write": AgentStep.StepType.WRITE,
            "mcp_tool": AgentStep.StepType.MCP_TOOL,
            "llm_call": AgentStep.StepType.LLM_CALL,
            "llm_draft": AgentStep.StepType.LLM_CALL,
            "policy_check": AgentStep.StepType.POLICY_CHECK,
            "handoff_trigger": AgentStep.StepType.HANDOFF_TRIGGER,
        }
        return mapping.get(type_str, AgentStep.StepType.QUERY)


def _find_model(entity_name: str):
    """Return the Django model class for an entity name, or None."""
    from django.apps import apps
    for model in apps.get_models():
        if model.__name__ == entity_name:
            return model
    return None
