"""Celery tasks for the AI agent layer."""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="ai_agent.execute_agent_run",
    max_retries=0,           # do not auto-retry; handoff handles recovery
    acks_late=True,          # re-queue if worker dies mid-task
    reject_on_worker_lost=True,
)
def execute_agent_run(self, run_id: str) -> None:
    """
    Execute or resume an AgentRun.

    Called at initial trigger and after each human handoff resolution.
    The executor is idempotent on terminal runs.
    """
    from .executor import AgentRunExecutor
    from .models import AgentRun

    try:
        run = AgentRun.objects.get(id=run_id)
    except AgentRun.DoesNotExist:
        logger.error("execute_agent_run: run %s not found", run_id)
        return

    # Store task ID on the run record for kill-switch revocation
    AgentRun.objects.filter(pk=run.pk).update(celery_task_id=self.request.id or "")

    executor = AgentRunExecutor(run_id=run_id)
    executor.execute()


@shared_task(name="ai_agent.revoke_agent_run_task")
def revoke_agent_run_task(task_id: str) -> None:
    """Revoke a Celery task by ID (hard kill for in-flight runs)."""
    from celery import current_app
    current_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    logger.info("revoke_agent_run_task: revoked task %s", task_id)


@shared_task(name="ai_agent.expire_stale_handoffs")
def expire_stale_handoffs() -> None:
    """
    Scheduled task (Celery Beat, hourly): marks overdue pending handoffs as expired.

    A handoff with an explicit `expires_at` expires at that timestamp; otherwise
    it falls back to a 7-day default measured from creation. A suspending handoff
    (one that put its AgentRun into AWAITING_HUMAN) also fails the run when it
    expires, since nobody is left to resolve it and it would otherwise sit
    orphaned forever.
    """
    from datetime import timedelta

    from django.db.models import Q

    from .models import AgentHandoffRequest, AgentRun

    now = timezone.now()
    default_cutoff = now - timedelta(days=7)

    stale = AgentHandoffRequest.objects.filter(
        status=AgentHandoffRequest.HandoffStatus.PENDING,
    ).filter(
        Q(expires_at__isnull=False, expires_at__lt=now)
        | Q(expires_at__isnull=True, created_at__lt=default_cutoff)
    ).select_related("run")

    count = 0
    for handoff in stale:
        handoff.status = AgentHandoffRequest.HandoffStatus.EXPIRED
        handoff.save(update_fields=["status"])
        if handoff.is_suspending and not handoff.run.is_terminal():
            AgentRun.objects.filter(pk=handoff.run_id).update(
                status=AgentRun.Status.FAILED,
                completed_at=now,
                failure_reason="Handoff expired without human resolution.",
            )
        count += 1

    if count:
        logger.info("expire_stale_handoffs: expired %d handoff(s)", count)
