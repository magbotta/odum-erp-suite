from django.apps import AppConfig


class GovernmentConfig(AppConfig):
    name = "apps.government"
    label = "government"
    verbose_name = "Government"
    entity_dir = "entities"
