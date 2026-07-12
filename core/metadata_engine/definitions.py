"""Pydantic models for the Entity Definition schema (the YAML format for §5)."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

FieldType = Literal[
    "string",
    "text",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "currency",
    "link",
    "table",
    "select",
    "multiselect",
    "email",
    "phone",
    "url",
    "json",
    "geopoint",
    "geofence",
    "route",
]


class FieldDefinition(BaseModel):
    name: str
    type: FieldType
    label: Optional[str] = None
    required: bool = False
    unique: bool = False
    default: Optional[Any] = None
    target: Optional[str] = None  # for link/table: target entity name
    options: Optional[list[str]] = None  # for select/multiselect
    computed: Optional[str] = None  # expression string for computed fields
    hidden: bool = False
    read_only: bool = False
    ai_eligible: bool = True  # whether AI copilot may include this field in context
    encrypted: bool = False  # field-level encryption (used for PHI, salary, etc.)
    max_length: Optional[int] = None  # for string fields

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        return self.name.replace("_", " ").title()


class PermissionDefinition(BaseModel):
    role: str
    read: bool = False
    write: bool = False
    submit: bool = False
    cancel: bool = False
    delete: bool = False


class WorkflowTransition(BaseModel):
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    action: Optional[str] = None
    condition: Optional[str] = None

    model_config = {"populate_by_name": True}


class WorkflowDefinition(BaseModel):
    states: list[str]
    initial_state: Optional[str] = None
    transitions: list[WorkflowTransition] = []

    @model_validator(mode="after")
    def set_initial(self) -> "WorkflowDefinition":
        if self.initial_state is None and self.states:
            self.initial_state = self.states[0]
        return self


class HooksDefinition(BaseModel):
    before_validate: list[str] = []
    before_save: list[str] = []
    after_save: list[str] = []
    before_submit: list[str] = []
    after_submit: list[str] = []
    before_cancel: list[str] = []
    after_cancel: list[str] = []
    before_delete: list[str] = []
    after_delete: list[str] = []


class EntityDefinition(BaseModel):
    entity: str
    app: str
    label: Optional[str] = None
    label_plural: Optional[str] = None
    description: Optional[str] = None
    fields: list[FieldDefinition] = []
    permissions: list[PermissionDefinition] = []
    workflow: Optional[WorkflowDefinition] = None
    hooks: HooksDefinition = Field(default_factory=HooksDefinition)

    # Behaviour flags
    track_changes: bool = True
    is_submittable: bool = False
    is_tree: bool = False
    allow_rename: bool = False
    multi_company: bool = True  # whether company_id is added automatically

    # API surface
    api_prefix: Optional[str] = None

    @property
    def snake_name(self) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", self.entity).lower()

    @property
    def display_label(self) -> str:
        return self.label or self.entity

    @property
    def display_label_plural(self) -> str:
        return self.label_plural or f"{self.display_label}s"

    @property
    def api_path(self) -> str:
        if self.api_prefix:
            return self.api_prefix
        slug = self.snake_name.replace("_", "-")
        return f"/{self.app}/{slug}"
