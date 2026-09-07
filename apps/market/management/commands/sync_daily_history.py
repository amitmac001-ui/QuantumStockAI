from django.core.management.base import BaseCommand, CommandError

from apps.market.services.daily_history_sync_service import DailyHistorySyncService


class Command(BaseCommand):
    help = "Incrementally sync real Upstox daily history into MarketOHLC."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--symbols", nargs="*", default=[])

    def handle(self, *args, **options):
        try:
            result = DailyHistorySyncService().sync(
                limit=max(int(options["limit"]), 0),
                symbols=options["symbols"],
            )
        except Exception as exc:
            raise CommandError(
                f"DAILY_HISTORY_SYNC_FAILED error={type(exc).__name__}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(
            "DAILY_HISTORY_SYNC_RESULT "
            f"latest_session={result.latest_session_date} "
            f"eligible={result.eligible_stocks} "
            f"already_current={result.already_current} "
            f"stocks_updated={result.stocks_updated} "
            f"candles_inserted={result.candles_inserted} "
            f"candles_updated={result.candles_updated} "
            f"failed={result.stocks_failed} "
            f"without_history={result.stocks_without_history} "
            f"remaining_stale={result.remaining_stale_stocks}"
        ))
