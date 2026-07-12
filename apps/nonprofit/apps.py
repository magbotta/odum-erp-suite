from django.apps import AppConfig


class NonprofitConfig(AppConfig):
    name = "apps.nonprofit"
    label = "nonprofit"
    verbose_name = "Nonprofit Management"
    entity_dir = "entities"
