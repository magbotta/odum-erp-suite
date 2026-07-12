"""Expose the entity registry as a REST endpoint so the frontend can discover entities."""
from ninja import Router
from core.platform_api.security import AuthBearer
from core.metadata_engine.registry import registry

meta_router = Router(tags=["Metadata"], auth=AuthBearer())


@meta_router.get("/entities/")
def list_entities(request):
    return [_serialize(d) for d in registry.all()]


@meta_router.get("/entities/{app}/{entity}/")
def get_entity(request, app: str, entity: str):
    from ninja.errors import HttpError
    defn = registry.get(app, entity)
    if not defn:
        raise HttpError(404, f"{app}.{entity} not found")
    return _serialize(defn)


def _serialize(d):
    return {
        "key": f"{d.app}.{d.entity}",
        "entity": d.entity,
        "app": d.app,
        "label": d.display_label,
        "label_plural": d.display_label_plural,
        "snake_name": d.snake_name,
        "api_slug": d.snake_name.replace("_", "-"),
        "api_path": d.api_path,
        "fields": [
            {
                "name": f.name,
                "type": f.type,
                "label": f.display_label,
                "required": f.required,
                "options": f.options,
                "target": f.target,
                "hidden": f.hidden,
                "read_only": f.read_only,
            }
            for f in d.fields
            if not f.hidden
        ],
        "workflow": {
            "states": d.workflow.states,
            "initial_state": d.workflow.initial_state,
            "transitions": [
                {"from": t.from_state, "to": t.to_state, "action": t.action}
                for t in d.workflow.transitions
            ],
        } if d.workflow else None,
    }
