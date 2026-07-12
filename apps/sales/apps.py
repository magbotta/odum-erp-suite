from django.apps import AppConfig


class SalesConfig(AppConfig):
    name = "apps.sales"
    label = "sales"
    verbose_name = "Sales"
    entity_dir = "entities"
