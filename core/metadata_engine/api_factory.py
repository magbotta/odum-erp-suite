"""
Dynamically generates Django Ninja routers from EntityDefinition objects.
Called at startup by PlatformAPIConfig.ready() after all entities are registered.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

from ninja import Router
from pydantic import create_model, Field

if TYPE_CHECKING:
    from .definitions import EntityDefinition

logger = logging.getLogger("ochre.metadata_engine.api_factory")

# Maps entity field types → Python/Pydantic types
_PYTHON_TYPE: dict[str, type] = {
    "string": str,
    "text": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "date": str,  # ISO date string
    "datetime": str,  # ISO datetime string
    "currency": float,
    "link": str,  # FK as UUID/pk string
    "select": str,
    "multiselect": list,
    "email": str,
    "phone": str,
    "url": str,
    "json": dict,
    "geopoint": dict,
    "geofence": dict,
    "route": dict,
}


def _build_schemas(definition: "EntityDefinition"):
    """Return (CreateSchema, UpdateSchema, ReadSchema) pydantic models."""
    create_fields: dict[str, Any] = {}
    update_fields: dict[str, Any] = {}
    read_fields: dict[str, Any] = {
        "id": (str, ...),
        "company_id": (Optional[str], None),
        "created_at": (str, ...),
        "updated_at": (str, ...),
    }

    if definition.workflow:
        read_fields["status"] = (str, definition.workflow.initial_state)
        update_fields["status"] = (Optional[str], None)

    for field in definition.fields:
        if field.computed:
            continue  # computed fields are read-only
        py_type = _PYTHON_TYPE.get(field.type, Any)
        if field.required:
            create_fields[field.name] = (py_type, ...)
        else:
            default = field.default
            create_fields[field.name] = (Optional[py_type], default)
        update_fields[field.name] = (Optional[py_type], None)
        read_fields[field.name] = (Optional[py_type], None)

    entity = definition.entity
    CreateSchema = create_model(f"{entity}Create", **create_fields)
    UpdateSchema = create_model(f"{entity}Update", **update_fields)
    ReadSchema = create_model(f"{entity}Read", **read_fields)
    return CreateSchema, UpdateSchema, ReadSchema


def build_entity_router(definition: "EntityDefinition") -> Router:
    """
    Build a Ninja Router with CRUD endpoints for the given entity.
    The actual ORM model lookup is deferred so this can be called before
    all models are available (e.g., during startup scanning).
    """
    from django.apps import apps as django_apps

    CreateSchema, UpdateSchema, ReadSchema = _build_schemas(definition)

    router = Router(tags=[definition.display_label])
    entity_name = definition.entity
    app_label = definition.app

    def _get_model():
        for model in django_apps.get_models():
            if model.__name__ == entity_name:
                return model
        return None

    @router.get("", response=list[ReadSchema], summary=f"List {definition.display_label_plural}")
    def list_entities(request, page: int = 1, page_size: int = 50):
        model = _get_model()
        if model is None:
            return []
        qs = model.objects.filter(is_deleted=False)
        # Apply company scoping
        if hasattr(request, "active_company_id") and request.active_company_id:
            qs = qs.filter(company_id=request.active_company_id)
        offset = (page - 1) * page_size
        return list(qs[offset : offset + page_size].values())

    @router.get("/{id}", response=ReadSchema, summary=f"Get {definition.display_label}")
    def get_entity(request, id: str):
        from ninja.errors import HttpError
        model = _get_model()
        if model is None:
            raise HttpError(404, f"Entity {entity_name} not found")
        try:
            obj = model.objects.get(pk=id, is_deleted=False)
        except model.DoesNotExist:
            raise HttpError(404, "Not found")
        from django.forms.models import model_to_dict
        return {**model_to_dict(obj), "id": str(obj.pk)}

    @router.post("", response=ReadSchema, summary=f"Create {definition.display_label}")
    def create_entity(request, payload: CreateSchema):
        model = _get_model()
        if model is None:
            from ninja.errors import HttpError
            raise HttpError(404, f"Entity {entity_name} not available")
        data = payload.model_dump(exclude_none=True)
        if definition.multi_company and hasattr(request, "active_company_id"):
            data["company_id"] = request.active_company_id
        if hasattr(request, "user") and request.user.is_authenticated:
            data["created_by_id"] = request.user.id
        obj = model.objects.create(**data)
        from django.forms.models import model_to_dict
        return {**model_to_dict(obj), "id": str(obj.pk)}

    @router.patch("/{id}", response=ReadSchema, summary=f"Update {definition.display_label}")
    def update_entity(request, id: str, payload: UpdateSchema):
        from ninja.errors import HttpError
        model = _get_model()
        if model is None:
            raise HttpError(404, f"Entity {entity_name} not available")
        try:
            obj = model.objects.get(pk=id, is_deleted=False)
        except model.DoesNotExist:
            raise HttpError(404, "Not found")
        data = payload.model_dump(exclude_none=True)
        for k, v in data.items():
            setattr(obj, k, v)
        if hasattr(request, "user") and request.user.is_authenticated:
            obj.updated_by_id = request.user.id
        obj.save()
        from django.forms.models import model_to_dict
        return {**model_to_dict(obj), "id": str(obj.pk)}

    @router.delete("/{id}", summary=f"Delete {definition.display_label}")
    def delete_entity(request, id: str):
        from ninja.errors import HttpError
        model = _get_model()
        if model is None:
            raise HttpError(404, f"Entity {entity_name} not available")
        try:
            obj = model.objects.get(pk=id, is_deleted=False)
        except model.DoesNotExist:
            raise HttpError(404, "Not found")
        obj.soft_delete()
        return {"ok": True, "id": id}

    return router


def register_all_entity_routers(api) -> None:
    """Mount auto-generated routers for all registered entities onto the main API."""
    from .registry import registry

    for definition in registry.all():
        try:
            router = build_entity_router(definition)
            api.add_router(definition.api_path, router)
            logger.debug("Mounted router for %s at %s", definition.entity, definition.api_path)
        except Exception as exc:
            logger.error("Failed to mount router for %s: %s", definition.entity, exc)
