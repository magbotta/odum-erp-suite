"""Authentication backends: JWT and API Key."""
from __future__ import annotations

import jwt
from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.http import HttpRequest

from .models import APIKey, OchreUser


class JWTBackend(BaseBackend):
    """Validates a Bearer JWT in the Authorization header."""

    def authenticate(self, request: HttpRequest, token: str | None = None, **kwargs):
        if token is None:
            return None
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        if payload.get("type") != "access":
            return None

        try:
            return OchreUser.objects.get(pk=payload["sub"], is_active=True)
        except OchreUser.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return OchreUser.objects.get(pk=user_id)
        except OchreUser.DoesNotExist:
            return None


class APIKeyBackend(BaseBackend):
    """Validates an API key passed as Bearer token or X-API-Key header."""

    def authenticate(self, request: HttpRequest, api_key: str | None = None, **kwargs):
        if api_key is None:
            return None
        key = APIKey.verify(api_key)
        if key is None:
            return None
        return key.user if key.user.is_active else None

    def get_user(self, user_id):
        try:
            return OchreUser.objects.get(pk=user_id)
        except OchreUser.DoesNotExist:
            return None
