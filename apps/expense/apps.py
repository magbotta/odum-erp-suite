from django.apps import AppConfig


class ExpenseConfig(AppConfig):
    name = "apps.expense"
    label = "expense"
    verbose_name = "Expense & Travel"
    entity_dir = "entities"
