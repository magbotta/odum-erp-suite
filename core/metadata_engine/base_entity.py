"""Abstract base Django model that every entity-engine-generated model inherits from."""
from __future__ import annotations

import uuid

from django.db import models


class BaseEntity(models.Model):
    """
    Common fields for every entity in Ochre ERP.
    Provides: UUID PK, company scoping, timestamps, soft-delete, JSONB custom fields.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_id = models.UUIDField(db_index=True, null=True, blank=True)
    custom_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Admin-added custom fields (backed by JSONB).",
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_id = models.UUIDField(null=True, blank=True)
    updated_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])
