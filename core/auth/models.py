"""Auth models: User, Company, Role, APIKey."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class OchreUserManager(BaseUserManager["OchreUser"]):
    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "OchreUser":
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields) -> "OchreUser":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class OchreUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = OchreUserManager()

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email


class Company(models.Model):
    """A legal entity / business unit. All transactional data is scoped to a company."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    abbr = models.CharField(max_length=10, help_text="Short abbreviation used in document numbering")
    default_currency = models.CharField(max_length=3, default="USD")
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subsidiaries"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_companies"
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self) -> str:
        return self.name


class Role(models.Model):
    """A named permission set, optionally scoped to a company."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.CASCADE, related_name="roles",
        help_text="Null = platform-wide role",
    )
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False, help_text="System roles cannot be deleted")

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_roles"
        unique_together = [("name", "company")]

    def __str__(self) -> str:
        if self.company:
            return f"{self.name} ({self.company})"
        return self.name


class UserRole(models.Model):
    """Many-to-many between users and roles, scoped to a company."""
    user = models.ForeignKey(OchreUser, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="user_roles")
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        OchreUser, null=True, on_delete=models.SET_NULL, related_name="grants_given"
    )

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_user_roles"
        unique_together = [("user", "role", "company")]


class EntityPermission(models.Model):
    """Defines what a role can do on a given entity type."""
    ACTIONS = ["read", "write", "submit", "cancel", "delete"]

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="entity_permissions")
    entity = models.CharField(max_length=100, help_text="Entity name, e.g. 'SalesInvoice'")
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)
    can_submit = models.BooleanField(default=False)
    can_cancel = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    row_filter = models.JSONField(
        null=True, blank=True,
        help_text="Optional JSON filter applied to restrict which rows are visible",
    )

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_entity_permissions"
        unique_together = [("role", "entity")]

    def __str__(self) -> str:
        return f"{self.role} → {self.entity}"


class APIKey(models.Model):
    """Long-lived API key for service accounts and n8n/webhook integrations."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(OchreUser, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=8, editable=False)
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="api_keys"
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "ochre_auth"
        db_table = "ochre_api_keys"

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"

    @classmethod
    def generate(cls, user: OchreUser, name: str, **kwargs) -> tuple["APIKey", str]:
        """Create a new API key. Returns (instance, raw_key). Raw key is only shown once."""
        raw = secrets.token_urlsafe(32)
        prefix = raw[:8]
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        instance = cls.objects.create(
            user=user, name=name, key_hash=key_hash, prefix=prefix, **kwargs
        )
        return instance, raw

    @classmethod
    def verify(cls, raw: str) -> "APIKey | None":
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        try:
            key = cls.objects.select_related("user").get(
                key_hash=key_hash, is_active=True
            )
        except cls.DoesNotExist:
            return None
        if key.expires_at and key.expires_at < timezone.now():
            return None
        cls.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return key
