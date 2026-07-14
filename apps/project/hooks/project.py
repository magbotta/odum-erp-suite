"""Project hooks: budget vs actual, task completion rollup."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.project.models import Project, ProjectTask


def update_project_progress(project: "Project") -> None:
    """Recompute percent_complete from task statuses and update actual_cost from timesheets."""
    from apps.project.models import ProjectTask, TimesheetEntry

    tasks = ProjectTask.objects.filter(project=project, is_deleted=False)
    total = tasks.count()
    if total == 0:
        project.percent_complete = Decimal("0")
    else:
        done = tasks.filter(status=ProjectTask.Status.DONE).count()
        project.percent_complete = Decimal(str(round(done / total * 100, 2)))

    # Actual cost from billable timesheet entries
    from django.db.models import Sum
    result = TimesheetEntry.objects.filter(
        project=project, is_billable=True, is_deleted=False
    ).aggregate(total=Sum("billing_amount"))
    project.actual_cost = result["total"] or Decimal("0")

    project.save(update_fields=["percent_complete", "actual_cost"])


def update_task_hours(task: "ProjectTask") -> None:
    """Rollup actual_hours from TimesheetEntry rows for this task."""
    from django.db.models import Sum
    from apps.project.models import TimesheetEntry

    result = TimesheetEntry.objects.filter(task=task, is_deleted=False).aggregate(
        total=Sum("hours")
    )
    task.actual_hours = result["total"] or Decimal("0")
    task.save(update_fields=["actual_hours"])


def create_project_from_template(template_id, project_name, start_date, company_id, customer_id=None,
                                  customer_name="", currency="USD"):
    """Instantiate a project and its tasks from a ProjectTemplate."""
    import datetime
    from apps.project.models import Project, ProjectTask, ProjectTemplate

    try:
        template = ProjectTemplate.objects.get(id=template_id, is_deleted=False)
    except ProjectTemplate.DoesNotExist:
        raise ValueError("Template {} not found.".format(template_id))

    if isinstance(start_date, str):
        start_date = datetime.date.fromisoformat(start_date)

    project = Project.objects.create(
        project_name=project_name,
        template=template,
        billing_type=template.default_billing_type,
        start_date=start_date,
        expected_end_date=start_date + datetime.timedelta(days=template.estimated_days),
        customer_id=customer_id,
        customer_name=customer_name,
        currency=currency,
        company_id=company_id,
    )

    for tt in template.template_tasks.order_by("sequence"):
        task_start = start_date + datetime.timedelta(days=tt.day_offset)
        ProjectTask.objects.create(
            project=project,
            title=tt.title,
            description=tt.description,
            sequence=tt.sequence,
            estimated_hours=tt.estimated_hours,
            start_date=task_start,
            end_date=task_start + datetime.timedelta(days=max(0, tt.duration_days - 1)),
            company_id=company_id,
        )

    return project
