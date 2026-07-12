"""Mixin for Django models that emit audit log entries on save/delete."""
from __future__ import annotations

import json
from typing import Any

from django.db import models

from .middleware import get_current_request
from .models import AuditLog


def _serialize(instance: models.Model) -> dict:
    """Produce a JSON-serializable snapshot of a model instance."""
    data = {}
    for field in instance._meta.get_fields():
        if hasattr(field, "attname"):
            val = getattr(instance, field.attname, None)
            try:
                json.dumps(val)
                data[field.name] = val
            except (TypeError, ValueError):
                data[field.name] = str(val)
    return data


def _diff(before: dict | None, after: dict | None) -> dict:
    if not before:
        return {}
    if not after:
        return {}
    return {
        k: [before.get(k), after.get(k)]
        for k in set(list(before.keys()) + list(after.keys()))
        if before.get(k) != after.get(k)
    }


class AuditableMixin:
    """
    Add to any Django Model to get automatic audit logging on save and delete.
    The entity name defaults to the model class name; override _audit_entity to change it.
    """

    _audit_entity: str = ""

    def _get_audit_entity(self) -> str:
        return self._audit_entity or self.__class__.__name__

    def _get_audit_id(self) -> str:
        return str(self.pk)

    def _get_request_context(self) -> dict[str, Any]:
        request = get_current_request()
        if request is None:
            return {}
        return {
            "user": getattr(request, "user", None) if (
                hasattr(request, "user") and request.user.is_authenticated
            ) else None,
            "ip_address": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
        }

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        before = None
        if not is_new:
            try:
                before = _serialize(self.__class__.objects.get(pk=self.pk))
            except self.__class__.DoesNotExist:
                pass

        super().save(*args, **kwargs)
        after = _serialize(self)

        ctx = self._get_request_context()
        AuditLog.objects.create(
            entity=self._get_audit_entity(),
            entity_id=self._get_audit_id(),
            action="create" if is_new else "update",
            before=before,
            after=after,
            diff=_diff(before, after),
            **ctx,
        )

    def delete(self, *args, **kwargs):
        before = _serialize(self)
        ctx = self._get_request_context()
        result = super().delete(*args, **kwargs)
        AuditLog.objects.create(
            entity=self._get_audit_entity(),
            entity_id=str(self.pk),
            action="delete",
            before=before,
            after=None,
            diff={},
            **ctx,
        )
        return result
