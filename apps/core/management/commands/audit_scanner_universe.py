import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.services.scanner_universe_audit import ScannerUniverseAuditService


class Command(BaseCommand):
    help = "Report aggregate-only, read-only scanner-universe diagnostics."

    def handle(self, *args, **options):
        try:
            connection.ensure_connection()
            audit = ScannerUniverseAuditService.collect()
        except Exception as exc:
            raise CommandError(f"Scanner universe audit failed: {exc}") from exc

        payload = json.dumps(audit, sort_keys=True, separators=(",", ":"))
        self.stdout.write(
            f"SCANNER_UNIVERSE_AUDIT database={connection.vendor} payload={payload}"
        )
