from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.companies.models import Company
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService


class Command(BaseCommand):
    help = "Refresh authoritative Upstox instrument identity/classification only."

    def handle(self, *args, **options):
        try:
            eligible, suspended = CloudEODIngestionService().refresh_instrument_mapping()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        categories = {
            row["security_category"]: row["count"]
            for row in Company.objects.values("security_category").annotate(
                count=Count("id")
            )
        }
        self.stdout.write(self.style.SUCCESS(
            "INSTRUMENT_MASTER_REFRESH_SUCCESS "
            f"scanner_eligible={eligible} suspended={suspended} "
            f"category_counts={categories}"
        ))
