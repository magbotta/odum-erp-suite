from django.apps import AppConfig


class TelecomConfig(AppConfig):
    name = "apps.telecom"
    label = "telecom"
    verbose_name = "Telecommunications"
    entity_dir = "entities"
