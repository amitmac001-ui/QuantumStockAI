from django.core.management.base import BaseCommand, CommandError

from apps.companies.models import Company
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService


class Command(BaseCommand):
    help = "Refresh genuine Upstox quotes for the active NSE EQ scanner universe."

    def handle(self, *args, **options):
        service = CloudEODIngestionService()
        try:
            quote_result = service.sync_quotes()
            updated = int(quote_result.get("equities_updated", 0))
            eligible = Company.scanner_eligible().values("id").distinct().count()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        coverage = (updated / eligible * 100.0) if eligible else 0.0
        if eligible == 0 or coverage < 95.0:
            failures = quote_result.get("failures") or []
            diagnostic = f" failures={'; '.join(failures[:3])}" if failures else ""
            raise CommandError(
                f"SCANNER_QUOTE_REFRESH_INCOMPLETE eligible={eligible} "
                f"updated={updated} coverage_pct={coverage:.2f}"
                f" batches_failed={quote_result.get('batches_failed', 0)}"
                f" skipped={quote_result.get('skipped', 0)}{diagnostic}"
            )
        self.stdout.write(self.style.SUCCESS(
            f"SCANNER_QUOTE_REFRESH_SUCCESS eligible={eligible} "
            f"updated={updated} coverage_pct={coverage:.2f}"
        ))
