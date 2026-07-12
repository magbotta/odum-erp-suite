"""Atomic document number generation."""
from __future__ import annotations

from uuid import UUID

from django.db import transaction


def get_next_number(series_name: str, company_id: UUID | str | None = None) -> str:
    """
    Atomically increment and return the next formatted document number.
    Creates the series with sensible defaults if it doesn't exist yet.
    """
    from .models import NumberSeries

    with transaction.atomic():
        series, _ = NumberSeries.objects.select_for_update().get_or_create(
            name=series_name,
            company_id=company_id,
            defaults={"prefix": f"{series_name}-", "padding": 5},
        )
        series.current_number += 1
        series.save(update_fields=["current_number"])
        return f"{series.prefix}{str(series.current_number).zfill(series.padding)}"
