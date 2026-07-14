from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("odum_audit", "0003_rename_odum_audit_entity_7da4d5_idx_odum_audit__entity_ae7582_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="agent_run_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                null=True,
                help_text="AgentRun.id that caused this write; null for non-agent origins",
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="agent_slug",
            field=models.CharField(
                blank=True,
                max_length=50,
                help_text="AgentDefinition.slug for AI-originated writes",
            ),
        ),
    ]
