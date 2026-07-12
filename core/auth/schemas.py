"""Pydantic schemas for auth API requests and responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from ninja import Schema


class LoginIn(Schema):
    email: str
    password: str


class TokenOut(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(Schema):
    refresh_token: str


class UserOut(Schema):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_staff: bool
    date_joined: datetime


class RegisterIn(Schema):
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""


class APIKeyCreateIn(Schema):
    name: str
    company_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class APIKeyOut(Schema):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None = None


class APIKeyCreatedOut(APIKeyOut):
    key: str  # only returned once at creation time
