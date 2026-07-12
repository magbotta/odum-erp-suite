"""RBAC helpers: check entity-level and row-level permissions."""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from .models import EntityPermission, OchreUser, UserRole

if TYPE_CHECKING:
    from uuid import UUID


def get_user_roles(user: OchreUser, company_id: "UUID | None" = None) -> list[str]:
    """Return role names for a user, optionally filtered by company."""
    qs = UserRole.objects.filter(user=user).select_related("role")
    if company_id:
        qs = qs.filter(company_id=company_id)
    return [ur.role.name for ur in qs]


def has_entity_permission(
    user: OchreUser,
    entity: str,
    action: str,
    company_id: "UUID | None" = None,
) -> bool:
    """
    Return True if the user has the given action on the entity.
    action: one of read / write / submit / cancel / delete
    """
    if user.is_superuser:
        return True

    role_names = get_user_roles(user, company_id)
    if not role_names:
        return False

    action_field = f"can_{action}"
    return EntityPermission.objects.filter(
        role__name__in=role_names,
        entity=entity,
        **{action_field: True},
    ).exists()


def get_row_filters(user: OchreUser, entity: str, company_id: "UUID | None" = None) -> list[dict]:
    """Return all row_filter JSON objects applicable to this user/entity combo."""
    if user.is_superuser:
        return []

    role_names = get_user_roles(user, company_id)
    perms = EntityPermission.objects.filter(
        role__name__in=role_names,
        entity=entity,
        can_read=True,
        row_filter__isnull=False,
    )
    return [p.row_filter for p in perms]
