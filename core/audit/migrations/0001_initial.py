import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("odum_auth", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entity", models.CharField(db_index=True, max_length=100)),
                ("entity_id", models.CharField(db_index=True, max_length=128)),
                ("action", models.CharField(db_index=True, max_length=20)),
                ("company_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("origin", models.CharField(choices=[("human", "Human"), ("ai", "AI"), ("automation", "Automation (n8n / webhook)"), ("system", "System")], default="human", max_length=20)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("diff", models.JSONField(blank=True, null=True)),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(db_index=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "odum_audit_log",
                "ordering": ["-timestamp"],
                "indexes": [
                    models.Index(fields=["entity", "entity_id"], name="odum_audit_entity_idx"),
                    models.Index(fields=["user", "timestamp"], name="odum_audit_user_ts_idx"),
                ],
            },
        ),
    ]
