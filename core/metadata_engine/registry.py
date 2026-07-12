"""Central registry that maps entity names to their definitions."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .definitions import EntityDefinition


class EntityRegistry:
    """Thread-safe registry for all registered EntityDefinition objects."""

    def __init__(self):
        self._entities: dict[str, "EntityDefinition"] = {}
        self._lock = threading.RLock()

    def register(self, definition: "EntityDefinition") -> None:
        key = f"{definition.app}.{definition.entity}"
        with self._lock:
            self._entities[key] = definition

    def unregister(self, app: str, entity: str) -> None:
        with self._lock:
            self._entities.pop(f"{app}.{entity}", None)

    def get(self, app: str, entity: str) -> "EntityDefinition | None":
        return self._entities.get(f"{app}.{entity}")

    def get_by_name(self, entity: str) -> "EntityDefinition | None":
        for defn in self._entities.values():
            if defn.entity == entity:
                return defn
        return None

    def all(self) -> list["EntityDefinition"]:
        with self._lock:
            return list(self._entities.values())

    def for_app(self, app: str) -> list["EntityDefinition"]:
        return [d for d in self._entities.values() if d.app == app]

    def names(self) -> list[str]:
        return list(self._entities.keys())

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, key: str) -> bool:
        return key in self._entities


registry = EntityRegistry()
