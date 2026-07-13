"""CRM opportunity hooks (§6.3)."""
from __future__ import annotations

from django.utils import timezone


def sync_stage_probability(opportunity) -> None:
    """Pull default probability from the linked PipelineStage when stage changes."""
    if opportunity.stage_id and opportunity.stage:
        stage = opportunity.stage
        if opportunity.probability == 0 or opportunity.probability == _previous_stage_probability(opportunity):
            opportunity.probability = stage.probability
        if stage.is_won:
            opportunity.forecast_category = "closed_won"
        elif stage.is_lost:
            opportunity.forecast_category = "closed_lost"
        elif opportunity.probability >= 90:
            opportunity.forecast_category = "commit"
        elif opportunity.probability >= 50:
            opportunity.forecast_category = "best_case"
        else:
            opportunity.forecast_category = "pipeline"


def _previous_stage_probability(opportunity) -> int:
    """Return the probability of the previous stage, or 0 if no prior stage."""
    try:
        from apps.crm.models import Opportunity
        prev = Opportunity.objects.filter(pk=opportunity.pk).values_list("stage__probability", flat=True).first()
        return prev or 0
    except Exception:
        return 0


def close_won(opportunity) -> None:
    """Mark opportunity closed-won and snapshot timestamp."""
    opportunity.forecast_category = "closed_won"
    if not opportunity.closed_at:
        opportunity.closed_at = timezone.now()


def close_lost(opportunity) -> None:
    """Mark opportunity closed-lost and snapshot timestamp."""
    opportunity.forecast_category = "closed_lost"
    if not opportunity.closed_at:
        opportunity.closed_at = timezone.now()
