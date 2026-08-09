from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.scanner.services.cloud_outcome_seed_service import (
    CloudOutcomeSeedError,
    CloudOutcomeSeedService,
)


class Command(BaseCommand):
    help = "Export only outcome snapshots and required instrument keys"

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            result = CloudOutcomeSeedService.export_to(Path(options["output"]))
        except (OSError, CloudOutcomeSeedError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"OUTCOME_SEED_EXPORTED companies={result['companies']} "
            f"outcomes={result['outcomes']}"
        ))
