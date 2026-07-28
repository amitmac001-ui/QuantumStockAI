from django.apps import AppConfig


class ScannerConfig(AppConfig):

    default_auto_field = "django.db.models.BigAutoField"

    name = "apps.scanner"

    def ready(self):

        from apps.scanner.engine.discovery import discover
        from apps.scanner.engine.registry import StrategyRegistry

        StrategyRegistry.clear()
        discover()
