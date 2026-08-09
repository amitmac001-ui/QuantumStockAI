from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.scanner.services.cloud_snapshot_cycle_service import CloudSnapshotCycleService


class Command(BaseCommand):
    help = "Run incremental compact EOD ingest, snapshot capture, and outcome evaluation"

    def add_arguments(self, parser):
        parser.add_argument("--history-limit", type=int, default=500)
        parser.add_argument("--allow-sqlite", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql" and not options["allow_sqlite"]:
            raise CommandError("Cloud snapshot cycle requires DATABASE_URL/PostgreSQL.")
        result = CloudSnapshotCycleService().run(history_limit=options["history_limit"])
        self.stdout.write(
            "CLOUD_SNAPSHOT_CYCLE " + json.dumps(result.as_mapping(), sort_keys=True)
        )