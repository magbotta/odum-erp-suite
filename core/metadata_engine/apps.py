from django.apps import AppConfig


class MetadataEngineConfig(AppConfig):
    name = "core.metadata_engine"
    label = "odum_metadata"
    verbose_name = "Odum Metadata Engine"

    def ready(self):
        from pathlib import Path
        from django.apps import apps as django_apps
        from .parser import scan_directory, scan_entity_dirs
        from django.conf import settings

        # 1. Auto-discover entity dirs declared on each AppConfig
        for app_config in django_apps.get_app_configs():
            entity_dir = getattr(app_config, "entity_dir", None)
            if entity_dir:
                path = Path(app_config.path) / entity_dir
                scan_directory(path)

        # 2. Scan any additional dirs from settings
        scan_entity_dirs(getattr(settings, "ODUM_ENTITY_SCAN_DIRS", []))
