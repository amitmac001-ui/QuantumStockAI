import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.companies.models import Company


class Command(BaseCommand):
    help = "Import NSE Company Master CSV"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to NSE Company Master CSV",
        )

    @transaction.atomic
    def handle(self, *args, **options):

        csv_file = Path(options["csv_file"])

        if not csv_file.exists():
            raise CommandError(
                f"File not found: {csv_file}"
            )

        created = 0
        updated = 0
        skipped = 0

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("QuantumStock AI - NSE Company Import")
        self.stdout.write("=" * 60)
        self.stdout.write("")

        with open(
            csv_file,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(
                file,
                skipinitialspace=True,
            )

            for row in reader:

                symbol = (
                    row.get("SYMBOL")
                    or ""
                ).strip().upper()

                if not symbol:
                    skipped += 1
                    continue

                name = (
                    row.get("NAME OF COMPANY")
                    or symbol
                ).strip()

                isin = (
                    row.get("ISIN NUMBER")
                    or ""
                ).strip().upper()

                series = (
                    row.get("SERIES")
                    or ""
                ).strip().upper()

                sector = (
                    row.get("SECTOR")
                    or ""
                ).strip()

                industry = (
                    row.get("INDUSTRY")
                    or ""
                ).strip()

                face_value = (
                    row.get("FACE VALUE")
                    or None
                )

                instrument_key = (
                    f"NSE_EQ|{isin}"
                    if isin
                    else ""
                )

                _, created_flag = Company.objects.update_or_create(
                    symbol=symbol,
                    defaults={
                        "name": name,
                        "exchange": "NSE",
                        "isin": isin,
                        "upstox_instrument_key": instrument_key,
                        "series": series,
                        "sector": sector,
                        "industry": industry,
                        "face_value": face_value,
                        "is_active": True,
                    },
                )

                if created_flag:
                    created += 1
                else:
                    updated += 1

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(
            self.style.SUCCESS(
                "Import Completed Successfully"
            )
        )
        self.stdout.write("=" * 60)
        self.stdout.write(f"Created : {created}")
        self.stdout.write(f"Updated : {updated}")
        self.stdout.write(f"Skipped : {skipped}")
        self.stdout.write("=" * 60)
