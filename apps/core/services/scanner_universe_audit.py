from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from django.db.models import Count, Max

from apps.companies.models import Company
from apps.core.services.scanner_data_readiness import ScannerDataReadinessService
from apps.market.models import CloudDailyCandle, CloudQuoteSnapshot


class ScannerUniverseAuditService:
    """Aggregate-only, read-only diagnostics for the persisted scanner universe."""

    # These are the only instrument types the cloud importer explicitly prioritizes.
    IMPORTER_RECOGNIZED_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ", "SM", "ST"})
    INDIAN_ISIN_FORMAT = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")

    @staticmethod
    def _group_counts(queryset, field: str, *, blank_label: str = "<blank>") -> dict[str, int]:
        rows = queryset.values(field).annotate(count=Count("id")).order_by(field)
        return {
            str(row[field] or blank_label): int(row["count"])
            for row in rows
        }

    @staticmethod
    def _duplicate_counts(queryset, field: str) -> dict[str, int]:
        counts = list(
            queryset.values(field)
            .annotate(row_count=Count("id"))
            .filter(row_count__gt=1)
            .values_list("row_count", flat=True)
        )
        return {
            "groups": len(counts),
            "rows": int(sum(counts)),
            "excess_rows": int(sum(count - 1 for count in counts)),
        }

    @staticmethod
    def _instrument_key_prefixes(keys: Iterable[str]) -> dict[str, int]:
        prefixes: Counter[str] = Counter()
        for raw_key in keys:
            key = str(raw_key or "").strip()
            if not key:
                prefixes["<blank>"] += 1
            elif "|" not in key:
                prefixes["<no-segment-prefix>"] += 1
            else:
                prefixes[key.split("|", 1)[0].upper()] += 1
        return dict(sorted(prefixes.items()))

    @classmethod
    def _is_checksum_valid_isin(cls, raw_isin: str) -> bool:
        isin = str(raw_isin or "").strip().upper()
        if not cls.INDIAN_ISIN_FORMAT.fullmatch(isin):
            return False
        expanded = "".join(
            str(ord(character) - 55) if character.isalpha() else character
            for character in isin
        )
        total = 0
        parity = len(expanded) % 2
        for index, character in enumerate(expanded):
            digit = int(character)
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0

    @classmethod
    def _isin_counts(cls, values: Iterable[str]) -> dict[str, int]:
        normalized = [str(value or "").strip().upper() for value in values]
        nonblank = [value for value in normalized if value]
        format_valid = [
            value for value in nonblank if cls.INDIAN_ISIN_FORMAT.fullmatch(value)
        ]
        return {
            "nonblank_rows": len(nonblank),
            "distinct_nonblank": len(set(nonblank)),
            "indian_format_valid_rows": len(format_valid),
            "indian_checksum_valid_rows": sum(
                cls._is_checksum_valid_isin(value) for value in format_valid
            ),
        }

    @classmethod
    def collect(cls) -> dict[str, Any]:
        companies = Company.objects.all()
        eligible = ScannerDataReadinessService.eligible_companies()
        eligible_count = eligible.values("id").distinct().count()

        all_keys = list(companies.values_list("upstox_instrument_key", flat=True))
        eligible_keys = list(eligible.values_list("upstox_instrument_key", flat=True))
        all_isins = list(companies.values_list("isin", flat=True))
        eligible_isins = list(eligible.values_list("isin", flat=True))

        nonblank_keys = companies.exclude(upstox_instrument_key="")
        duplicate_keys = cls._duplicate_counts(
            nonblank_keys, "upstox_instrument_key"
        )
        duplicate_symbols = cls._duplicate_counts(companies, "symbol")

        stock_intersection = eligible.filter(
            cloud_daily_candles__isnull=False
        ).values("id").distinct()
        quote_intersection = eligible.filter(
            cloud_quote_snapshot__isnull=False
        ).values("id").distinct()
        stock_no_quote = eligible.filter(
            cloud_daily_candles__isnull=False,
            cloud_quote_snapshot__isnull=True,
        ).values("id").distinct()
        quote_no_stock = eligible.filter(
            cloud_quote_snapshot__isnull=False,
            cloud_daily_candles__isnull=True,
        ).values("id").distinct()

        latest_stock_session = CloudDailyCandle.objects.aggregate(
            latest=Max("session_date")
        )["latest"]
        latest_session_stock_count = (
            CloudDailyCandle.objects.filter(
                company__in=eligible,
                session_date=latest_stock_session,
            ).values("company_id").distinct().count()
            if latest_stock_session else 0
        )

        eligible_series_counts = cls._group_counts(eligible, "series")
        recognized_series_count = sum(
            count for series, count in eligible_series_counts.items()
            if series in cls.IMPORTER_RECOGNIZED_EQUITY_SERIES
        )
        unclassified_series_count = eligible_count - recognized_series_count

        return {
            "company_rows": {
                "total": companies.count(),
                "active": companies.filter(is_active=True).count(),
                "inactive": companies.filter(is_active=False).count(),
            },
            "instrument_status_counts": cls._group_counts(
                companies, "instrument_status"
            ),
            "exchange_counts": cls._group_counts(companies, "exchange"),
            "persisted_series_counts": cls._group_counts(companies, "series"),
            "eligible_series_counts": eligible_series_counts,
            "identity_counts": {
                "distinct_symbols": companies.values("symbol").distinct().count(),
                "distinct_nonblank_instrument_keys": (
                    nonblank_keys.values("upstox_instrument_key").distinct().count()
                ),
                "duplicate_symbols": duplicate_symbols,
                "duplicate_instrument_keys": duplicate_keys,
            },
            "isin_counts": {
                "all_companies": cls._isin_counts(all_isins),
                "eligible_companies": cls._isin_counts(eligible_isins),
            },
            "current_eligibility": {
                "rule": (
                    "exchange=NSE,is_active=true,instrument_status=active,"
                    "instrument_key_not_empty"
                ),
                "company_rows_matching_rule": eligible_count,
                "distinct_symbols_matching_rule": (
                    eligible.values("symbol").distinct().count()
                ),
                "distinct_instrument_keys_matching_rule": (
                    eligible.values("upstox_instrument_key").distinct().count()
                ),
                "company_rows_with_nse_eq_key": eligible.filter(
                    upstox_instrument_key__startswith="NSE_EQ|"
                ).values("id").distinct().count(),
                "company_rows_with_non_nse_eq_key": eligible.exclude(
                    upstox_instrument_key__startswith="NSE_EQ|"
                ).values("id").distinct().count(),
                "recognized_importer_equity_series": recognized_series_count,
                "unclassified_by_recognized_series": unclassified_series_count,
            },
            "instrument_key_prefix_counts": {
                "all_companies": cls._instrument_key_prefixes(all_keys),
                "eligible_companies": cls._instrument_key_prefixes(eligible_keys),
            },
            "persisted_market_data": {
                "distinct_stock_instruments_all_sessions": (
                    CloudDailyCandle.objects.values("company_id").distinct().count()
                ),
                "distinct_quote_instruments": (
                    CloudQuoteSnapshot.objects.values("company_id").distinct().count()
                ),
                "stock_data_intersection_with_eligible": stock_intersection.count(),
                "quote_data_intersection_with_eligible": quote_intersection.count(),
                "eligible_stock_without_quote": stock_no_quote.count(),
                "eligible_quote_without_stock": quote_no_stock.count(),
                "eligible_with_neither_stock_nor_quote": eligible.exclude(
                    id__in=stock_intersection
                ).exclude(id__in=quote_intersection).values("id").distinct().count(),
                "latest_stock_session": (
                    latest_stock_session.isoformat() if latest_stock_session else None
                ),
                "eligible_stock_instruments_on_latest_session": (
                    latest_session_stock_count
                ),
            },
            "classification_evidence": {
                "persisted_exchange": True,
                "persisted_series": True,
                "persisted_source_segment": False,
                "persisted_dedicated_instrument_type": False,
                "persisted_security_category": False,
                "schema_can_prove_company_equity_universe": False,
                "blocker": (
                    "Company.series is populated from NSE CSV SERIES or Upstox "
                    "instrument_type; source segment and a dedicated security "
                    "category are not persisted. Exact company-equity classification "
                    "cannot be reconstructed safely from stored fields alone."
                ),
            },
        }
