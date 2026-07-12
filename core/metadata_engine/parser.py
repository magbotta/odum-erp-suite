"""YAML parser for entity definition files."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .definitions import EntityDefinition
from .registry import registry

logger = logging.getLogger("ochre.metadata_engine")


def load_entity_file(path: Path) -> EntityDefinition | None:
    """Parse a single YAML entity definition file and return an EntityDefinition."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return EntityDefinition.model_validate(raw)
    except Exception as exc:
        logger.error("Failed to load entity definition %s: %s", path, exc)
        return None


def scan_directory(directory: Path) -> list[EntityDefinition]:
    """
    Scan a directory (recursively) for *.yaml entity definitions.
    Returns all successfully parsed definitions.
    """
    loaded = []
    if not directory.is_dir():
        return loaded
    for yaml_file in sorted(directory.rglob("*.yaml")):
        defn = load_entity_file(yaml_file)
        if defn is not None:
            registry.register(defn)
            loaded.append(defn)
            logger.debug("Registered entity %s.%s from %s", defn.app, defn.entity, yaml_file)
    return loaded


def scan_entity_dirs(dirs: list[str]) -> None:
    """Scan a list of directory paths (as strings) for entity definitions."""
    for d in dirs:
        path = Path(d)
        found = scan_directory(path)
        if found:
            logger.info("Loaded %d entity definitions from %s", len(found), path)


def register_entity(definition: EntityDefinition) -> None:
    """Register a single entity definition programmatically (Python API)."""
    registry.register(definition)
    logger.debug("Registered entity %s.%s (programmatic)", definition.app, definition.entity)
