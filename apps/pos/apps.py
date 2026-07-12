from django.apps import AppConfig


class POSConfig(AppConfig):
    name = "apps.pos"
    label = "pos"
    verbose_name = "Point of Sale"
    entity_dir = "entities"
