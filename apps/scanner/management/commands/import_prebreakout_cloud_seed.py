from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.scanner.services.cloud_outcome_seed_service import (
    CloudOutcomeSeedError,
    CloudOutcomeSeedService,
)


class Command(BaseCommand):
    help = "Idempotently import a checksum-protected outcome seed into PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--allow-sqlite", action="store_true", help="Tests/local verification only")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql" and not options["allow_sqlite"]:
            raise CommandError("Outcome seed import requires DATABASE_URL/PostgreSQL.")
        try:
            result = CloudOutcomeSeedService.import_from(Path(options["input"]))
        except (OSError, KeyError, TypeError, CloudOutcomeSeedError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            "OUTCOME_SEED_IMPORTED "
            + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
        ))
