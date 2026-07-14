"""
HandoffService — assembles and delivers handoff packets.

Delivers into the AgentHandoffRequest table (the in-app inbox).
Optionally dispatches an outbound webhook event for n8n / external routing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone

from .tasks import execute_agent_run  # noqa: E402 — safe: tasks does not import handoff at module level

logger = logging.getLogger(__name__)


def create_handoff(
    run,
    step,
    trigger_reason: str,
    trigger_detail: str,
    proposed_action: Optional[Dict[str, Any]] = None,
    proposed_reasoning: str = "",
    confidence: Optional[float] = None,
    record_links: Optional[List[Dict[str, Any]]] = None,
    assigned_to_id=None,
    is_review_queue: bool = False,
) -> "AgentHandoffRequest":
    """
    Assemble a handoff packet and persist it.

    For suspending handoffs (is_review_queue=False) the run status is also
    set to AWAITING_HUMAN.  For review-queue entries the run keeps running.
    """
    from .models import AgentHandoffRequest, AgentRun

    handoff = AgentHandoffRequest.objects.create(
        run=run,
        step=step,
        trigger_reason=trigger_reason,
        trigger_detail=trigger_detail,
        proposed_action=proposed_action,
        proposed_reasoning=proposed_reasoning,
        confidence=confidence,
        data_gathered=dict(run.data_gathered),
        record_links=record_links or [],
        assigned_to_id=assigned_to_id,
        company_id=run.company_id,
        status=AgentHandoffRequest.HandoffStatus.PENDING,
    )

    if not is_review_queue:
        AgentRun.objects.filter(pk=run.pk).update(status=AgentRun.Status.AWAITING_HUMAN)
        run.status = AgentRun.Status.AWAITING_HUMAN

    if step is not None:
        from .models import AgentStep
        AgentStep.objects.filter(pk=step.pk).update(
            status=AgentStep.StepStatus.HANDED_OFF
        )

    # Optionally fire outbound webhook for n8n routing (fire-and-forget)
    _dispatch_webhook_event(handoff)

    logger.info(
        "Handoff created: run=%s reason=%s suspending=%s",
        run.id, trigger_reason, not is_review_queue,
    )
    return handoff


def resolve_handoff(
    handoff,
    resolution: str,
    resolved_by_id,
    notes: str = "",
    edited_payload: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Mark a handoff resolved and (if suspending) re-queue the run.
    resolution: "approved" | "edited_approved" | "rejected" | "taken_over" | "acknowledged"
    """
    from .models import AgentHandoffRequest, AgentRun

    handoff.status = resolution
    handoff.resolved_by_id = resolved_by_id
    handoff.resolved_at = timezone.now()
    handoff.resolution_notes = notes
    if edited_payload is not None:
        handoff.edited_payload = edited_payload
    handoff.save(update_fields=[
        "status", "resolved_by_id", "resolved_at", "resolution_notes", "edited_payload",
    ])

    run = handoff.run
    if resolution == "taken_over":
        AgentRun.objects.filter(pk=run.pk).update(
            status=AgentRun.Status.KILLED,
            completed_at=timezone.now(),
            failure_reason="Human took over task",
        )
        return

    if resolution == "acknowledged":
        # Review-queue only — run is not suspended so no re-queue needed
        return

    if handoff.is_suspending:
        if resolution == "rejected":
            # Store rejection as a learning signal in the run context
            run.refresh_from_db()
            rejections = run.context.get("rejections", [])
            rejections.append({
                "handoff_id": str(handoff.id),
                "proposed_action": handoff.proposed_action,
                "reason": notes,
                "rejected_at": timezone.now().isoformat(),
            })
            AgentRun.objects.filter(pk=run.pk).update(
                status=AgentRun.Status.PENDING,
                context={**run.context, "rejections": rejections},
            )
        else:
            # approved / edited_approved → re-queue
            AgentRun.objects.filter(pk=run.pk).update(status=AgentRun.Status.PENDING)

        execute_agent_run.delay(str(run.pk))


def _dispatch_webhook_event(handoff) -> None:
    """Fire-and-forget webhook to notify external systems (n8n etc.)."""
    from django.conf import settings
    webhook_url = getattr(settings, "ODUM_AI_AGENT", {}).get("handoff_webhook_url")
    if not webhook_url:
        return

    import json
    import threading
    import urllib.request

    def _send():
        payload = json.dumps({
            "event": "agent_handoff.created",
            "handoff_id": str(handoff.id),
            "run_id": str(handoff.run_id),
            "agent_slug": handoff.run.agent.slug,
            "trigger_reason": handoff.trigger_reason,
            "company_id": str(handoff.company_id) if handoff.company_id else None,
        }).encode()
        try:
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.debug("Handoff webhook dispatch failed (non-critical): %s", exc)

    threading.Thread(target=_send, daemon=True).start()
