"""Register the hourly expire_stale_handoffs Celery Beat task (DatabaseScheduler)."""
from django.db import migrations


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=1, period="hours",
    )
    PeriodicTask.objects.get_or_create(
        task="ai_agent.expire_stale_handoffs",
        defaults={
            "name": "AI Agent: expire stale handoffs",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(task="ai_agent.expire_stale_handoffs").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("odum_ai_agent", "0002_rename_odum_handoffs_company_status_idx_odum_agent__company_e9bbcf_idx_and_more"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
