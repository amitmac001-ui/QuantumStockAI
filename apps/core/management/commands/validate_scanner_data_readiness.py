from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.services.scanner_data_readiness import (
    ScannerDataReadinessService,
)


class Command(BaseCommand):
    help = "Validate persisted database and aligned scanner-session readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-cache",
            action="store_true",
            help="Also require the generated scan cache to cover the eligible universe.",
        )

    def handle(self, *args, **options):
        try:
            connection.ensure_connection()
            snapshot = ScannerDataReadinessService.collect(
                check_cache=options["check_cache"]
            )
        except Exception as exc:
            raise CommandError(f"Scanner data readiness failed: {exc}") from exc
        fields = ScannerDataReadinessService.diagnostic_fields(snapshot)
        self.stdout.write(f"SCANNER_DATA_DIAGNOSTIC database={connection.vendor} {fields}")
        failures = ScannerDataReadinessService.failures(snapshot)
        if failures:
            raise CommandError(
                "SCANNER_DATA_NOT_READY reasons=" + ",".join(failures)
            )
        self.stdout.write(self.style.SUCCESS(
            f"SCANNER_DATA_READY database={connection.vendor} {fields}"
        ))
