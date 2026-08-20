from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.market.models import (
    CloudDailyCandle,
    CloudQuoteSnapshot,
    MarketOHLC,
    MarketQuote,
)
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class Command(BaseCommand):
    help = "Validate persisted database and aligned scanner-session readiness."

    def handle(self, *args, **options):
        try:
            connection.ensure_connection()
            session = ScanReportCacheService.latest_aligned_session()
            if settings.CLOUD_COMPACT_MARKET_DATA:
                stock_rows = CloudDailyCandle.objects.filter(session_date=session).count()
                quote_rows = CloudQuoteSnapshot.objects.count()
                mode = "cloud_compact"
            else:
                stock_rows = MarketOHLC.objects.filter(
                    interval=MarketOHLC.Interval.D1,
                    candle_time__date=session,
                ).count()
                quote_rows = MarketQuote.objects.count()
                mode = "standard"
            if stock_rows <= 0:
                raise CommandError("No persisted stock rows exist for the aligned session.")
            if quote_rows <= 0:
                raise CommandError("No persisted quote snapshots are available.")
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Scanner data readiness failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            "SCANNER_DATA_READY "
            f"database={connection.vendor} mode={mode} session={session.isoformat()} "
            f"stock_rows={stock_rows} quote_rows={quote_rows}"
        ))
