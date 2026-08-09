from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.scanner.services.cloud_outcome_cycle_service import CloudOutcomeCycleService


class Command(BaseCommand):
    help = "Fetch legitimate forward candles and evaluate persisted outcome snapshots"

    def add_arguments(self, parser):
        parser.add_argument("--allow-sqlite", action="store_true", help="Tests/local verification only")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql" and not options["allow_sqlite"]:
            raise CommandError("Cloud outcome cycle requires DATABASE_URL/PostgreSQL.")
        result = CloudOutcomeCycleService().run()
        self.stdout.write(
            "CLOUD_OUTCOME_CYCLE " + json.dumps(result.as_mapping(), sort_keys=True)
        )
