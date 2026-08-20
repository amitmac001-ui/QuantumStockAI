from __future__ import annotations

import time
from datetime import time as clock_time
from time import perf_counter
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.services.live_sync_runtime import live_sync_lock
from apps.core.services.technical_scanner_publisher import (
    TechnicalScannerProjectionBuilder,
    TechnicalScannerPublisher,
)
from apps.scanner.services.live_scan_overlay_service import LiveScanOverlayService
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class Command(BaseCommand):
    help = "Continuously publish provider-free cached Technical Scanner snapshots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval", type=int,
            default=settings.TECHNICAL_SCANNER_PUBLISH_INTERVAL_SECONDS,
        )
        parser.add_argument("--closed-interval", type=int, default=300)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if not settings.GOOGLE_SHEETS_ENABLED:
            raise CommandError("GOOGLE_SHEETS_ENABLED is false.")
        interval = max(10, min(int(options["interval"]), 30))
        closed_interval = max(60, int(options["closed_interval"]))
        publisher = TechnicalScannerPublisher()
        while True:
            cycle_started = perf_counter()
            market_open = False
            failure = None
            try:
                with live_sync_lock():
                    reports, _context = ScanReportCacheService().load_valid()
                    overlaid = LiveScanOverlayService.overlay_reports(reports)
                    rows = TechnicalScannerProjectionBuilder.rows(overlaid)
                    publisher.publish(overlaid)
                local_now = timezone.now().astimezone(ZoneInfo("Asia/Kolkata"))
                market_window = (
                    local_now.weekday() < 5
                    and clock_time(9, 15) <= local_now.time() <= clock_time(15, 30)
                )
                market_open = market_window and any(row[9] == "OK" for row in rows)
            except Exception as exc:
                failure = exc
                self.stderr.write(f"TECHNICAL_SCANNER_CYCLE_FAILED {exc}")
            if options["once"]:
                if failure is not None:
                    raise CommandError(str(failure)) from failure
                return
            target = interval if market_open else closed_interval
            time.sleep(max(0.0, target - (perf_counter() - cycle_started)))
