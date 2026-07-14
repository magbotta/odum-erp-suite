"""
AI Agent REST API (ADR-0001).

NOTE: do NOT add `from __future__ import annotations` — Pydantic v2 compat
      requires runtime annotation evaluation in api.py files.

Endpoints:
  Agent definitions (CRUD + kill switch)
  Agent runs (trigger, status, kill)
  Handoff inbox (list, detail, resolve)
  Admin (platform-wide kill switch, status)
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from core.ai_agent.models import (
    AgentDefinition,
    AgentHandoffRequest,
    AgentRun,
    AgentStep,
)
from core.ai_agent.tasks import execute_agent_run, revoke_agent_run_task

router = Router(tags=["AI Agents"])


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

class ActionResponse(Schema):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# AgentDefinition schemas
# ---------------------------------------------------------------------------

class AgentDefinitionIn(Schema):
    slug: str
    name: str
    goal_template: str
    allowed_actions: List[Dict[str, Any]]
    allowed_mcp_tools: Optional[List[Dict[str, Any]]] = None
    autonomy_config: Optional[Dict[str, str]] = None
    confidence_threshold: Optional[float] = 0.80
    handoff_triggers: Optional[Dict[str, Any]] = None
    max_steps: Optional[int] = 30
    rate_limit_per_hour: Optional[int] = 10
    planning_mode: Optional[str] = "structured"
    step_script: Optional[List[Dict[str, Any]]] = None
    service_account_id: Optional[str] = None
    company_id: Optional[str] = None


class AgentDefinitionOut(Schema):
    id: str
    slug: str
    name: str
    goal_template: str
    allowed_actions: List[Dict[str, Any]]
    allowed_mcp_tools: List[Dict[str, Any]]
    autonomy_config: Dict[str, str]
    confidence_threshold: float
    handoff_triggers: Dict[str, Any]
    max_steps: int
    rate_limit_per_hour: int
    planning_mode: str
    step_script: Optional[List[Dict[str, Any]]]
    is_active: bool
    is_paused: bool
    company_id: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# AgentRun schemas
# ---------------------------------------------------------------------------

class TriggerRunIn(Schema):
    agent_id: str
    context: Optional[Dict[str, Any]] = None
    goal_override: Optional[str] = None


class AgentStepOut(Schema):
    id: str
    step_number: int
    step_type: str
    description: str
    entity: str
    action: str
    confidence: Optional[float]
    autonomy_tier: Optional[str]
    status: str
    executed_at: Optional[datetime]
    error_message: str


class AgentRunOut(Schema):
    id: str
    agent_id: str
    agent_name: str
    agent_slug: str
    status: str
    goal: str
    step_count: int
    data_gathered: Dict[str, Any]
    kill_requested: bool
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    failure_reason: str
    created_at: datetime
    steps: List[AgentStepOut]
    pending_handoff_id: Optional[str]


# ---------------------------------------------------------------------------
# Handoff schemas
# ---------------------------------------------------------------------------

class RecordLinkOut(Schema):
    entity: str
    id: str
    label: str
    api_url: str


class AgentHandoffOut(Schema):
    id: str
    run_id: str
    agent_name: str
    agent_slug: str
    trigger_reason: str
    trigger_detail: str
    proposed_action: Optional[Dict[str, Any]]
    proposed_reasoning: str
    confidence: Optional[float]
    data_gathered: Dict[str, Any]
    record_links: List[Dict[str, Any]]
    status: str
    resolved_by_id: Optional[str]
    resolved_at: Optional[datetime]
    resolution_notes: str
    created_at: datetime


class ApproveHandoffIn(Schema):
    notes: Optional[str] = ""


class EditApproveHandoffIn(Schema):
    edited_payload: Dict[str, Any]
    notes: Optional[str] = ""


class RejectHandoffIn(Schema):
    reason: str


class TakeOverHandoffIn(Schema):
    notes: Optional[str] = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _def_out(d):
    return {
        "id": str(d.id),
        "slug": d.slug,
        "name": d.name,
        "goal_template": d.goal_template,
        "allowed_actions": d.allowed_actions or [],
        "allowed_mcp_tools": d.allowed_mcp_tools or [],
        "autonomy_config": d.autonomy_config or {},
        "confidence_threshold": d.confidence_threshold,
        "handoff_triggers": d.handoff_triggers or {},
        "max_steps": d.max_steps,
        "rate_limit_per_hour": d.rate_limit_per_hour,
        "planning_mode": d.planning_mode,
        "step_script": d.step_script,
        "is_active": d.is_active,
        "is_paused": d.is_paused,
        "company_id": str(d.company_id) if d.company_id else None,
        "created_at": d.created_at,
    }


def _run_out(run):
    steps = [
        {
            "id": str(s.id),
            "step_number": s.step_number,
            "step_type": s.step_type,
            "description": s.description,
            "entity": s.entity,
            "action": s.action,
            "confidence": s.confidence,
            "autonomy_tier": s.autonomy_tier,
            "status": s.status,
            "executed_at": s.executed_at,
            "error_message": s.error_message,
        }
        for s in run.steps.order_by("step_number")
    ]
    pending = run.handoffs.filter(status="pending").first()
    return {
        "id": str(run.id),
        "agent_id": str(run.agent_id),
        "agent_name": run.agent.name,
        "agent_slug": run.agent.slug,
        "status": run.status,
        "goal": run.goal,
        "step_count": run.step_count,
        "data_gathered": run.data_gathered or {},
        "kill_requested": run.kill_requested,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "failure_reason": run.failure_reason,
        "created_at": run.created_at,
        "steps": steps,
        "pending_handoff_id": str(pending.id) if pending else None,
    }


def _handoff_out(h):
    return {
        "id": str(h.id),
        "run_id": str(h.run_id),
        "agent_name": h.run.agent.name,
        "agent_slug": h.run.agent.slug,
        "trigger_reason": h.trigger_reason,
        "trigger_detail": h.trigger_detail,
        "proposed_action": h.proposed_action,
        "proposed_reasoning": h.proposed_reasoning,
        "confidence": h.confidence,
        "data_gathered": h.data_gathered or {},
        "record_links": h.record_links or [],
        "status": h.status,
        "resolved_by_id": str(h.resolved_by_id) if h.resolved_by_id else None,
        "resolved_at": h.resolved_at,
        "resolution_notes": h.resolution_notes,
        "created_at": h.created_at,
    }


def _get_company_id(request):
    company_id = request.GET.get("company_id") or request.headers.get("X-Company-Id")
    if company_id:
        try:
            return uuid.UUID(company_id)
        except ValueError:
            pass
    return None


def _check_rate_limit(agent: AgentDefinition, company_id) -> None:
    """
    Raise HttpError(429) if this agent has already been triggered
    `rate_limit_per_hour` times in the trailing hour for this company.

    Platform-wide definitions (company_id=None) are rate-limited per
    triggering company_id too, so one company can't exhaust the quota
    of a shared agent for everyone else.
    """
    from ninja.errors import HttpError

    window_start = timezone.now() - timedelta(hours=1)
    recent_count = AgentRun.objects.filter(
        agent=agent, company_id=company_id, created_at__gte=window_start,
    ).count()
    if recent_count >= agent.rate_limit_per_hour:
        raise HttpError(
            429,
            "Agent '{0}' has reached its rate limit of {1} run(s) per hour.".format(
                agent.name, agent.rate_limit_per_hour
            ),
        )


# ---------------------------------------------------------------------------
# Agent Definition endpoints
# ---------------------------------------------------------------------------

@router.post("/definitions", response=AgentDefinitionOut)
def create_agent_definition(request, data: AgentDefinitionIn):
    d = AgentDefinition.objects.create(
        slug=data.slug,
        name=data.name,
        goal_template=data.goal_template,
        allowed_actions=data.allowed_actions,
        allowed_mcp_tools=data.allowed_mcp_tools or [],
        autonomy_config=data.autonomy_config or {},
        confidence_threshold=data.confidence_threshold or 0.80,
        handoff_triggers=data.handoff_triggers or {},
        max_steps=data.max_steps or 30,
        rate_limit_per_hour=data.rate_limit_per_hour or 10,
        planning_mode=data.planning_mode or "structured",
        step_script=data.step_script,
        configured_by_id=request.user.id,
        service_account_id=uuid.UUID(data.service_account_id) if data.service_account_id else None,
        company_id=uuid.UUID(data.company_id) if data.company_id else None,
    )
    return _def_out(d)


@router.get("/definitions", response=List[AgentDefinitionOut])
def list_agent_definitions(request, company_id: Optional[str] = None):
    qs = AgentDefinition.objects.filter(is_active=True)
    if company_id:
        try:
            cid = uuid.UUID(company_id)
            qs = qs.filter(company_id=cid)
        except ValueError:
            pass
    return [_def_out(d) for d in qs]


@router.get("/definitions/{agent_id}", response=AgentDefinitionOut)
def get_agent_definition(request, agent_id: str):
    d = get_object_or_404(AgentDefinition, id=agent_id)
    return _def_out(d)


@router.post("/definitions/{agent_id}/pause", response=ActionResponse)
def pause_agent(request, agent_id: str):
    """Kill switch — pauses all new and in-flight runs for this agent."""
    d = get_object_or_404(AgentDefinition, id=agent_id)
    d.is_paused = True
    d.save(update_fields=["is_paused", "updated_at"])
    # Signal in-flight runs to stop
    _kill_in_flight_runs(d)
    return {"ok": True, "message": "Agent '{0}' paused. In-flight runs signalled to stop.".format(d.name)}


@router.post("/definitions/{agent_id}/resume", response=ActionResponse)
def resume_agent(request, agent_id: str):
    d = get_object_or_404(AgentDefinition, id=agent_id)
    d.is_paused = False
    d.save(update_fields=["is_paused", "updated_at"])
    return {"ok": True, "message": "Agent '{0}' resumed.".format(d.name)}


@router.post("/definitions/{agent_id}/disable", response=ActionResponse)
def disable_agent(request, agent_id: str):
    d = get_object_or_404(AgentDefinition, id=agent_id)
    d.is_active = False
    d.is_paused = True
    d.save(update_fields=["is_active", "is_paused", "updated_at"])
    _kill_in_flight_runs(d)
    return {"ok": True, "message": "Agent '{0}' disabled permanently.".format(d.name)}


def _kill_in_flight_runs(agent):
    # revoke_agent_run_task imported at module level
    running = AgentRun.objects.filter(
        agent=agent,
        status__in=[AgentRun.Status.RUNNING, AgentRun.Status.PENDING],
    )
    for run in running:
        AgentRun.objects.filter(pk=run.pk).update(kill_requested=True)
        if run.celery_task_id:
            revoke_agent_run_task.delay(run.celery_task_id)


# ---------------------------------------------------------------------------
# Agent Run endpoints
# ---------------------------------------------------------------------------

@router.post("/runs", response=AgentRunOut)
def trigger_agent_run(request, data: TriggerRunIn):
    # execute_agent_run imported at module level

    agent = get_object_or_404(AgentDefinition, id=data.agent_id, is_active=True)

    if agent.is_paused:
        from ninja.errors import HttpError
        raise HttpError(409, "Agent '{0}' is currently paused.".format(agent.name))

    company_id = _get_company_id(request)
    _check_rate_limit(agent, company_id)
    context = data.context or {}
    goal = data.goal_override or agent.goal_template.format(**context)

    run = AgentRun.objects.create(
        agent=agent,
        status=AgentRun.Status.PENDING,
        goal=goal,
        context=context,
        data_gathered={},
        triggered_by_id=request.user.id,
        company_id=company_id,
    )

    task = execute_agent_run.delay(str(run.id))
    AgentRun.objects.filter(pk=run.pk).update(celery_task_id=task.id or "")
    run.refresh_from_db()
    return _run_out(run)


@router.get("/runs/{run_id}", response=AgentRunOut)
def get_agent_run(request, run_id: str):
    run = get_object_or_404(AgentRun.objects.select_related("agent").prefetch_related("steps", "handoffs"), id=run_id)
    return _run_out(run)


@router.get("/runs", response=List[AgentRunOut])
def list_agent_runs(request, agent_id: Optional[str] = None, status: Optional[str] = None):
    qs = AgentRun.objects.select_related("agent").prefetch_related("steps", "handoffs")
    if agent_id:
        qs = qs.filter(agent_id=agent_id)
    if status:
        qs = qs.filter(status=status)
    company_id = _get_company_id(request)
    if company_id:
        qs = qs.filter(company_id=company_id)
    return [_run_out(r) for r in qs[:50]]


@router.delete("/runs/{run_id}", response=ActionResponse)
def kill_agent_run(request, run_id: str):
    """Kill a specific in-flight run."""
    # revoke_agent_run_task imported at module level
    run = get_object_or_404(AgentRun, id=run_id)
    AgentRun.objects.filter(pk=run.pk).update(kill_requested=True)
    if run.celery_task_id:
        revoke_agent_run_task.delay(run.celery_task_id)
    return {"ok": True, "message": "Kill signal sent to run {0}.".format(run_id)}


# ---------------------------------------------------------------------------
# Handoff inbox endpoints
# ---------------------------------------------------------------------------

@router.get("/handoffs", response=List[AgentHandoffOut])
def list_handoffs(request, status: Optional[str] = None, agent_id: Optional[str] = None):
    qs = AgentHandoffRequest.objects.select_related("run__agent").order_by("-created_at")
    company_id = _get_company_id(request)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.filter(status=AgentHandoffRequest.HandoffStatus.PENDING)
    if agent_id:
        qs = qs.filter(run__agent_id=agent_id)
    return [_handoff_out(h) for h in qs[:100]]


@router.get("/handoffs/{handoff_id}", response=AgentHandoffOut)
def get_handoff(request, handoff_id: str):
    h = get_object_or_404(
        AgentHandoffRequest.objects.select_related("run__agent"),
        id=handoff_id,
    )
    return _handoff_out(h)


@router.post("/handoffs/{handoff_id}/approve", response=ActionResponse)
def approve_handoff(request, handoff_id: str, data: ApproveHandoffIn):
    h = get_object_or_404(AgentHandoffRequest, id=handoff_id, status="pending")
    from .handoff import resolve_handoff
    resolve_handoff(h, "approved", request.user.id, notes=data.notes or "")
    return {"ok": True, "message": "Handoff approved. Agent run will resume."}


@router.post("/handoffs/{handoff_id}/edit-approve", response=ActionResponse)
def edit_approve_handoff(request, handoff_id: str, data: EditApproveHandoffIn):
    h = get_object_or_404(AgentHandoffRequest, id=handoff_id, status="pending")
    from .handoff import resolve_handoff
    resolve_handoff(
        h, "edited_approved", request.user.id,
        notes=data.notes or "",
        edited_payload=data.edited_payload,
    )
    return {"ok": True, "message": "Handoff approved with edits. Agent run will resume."}


@router.post("/handoffs/{handoff_id}/reject", response=ActionResponse)
def reject_handoff(request, handoff_id: str, data: RejectHandoffIn):
    h = get_object_or_404(AgentHandoffRequest, id=handoff_id, status="pending")
    from .handoff import resolve_handoff
    resolve_handoff(h, "rejected", request.user.id, notes=data.reason)
    return {"ok": True, "message": "Handoff rejected. Rejection reason sent to agent as learning signal."}


@router.post("/handoffs/{handoff_id}/take-over", response=ActionResponse)
def take_over_handoff(request, handoff_id: str, data: TakeOverHandoffIn):
    h = get_object_or_404(AgentHandoffRequest, id=handoff_id, status="pending")
    from .handoff import resolve_handoff
    resolve_handoff(h, "taken_over", request.user.id, notes=data.notes or "")
    return {"ok": True, "message": "You have taken over this task. Agent run has been stopped."}


@router.post("/handoffs/{handoff_id}/acknowledge", response=ActionResponse)
def acknowledge_handoff(request, handoff_id: str, data: ApproveHandoffIn):
    """Acknowledge a review-queue entry (auto_execute_with_review)."""
    h = get_object_or_404(AgentHandoffRequest, id=handoff_id, status="pending")
    from .handoff import resolve_handoff
    resolve_handoff(h, "acknowledged", request.user.id, notes=data.notes or "")
    return {"ok": True, "message": "Review entry acknowledged."}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/status", response=Dict[str, Any])
def agent_system_status(request):
    """Platform-wide agent system status (requires staff)."""
    if not request.user.is_staff:
        from ninja.errors import HttpError
        raise HttpError(403, "Staff access required.")
    total_defs = AgentDefinition.objects.count()
    active_defs = AgentDefinition.objects.filter(is_active=True, is_paused=False).count()
    paused_defs = AgentDefinition.objects.filter(is_paused=True).count()
    running = AgentRun.objects.filter(status=AgentRun.Status.RUNNING).count()
    awaiting = AgentRun.objects.filter(status=AgentRun.Status.AWAITING_HUMAN).count()
    pending_handoffs = AgentHandoffRequest.objects.filter(status="pending").count()
    return {
        "agent_definitions": {"total": total_defs, "active": active_defs, "paused": paused_defs},
        "runs": {"running": running, "awaiting_human": awaiting},
        "pending_handoffs": pending_handoffs,
    }


@router.post("/admin/kill-all", response=ActionResponse)
def kill_all_agents(request):
    """Platform-wide kill switch — pauses all agents and kills all running runs."""
    if not request.user.is_staff:
        from ninja.errors import HttpError
        raise HttpError(403, "Staff access required.")

    # revoke_agent_run_task imported at module level

    # Pause all active definitions
    AgentDefinition.objects.filter(is_active=True).update(is_paused=True)

    # Signal all running/pending runs to stop
    running_runs = AgentRun.objects.filter(
        status__in=[AgentRun.Status.RUNNING, AgentRun.Status.PENDING]
    )
    count = 0
    for run in running_runs:
        AgentRun.objects.filter(pk=run.pk).update(kill_requested=True)
        if run.celery_task_id:
            revoke_agent_run_task.delay(run.celery_task_id)
        count += 1

    return {
        "ok": True,
        "message": "Platform-wide kill switch activated. {0} run(s) signalled to stop. All agent definitions paused.".format(count),
    }
