from django.apps import AppConfig


class AssetManagementConfig(AppConfig):
    name = "apps.asset_management"
    label = "asset_management"
    verbose_name = "Asset Management"
    entity_dir = "entities"
