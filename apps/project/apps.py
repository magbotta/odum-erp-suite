from django.apps import AppConfig


class ProjectConfig(AppConfig):
    name = "apps.project"
    label = "project"
    verbose_name = "Project Management"
    entity_dir = "entities"
