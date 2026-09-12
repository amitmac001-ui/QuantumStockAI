from __future__ import annotations

import csv
from io import StringIO
from datetime import datetime
from pathlib import Path

import requests

from apps.companies.models import Company


class ListingDateRecoveryService:
    """Fill missing listing dates from the bundled official NSE equity master."""

    OFFICIAL_NSE_EQUITY_MASTER_URL = (
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    )

    @staticmethod
    def _date(value: str):
        value = str(value or "").strip().upper()
        return datetime.strptime(value, "%d-%b-%Y").date() if value else None

    @classmethod
    def recover(
        cls, csv_file: str | Path, *, source_url: str | None = None, http=None
    ) -> dict[str, int | str]:
        by_isin = {}
        by_symbol = {}
        source = "bundled_official_nse_master"
        if source_url:
            response = (http or requests).get(source_url, timeout=30)
            response.raise_for_status()
            handle = StringIO(response.content.decode("utf-8-sig"))
            source = source_url
        else:
            handle = Path(csv_file).open("r", encoding="utf-8-sig", newline="")
        with handle:
            for row in csv.DictReader(handle, skipinitialspace=True):
                if str(row.get("SERIES") or "").strip().upper() != "EQ":
                    continue
                listing_date = cls._date(row.get("DATE OF LISTING"))
                if listing_date is None:
                    continue
                isin = str(row.get("ISIN NUMBER") or "").strip().upper()
                symbol = str(row.get("SYMBOL") or "").strip().upper()
                if isin:
                    by_isin[isin] = listing_date
                if symbol:
                    by_symbol[symbol] = (isin, listing_date)

        candidates = list(
            Company.scanner_eligible()
            .filter(listing_date__isnull=True)
            .only("id", "symbol", "isin", "listing_date")
        )
        updates = []
        matched_by_isin = 0
        matched_by_symbol = 0
        for company in candidates:
            isin = str(company.isin or "").strip().upper()
            symbol = str(company.symbol or "").strip().upper()
            listing_date = by_isin.get(isin) if isin else None
            if listing_date is not None:
                matched_by_isin += 1
            else:
                symbol_match = by_symbol.get(symbol)
                # A symbol fallback is accepted only when the master has no
                # conflicting ISIN. This avoids attaching a predecessor's date.
                if symbol_match and (
                    not isin or not symbol_match[0] or symbol_match[0] == isin
                ):
                    listing_date = symbol_match[1]
                    matched_by_symbol += 1
            if listing_date is not None:
                company.listing_date = listing_date
                updates.append(company)

        if updates:
            Company.objects.bulk_update(updates, ["listing_date"], batch_size=1_000)
        return {
            "source": source,
            "missing_before": len(candidates),
            "recovered": len(updates),
            "matched_by_isin": matched_by_isin,
            "matched_by_symbol": matched_by_symbol,
            "unresolved": len(candidates) - len(updates),
        }
