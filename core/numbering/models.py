"""Configurable document number series (§12 soft-delete + configurable numbering)."""
from __future__ import annotations

import uuid
from django.db import models


class NumberSeries(models.Model):
    """
    Auto-incrementing number series per document type and company.
    Generates numbers like INV-2026-00042.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, help_text="e.g. INV, PO, SO, GRN, PAY")
    prefix = models.CharField(max_length=20, blank=True, help_text="e.g. INV-2026-")
    current_number = models.PositiveIntegerField(default=0)
    padding = models.PositiveSmallIntegerField(default=5, help_text="Zero-pad width")
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "odum_number_series"
        unique_together = [("name", "company_id")]
        verbose_name = "Number Series"
        verbose_name_plural = "Number Series"

    def __str__(self) -> str:
        return f"{self.name} → {self.prefix}{str(self.current_number + 1).zfill(self.padding)}"
