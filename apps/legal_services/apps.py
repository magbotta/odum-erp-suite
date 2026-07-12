from django.apps import AppConfig


class LegalServicesConfig(AppConfig):
    name = "apps.legal_services"
    label = "legal_services"
    verbose_name = "Legal Services"
    entity_dir = "entities"
