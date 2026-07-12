"""Auth endpoints: login, refresh, register, API key management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from ninja import Router

from .models import APIKey, OchreUser
from .schemas import (
    APIKeyCreateIn,
    APIKeyCreatedOut,
    APIKeyOut,
    LoginIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserOut,
)
from core.platform_api.security import AuthBearer

router = Router(tags=["auth"])


def _make_tokens(user: OchreUser) -> dict:
    now = datetime.now(tz=timezone.utc)
    access_payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    }
    refresh_payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    }
    return {
        "access_token": jwt.encode(access_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM),
        "refresh_token": jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM),
    }


@router.post("/login", response=TokenOut, auth=None)
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.email, password=payload.password)
    if user is None:
        from ninja.errors import HttpError
        raise HttpError(401, "Invalid credentials")
    return _make_tokens(user)


@router.post("/refresh", response=TokenOut, auth=None)
def refresh(request, payload: RefreshIn):
    from ninja.errors import HttpError
    try:
        data = jwt.decode(
            payload.refresh_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.InvalidTokenError:
        raise HttpError(401, "Invalid or expired refresh token")
    if data.get("type") != "refresh":
        raise HttpError(401, "Not a refresh token")
    try:
        user = OchreUser.objects.get(pk=data["sub"], is_active=True)
    except OchreUser.DoesNotExist:
        raise HttpError(401, "User not found")
    return _make_tokens(user)


@router.post("/register", response=UserOut, auth=None)
def register(request, payload: RegisterIn):
    from ninja.errors import HttpError
    if OchreUser.objects.filter(email=payload.email).exists():
        raise HttpError(400, "Email already registered")
    user = OchreUser.objects.create_user(
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return user


@router.get("/me", response=UserOut, auth=AuthBearer())
def me(request):
    return request.user


@router.get("/api-keys", response=list[APIKeyOut], auth=AuthBearer())
def list_api_keys(request):
    return list(request.user.api_keys.filter(is_active=True).order_by("-created_at"))


@router.post("/api-keys", response=APIKeyCreatedOut, auth=AuthBearer())
def create_api_key(request, payload: APIKeyCreateIn):
    instance, raw = APIKey.generate(
        user=request.user,
        name=payload.name,
        company_id=payload.company_id,
        expires_at=payload.expires_at,
    )
    return APIKeyCreatedOut(
        id=instance.id,
        name=instance.name,
        prefix=instance.prefix,
        created_at=instance.created_at,
        expires_at=instance.expires_at,
        key=raw,
    )


@router.delete("/api-keys/{key_id}", auth=AuthBearer())
def revoke_api_key(request, key_id: str):
    from ninja.errors import HttpError
    updated = request.user.api_keys.filter(pk=key_id).update(is_active=False)
    if not updated:
        raise HttpError(404, "API key not found")
    return {"ok": True}
