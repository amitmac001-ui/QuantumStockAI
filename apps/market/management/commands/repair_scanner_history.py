from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.companies.services.listing_date_recovery import ListingDateRecoveryService
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService


class Command(BaseCommand):
    help = "Backfill real Upstox daily history for scanner instruments with gaps"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Scanner-history repair requires DATABASE_URL/PostgreSQL.")
        limit = options["limit"]
        if not 1 <= limit <= 500:
            raise CommandError("--limit must be between 1 and 500.")
        service = CloudEODIngestionService()
        service._ensure_provider_clients()
        listing_dates = ListingDateRecoveryService.recover(
            settings.BASE_DIR / "data" / "EQUITY_L.csv"
        )
        latest_session = service.resolve_latest_session()
        benchmark_rows = service.sync_benchmark(latest_session)
        result = service.sync_stock_history(
            latest_session, limit=limit, include_insufficient=True
        )
        if (
            result["attempted"]
            and result["updated"] == 0
            and result["empty"] + result["failed"] == result["attempted"]
        ):
            raise CommandError(
                "Upstox returned no usable history for the entire repair batch."
            )
        self.stdout.write("SCANNER_HISTORY_REPAIR " + json.dumps({
            "latest_session": latest_session.isoformat(),
            "benchmark_rows": benchmark_rows,
            "listing_dates": listing_dates,
            **result,
        }, sort_keys=True))
