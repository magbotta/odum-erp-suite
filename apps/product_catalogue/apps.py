from django.apps import AppConfig


class ProductCatalogueConfig(AppConfig):
    name = "apps.product_catalogue"
    label = "product_catalogue"
    verbose_name = "Product Catalogue"
    entity_dir = "entities"
