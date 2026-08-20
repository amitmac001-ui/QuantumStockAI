from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.services.live_sync_runtime import live_sync_lock
from apps.core.services.workbook_scanner_publisher import (
    WorkbookScannerPublisher,
    WorkbookScannerReportSet,
)
from apps.scanner.services.live_scan_overlay_service import LiveScanOverlayService
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class Command(BaseCommand):
    help = (
        "Project the persisted scanner cache into the exact workbook schemas. "
        "Dry-run never constructs Google credentials or a Sheets client."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--write", action="store_true")

    def handle(self, *args, **options):
        started = perf_counter()
        try:
            with live_sync_lock():
                reports, context = ScanReportCacheService().load_valid()
                # Persisted quote fields may move; structural scores and report order stay frozen.
                overlaid = LiveScanOverlayService.overlay_reports(reports)
                report_set = WorkbookScannerReportSet.build(overlaid)
                session = context.get("scanner_session")
                generated_at = context.get("cache_generated_at")
                if options["dry_run"]:
                    self.stdout.write(self.style.SUCCESS(
                        "TECHNICAL_SCANNER_WORKBOOK_DRY_RUN_SUCCESS "
                        f"rows={len(report_set.technical_rows)} columns=50 "
                        f"unavailable={report_set.unavailable_count(report_set.technical_rows)} "
                        f"session={session} freshness={report_set.freshness()} "
                        f"cache_generated_at={generated_at}"
                    ))
                    self.stdout.write(self.style.SUCCESS(
                        "SWING_PREBREAKOUT_DRY_RUN_SUCCESS "
                        f"rows={len(report_set.swing_rows)} columns=40 "
                        f"unavailable={report_set.unavailable_count(report_set.swing_rows)} "
                        f"session={session} freshness={report_set.freshness()} "
                        f"cache_generated_at={generated_at}"
                    ))
                    self.stdout.write(self.style.SUCCESS(
                        "WORKBOOK_SCANNERS_DRY_RUN_SUCCESS provider_calls=0 sheet_writes=0 "
                        f"duration_ms={int((perf_counter() - started) * 1000)}"
                    ))
                    return
                if not settings.GOOGLE_SHEETS_ENABLED:
                    raise CommandError("GOOGLE_SHEETS_ENABLED is false.")
                result = WorkbookScannerPublisher().publish(report_set)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            "WORKBOOK_SCANNERS_PUBLISH_SUCCESS "
            f"technical_rows={result.technical.rows} swing_rows={result.swing.rows} "
            f"session={session} freshness={report_set.freshness()} "
            f"duration_ms={result.duration_ms} run_id={result.run_id}"
        ))
