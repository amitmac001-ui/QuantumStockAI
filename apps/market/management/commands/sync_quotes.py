import time

from django.core.management.base import BaseCommand

from apps.market.services.quote_sync import QuoteSyncService


class Command(BaseCommand):

    help = "Continuously Sync Quotes From Upstox"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one bounded provider sync and exit.",
        )

    def handle(self, *args, **options):

        interval = max(
            options["interval"],
            1,
        )

        instruments = QuoteSyncService.default_instruments()

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(instruments)} instruments."
            )
        )

        if not instruments:

            self.stdout.write(
                self.style.ERROR(
                    "No instrument keys found."
                )
            )

            return

        service = QuoteSyncService()

        self.stdout.write(
            self.style.SUCCESS(
                f"Quote Sync Started (Interval: {interval}s)"
            )
        )

        while True:

            try:

                result = service.sync(
                    instruments
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        "QUOTE_SYNC_RESULT "
                        f"requested={result.requested} "
                        f"updated={result.quotes_updated} "
                        f"coverage_pct={result.coverage * 100:.2f} "
                        f"batches={result.batches} "
                        f"batches_failed={result.batches_failed} "
                        f"skipped={result.skipped} "
                        f"failed_instruments={result.failed_instruments}"
                    )
                )

                if options["once"]:
                    break

            except KeyboardInterrupt:

                self.stdout.write(
                    self.style.WARNING(
                        "Quote Sync Stopped"
                    )
                )

                break

            except Exception as e:

                self.stderr.write(
                    self.style.ERROR(
                        str(e)
                    )
                )

            time.sleep(
                interval
            )
