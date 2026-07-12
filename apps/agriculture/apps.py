from django.apps import AppConfig


class AgricultureConfig(AppConfig):
    name = "apps.agriculture"
    label = "agriculture"
    verbose_name = "Agriculture Management"
    entity_dir = "entities"
