from django.apps import AppConfig


class CRMConfig(AppConfig):
    name = "apps.crm"
    label = "crm"
    verbose_name = "CRM"
    entity_dir = "entities"
