from django.apps import AppConfig


class WarehouseConfig(AppConfig):
    name = "apps.warehouse"
    label = "warehouse"
    verbose_name = "Warehouse & Inventory"
    entity_dir = "entities"
