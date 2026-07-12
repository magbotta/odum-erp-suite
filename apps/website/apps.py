from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    name = "apps.website"
    label = "website"
    verbose_name = "Website / CMS"
    entity_dir = "entities"
