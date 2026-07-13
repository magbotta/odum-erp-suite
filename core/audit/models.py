"""Universal audit trail — every entity write is logged here."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Immutable record of every change made to any entity in the system."""

    class Origin(models.TextChoices):
        HUMAN = "human", "Human"
        AI = "ai", "AI"
        AUTOMATION = "automation", "Automation (n8n / webhook)"
        SYSTEM = "system", "System"

    # What changed
    entity = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=128, db_index=True)
    action = models.CharField(
        max_length=20,
        db_index=True,
        help_text="create / update / delete / submit / cancel",
    )

    # Context
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.HUMAN)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    # Payload
    before = models.JSONField(null=True, blank=True, help_text="Snapshot before change")
    after = models.JSONField(null=True, blank=True, help_text="Snapshot after change")
    diff = models.JSONField(null=True, blank=True, help_text="Field-level diff {field: [old, new]}")

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "odum_audit"
        db_table = "odum_audit_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["entity", "entity_id"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} {self.entity}/{self.entity_id}"
