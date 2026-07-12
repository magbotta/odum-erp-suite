"""Ninja HTTP security schemes for the platform API."""
from __future__ import annotations

from ninja.security import HttpBearer


class AuthBearer(HttpBearer):
    """Validates JWT Bearer tokens and API keys from the Authorization header."""

    def authenticate(self, request, token: str):
        from django.contrib.auth import authenticate

        # Try JWT first, then API key
        user = authenticate(request, token=token)
        if user is None:
            user = authenticate(request, api_key=token)
        if user is not None and user.is_active:
            request.user = user
            return user
        return None
