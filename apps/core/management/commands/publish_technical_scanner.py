from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.services.live_sync_runtime import live_sync_lock
from apps.core.services.technical_scanner_publisher import (
    TechnicalScannerProjectionBuilder,
    TechnicalScannerPublisher,
)
from apps.scanner.services.live_scan_overlay_service import LiveScanOverlayService
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class Command(BaseCommand):
    help = "Publish latest aligned cached reports; never calls market-data providers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        started = perf_counter()
        try:
            with live_sync_lock():
                reports, context = ScanReportCacheService().load_valid()
                overlaid = LiveScanOverlayService.overlay_reports(reports)
                if options["dry_run"]:
                    rows = TechnicalScannerProjectionBuilder.rows(overlaid)
                    self.stdout.write(self.style.SUCCESS(
                        "TECHNICAL_SCANNER_DRY_RUN_SUCCESS "
                        f"rows={len(rows)} "
                        f"columns={len(TechnicalScannerProjectionBuilder.HEADERS)} "
                        f"session={context.get('scanner_session')} "
                        f"duration_ms={int((perf_counter() - started) * 1000)}"
                    ))
                    return
                if not settings.GOOGLE_SHEETS_ENABLED:
                    raise CommandError("GOOGLE_SHEETS_ENABLED is false.")
                result = TechnicalScannerPublisher().publish(overlaid)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            "TECHNICAL_SCANNER_PUBLISH_SUCCESS "
            f"rows={result.rows} columns={result.columns} chunks={result.chunks} "
            f"session={context.get('scanner_session')} duration_ms={result.duration_ms}"
        ))
