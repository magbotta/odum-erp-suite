from django.apps import AppConfig


class PaymentsGatewayConfig(AppConfig):
    name = "core.payments_gateway"
    label = "odum_payments_gateway"
    verbose_name = "Odum Payments Gateway"

    def ready(self) -> None:
        # Register all built-in drivers into the global registry.
        # Import inside ready() to avoid circular imports at module load time.
        from core.payments_gateway.drivers.mobile_money import register_all as reg_mm
        from core.payments_gateway.drivers.cash_teller import register_all as reg_cash

        reg_mm()
        reg_cash()
