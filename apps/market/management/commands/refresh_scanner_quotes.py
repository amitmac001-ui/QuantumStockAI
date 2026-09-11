from django.core.management.base import BaseCommand, CommandError

from apps.companies.models import Company
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService


class Command(BaseCommand):
    help = "Refresh genuine Upstox quotes for the active NSE EQ scanner universe."

    def handle(self, *args, **options):
        service = CloudEODIngestionService()
        try:
            quote_result = service.sync_quotes()
            updated = int(quote_result.get("updated", 0))
            eligible = Company.objects.filter(
                exchange="NSE",
                series="EQ",
                is_active=True,
                instrument_status=Company.InstrumentStatus.ACTIVE,
            ).exclude(upstox_instrument_key="").count()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        coverage = (updated / eligible * 100.0) if eligible else 0.0
        if eligible == 0 or coverage < 95.0:
            raise CommandError(
                f"SCANNER_QUOTE_REFRESH_INCOMPLETE eligible={eligible} "
                f"updated={updated} coverage_pct={coverage:.2f}"
            )
        self.stdout.write(self.style.SUCCESS(
            f"SCANNER_QUOTE_REFRESH_SUCCESS eligible={eligible} "
            f"updated={updated} coverage_pct={coverage:.2f}"
        ))
