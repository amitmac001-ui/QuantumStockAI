import time

from django.core.management.base import BaseCommand

from apps.companies.models import Company
from apps.market.services.quote_sync import QuoteSyncService


class Command(BaseCommand):

    help = "Continuously Sync Quotes From Upstox"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
        )

    def handle(self, *args, **options):

        interval = max(
            options["interval"],
            1,
        )

        instruments = list(
            Company.objects.filter(
                is_active=True,
                exchange="NSE",
            )
            .exclude(
                upstox_instrument_key="",
            )
            .values_list(
                "upstox_instrument_key",
                flat=True,
            )
        )

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

                total = service.sync(
                    instruments
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{total} Quotes Updated"
                    )
                )

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
