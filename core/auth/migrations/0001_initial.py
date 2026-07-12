import uuid
import django.contrib.auth.models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="OchreUser",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("email", models.EmailField(db_index=True, max_length=254, unique=True)),
                ("first_name", models.CharField(blank=True, max_length=150)),
                ("last_name", models.CharField(blank=True, max_length=150)),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now)),
                ("groups", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={"db_table": "ochre_users", "verbose_name": "User", "verbose_name_plural": "Users"},
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("abbr", models.CharField(max_length=10)),
                ("default_currency", models.CharField(default="USD", max_length=3)),
                ("country", models.CharField(blank=True, max_length=2)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="subsidiaries", to="ochre_auth.company")),
            ],
            options={"db_table": "ochre_companies", "verbose_name": "Company", "verbose_name_plural": "Companies"},
        ),
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("is_system", models.BooleanField(default=False)),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="roles", to="ochre_auth.company")),
            ],
            options={"db_table": "ochre_roles", "unique_together": {("name", "company")}},
        ),
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_roles", to=settings.AUTH_USER_MODEL)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_roles", to="ochre_auth.role")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_roles", to="ochre_auth.company")),
                ("granted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="grants_given", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "ochre_user_roles", "unique_together": {("user", "role", "company")}},
        ),
        migrations.CreateModel(
            name="EntityPermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entity", models.CharField(max_length=100)),
                ("can_read", models.BooleanField(default=False)),
                ("can_write", models.BooleanField(default=False)),
                ("can_submit", models.BooleanField(default=False)),
                ("can_cancel", models.BooleanField(default=False)),
                ("can_delete", models.BooleanField(default=False)),
                ("row_filter", models.JSONField(blank=True, null=True)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entity_permissions", to="ochre_auth.role")),
            ],
            options={"db_table": "ochre_entity_permissions", "unique_together": {("role", "entity")}},
        ),
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("key_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("prefix", models.CharField(editable=False, max_length=8)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="api_keys", to="ochre_auth.company")),
            ],
            options={"db_table": "ochre_api_keys"},
        ),
    ]
