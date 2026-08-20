from django.core.management.base import BaseCommand, CommandError

from apps.scanner.services.scan_report_cache_service import ScanReportCacheService
from apps.scanner.services.scanner_service import ScannerService


class Command(BaseCommand):
    help = "Build an atomic Technical Scanner cache from persisted market data only."

    def handle(self, *args, **options):
        cache = ScanReportCacheService()
        try:
            session = cache.latest_aligned_session()
            reports = ScannerService.scan_live_market()
            current = [
                report for report in reports
                if report.snapshot.latest_daily_session is not None
                and cache._session(report.snapshot.latest_daily_session) == session
            ]
            cache.save(
                current,
                session=session,
                session_context={
                    "scanner_session": session.isoformat(),
                    "reports": len(current),
                    "source": "build_technical_scan_cache",
                },
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"TECHNICAL_SCAN_CACHE_SUCCESS reports={len(current)} session={session}"
        ))
