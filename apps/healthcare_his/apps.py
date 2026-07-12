from django.apps import AppConfig


class HealthcareHISConfig(AppConfig):
    name = "apps.healthcare_his"
    label = "healthcare_his"
    verbose_name = "Healthcare / Hospital Information System"
    entity_dir = "entities"
