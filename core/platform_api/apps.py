from django.apps import AppConfig


class PlatformAPIConfig(AppConfig):
    name = "core.platform_api"
    label = "ochre_platform_api"
    verbose_name = "Ochre Platform API"

    def ready(self):
        # Wire entity routers after all apps and entity definitions are loaded
        from .api import api
        from core.metadata_engine.api_factory import register_all_entity_routers
        register_all_entity_routers(api)
