from __future__ import annotations

import gzip
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import requests
from django.db import connection, transaction
from django.db.models import Max

from apps.companies.models import Company
from apps.market.models import (
    CloudBenchmarkCandle,
    CloudDailyCandle,
    CloudQuoteSnapshot,
)
from apps.market.providers.historical_client import HistoricalClient
from apps.market.providers.upstox_client import UpstoxClient
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.market.services.quote_sync import QuoteSyncService


@dataclass(slots=True)
class CloudEODIngestionResult:
    latest_session: date | None = None
    active_instruments: int = 0
    suspended_instruments: int = 0
    history_attempted: int = 0
    history_current: int = 0
    history_updated: int = 0
    candle_rows_created: int = 0
    candle_rows_updated: int = 0
    provider_empty: int = 0
    provider_failed: int = 0
    benchmark_rows: int = 0
    quotes_updated: int = 0
    candles_pruned: int = 0
    benchmark_pruned: int = 0
    failures: list[str] = field(default_factory=list)

    def as_mapping(self):
        data = asdict(self)
        data["latest_session"] = self.latest_session.isoformat() if self.latest_session else None
        return data


class CloudEODIngestionService:
    NSE_INSTRUMENTS_URL = (
        "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    )
    SUSPENDED_INSTRUMENTS_URL = (
        "https://assets.upstox.com/market-quote/instruments/exchange/"
        "suspended-instrument.json.gz"
    )
    STOCK_RETENTION_SESSIONS = 272
    BENCHMARK_RETENTION_SESSIONS = 300
    INITIAL_CALENDAR_DAYS = 430
    HISTORY_BATCH_LIMIT = 500
    QUOTE_BATCH_SIZE = 200
    WRITE_BATCH_SIZE = 5_000
    REQUEST_INTERVAL_SECONDS = 0.25

    def __init__(self, *, historical=None, quotes=None, http=None, now=None, sleep=None):
        self.historical = historical or HistoricalClient()
        self.quotes = quotes or UpstoxClient()
        self.http = http or requests.Session()
        self.sleep = sleep or time.sleep
        self.history = DailyHistorySyncService(
            self.historical, now=now, sleep=self.sleep,
            request_interval_seconds=self.REQUEST_INTERVAL_SECONDS,
        )

    def _download_json_gzip(self, url: str) -> list[dict[str, Any]]:
        response = self.http.get(url, timeout=60)
        response.raise_for_status()
        return json.loads(gzip.decompress(response.content).decode("utf-8"))

    @transaction.atomic
    def refresh_instrument_mapping(self) -> tuple[int, int]:
        active_rows = self._download_json_gzip(self.NSE_INSTRUMENTS_URL)
        suspended_rows = self._download_json_gzip(self.SUSPENDED_INSTRUMENTS_URL)
        priorities = {"EQ": 0, "BE": 1, "BZ": 2, "SM": 3, "ST": 4}
        selected: dict[str, dict[str, Any]] = {}
        for row in active_rows:
            if row.get("segment") != "NSE_EQ":
                continue
            symbol = str(row.get("trading_symbol") or "").strip().upper()
            isin = str(row.get("isin") or "").strip().upper()
            instrument_key = str(row.get("instrument_key") or "").strip()
            instrument_type = str(row.get("instrument_type") or "").strip().upper()
            if not symbol or not isin or not instrument_key:
                continue
            current = selected.get(symbol)
            if current is None or priorities.get(instrument_type, 99) < priorities.get(
                str(current.get("instrument_type") or "").upper(), 99
            ):
                selected[symbol] = row

        if len(selected) < 1_000:
            raise RuntimeError("Upstox NSE instrument master is unexpectedly incomplete.")

        existing = {
            company.symbol: company
            for company in Company.objects.filter(symbol__in=selected).iterator(chunk_size=2_000)
        }
        creates, updates = [], []
        update_fields = [
            "exchange", "isin", "upstox_instrument_key", "name", "series",
            "is_active", "instrument_status", "instrument_status_reason",
        ]
        for symbol, row in selected.items():
            values = {
                "exchange": "NSE",
                "isin": str(row.get("isin") or "").strip().upper(),
                "upstox_instrument_key": str(row.get("instrument_key") or "").strip(),
                "name": str(row.get("name") or row.get("short_name") or symbol).strip(),
                "series": str(row.get("instrument_type") or "").strip().upper(),
                "is_active": True,
                "instrument_status": Company.InstrumentStatus.ACTIVE,
                "instrument_status_reason": "",
            }
            company = existing.get(symbol)
            if company is None:
                creates.append(Company(symbol=symbol, **values))
            else:
                for field_name, value in values.items():
                    setattr(company, field_name, value)
                updates.append(company)
        Company.objects.bulk_create(creates, batch_size=1_000, ignore_conflicts=True)
        if updates:
            Company.objects.bulk_update(updates, update_fields, batch_size=1_000)

        selected_keys = {
            str(row.get("instrument_key") or "").strip() for row in selected.values()
        }
        Company.objects.filter(exchange="NSE").exclude(
            upstox_instrument_key__in=selected_keys
        ).update(
            is_active=False,
            instrument_status=Company.InstrumentStatus.INACTIVE,
            instrument_status_reason="Absent from current Upstox NSE instrument master",
        )

        suspended_keys = {
            str(row.get("instrument_key") or "").strip()
            for row in suspended_rows
            if str(row.get("instrument_key") or "").startswith("NSE_EQ|")
        }
        suspended = 0
        if suspended_keys:
            suspended = Company.objects.filter(
                upstox_instrument_key__in=suspended_keys
            ).update(
                is_active=False,
                instrument_status=Company.InstrumentStatus.SUSPENDED,
                instrument_status_reason="Upstox suspended instrument master",
            )
        active_count = Company.objects.filter(
            exchange="NSE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="").count()
        return active_count, suspended

    def resolve_latest_session(self) -> date:
        local_now = self.history.now.astimezone(self.history.canonical_session_timestamp(date.today()).tzinfo)
        end = local_now.date()
        start = end - timedelta(days=self.history.SESSION_DISCOVERY_DAYS)
        response = self.history._request("NSE_INDEX|Nifty 50", start, end)
        frame = self.history._clean_frame(
            self.history._frame_from_response(response), start=start, end=end
        )
        if local_now.time() < self.history.MARKET_CLOSE_GRACE:
            frame = frame.loc[frame["session_date"] < local_now.date()]
        if frame.empty:
            raise RuntimeError("Upstox returned no completed NIFTY 50 daily session.")
        return max(frame["session_date"])

    @staticmethod
    def _decimal(value) -> Decimal:
        return Decimal(str(value))

    @classmethod
    def _stock_objects(cls, company, clean):
        return [
            CloudDailyCandle(
                company=company,
                session_date=row.session_date,
                open=cls._decimal(row.open), high=cls._decimal(row.high),
                low=cls._decimal(row.low), close=cls._decimal(row.close),
                volume=int(row.volume), provider_timestamp=row.provider_timestamp,
                data_quality_flags=row.data_quality_flags or [],
            )
            for row in clean.itertuples(index=False)
        ]

    @staticmethod
    def _flush_stock_rows(rows: list[CloudDailyCandle]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        keys = {(row.company_id, row.session_date) for row in rows}
        company_ids = {key[0] for key in keys}
        dates = {key[1] for key in keys}
        existing = set(CloudDailyCandle.objects.filter(
            company_id__in=company_ids, session_date__in=dates,
        ).values_list("company_id", "session_date"))
        CloudDailyCandle.objects.bulk_create(
            rows, batch_size=1_000, update_conflicts=True,
            unique_fields=["company", "session_date"],
            update_fields=[
                "open", "high", "low", "close", "volume",
                "provider_timestamp", "data_quality_flags",
            ],
        )
        created = len(keys.difference(existing))
        return created, len(keys) - created

    def sync_stock_history(self, latest_session: date, *, limit: int = 0) -> dict[str, int]:
        companies = list(Company.objects.filter(
            exchange="NSE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="").only(
            "id", "symbol", "exchange", "upstox_instrument_key"
        ).order_by("symbol"))
        latest_map = dict(CloudDailyCandle.objects.values_list("company_id").annotate(
            latest=Max("session_date")
        ).values_list("company_id", "latest"))
        pending = [company for company in companies if latest_map.get(company.id) != latest_session]
        processable = pending[: (limit or self.HISTORY_BATCH_LIMIT)]
        counters = {"attempted": 0, "current": len(companies) - len(pending), "updated": 0,
                    "created": 0, "rows_updated": 0, "empty": 0, "failed": 0}
        buffer: list[CloudDailyCandle] = []
        for company in processable:
            counters["attempted"] += 1
            start = (
                latest_map[company.id] + timedelta(days=1)
                if latest_map.get(company.id)
                else latest_session - timedelta(days=self.INITIAL_CALENDAR_DAYS)
            )
            try:
                response = self.history._request(company.upstox_instrument_key, start, latest_session)
                frame = self.history._frame_from_response(response)
                clean = self.history._clean_frame(frame, start=start, end=latest_session)
                if clean.empty:
                    counters["empty"] += 1
                    continue
                buffer.extend(self._stock_objects(company, clean))
                counters["updated"] += 1
                if len(buffer) >= self.WRITE_BATCH_SIZE:
                    created, updated = self._flush_stock_rows(buffer)
                    counters["created"] += created
                    counters["rows_updated"] += updated
                    buffer.clear()
            except Exception:
                counters["failed"] += 1
        created, updated = self._flush_stock_rows(buffer)
        counters["created"] += created
        counters["rows_updated"] += updated
        return counters

    def sync_benchmark(self, latest_session: date) -> int:
        latest = CloudBenchmarkCandle.objects.aggregate(latest=Max("session_date"))["latest"]
        start = latest + timedelta(days=1) if latest else latest_session - timedelta(days=500)
        if start > latest_session:
            return 0
        response = self.history._request("NSE_INDEX|Nifty 50", start, latest_session)
        frame = self.history._frame_from_response(response)
        clean = self.history._clean_frame(frame, start=start, end=latest_session)
        if clean.empty:
            return 0
        rows = [CloudBenchmarkCandle(
            session_date=row.session_date,
            open=self._decimal(row.open), high=self._decimal(row.high),
            low=self._decimal(row.low), close=self._decimal(row.close),
            volume=int(row.volume), provider_timestamp=row.provider_timestamp,
            data_quality_flags=row.data_quality_flags or [],
        ) for row in clean.itertuples(index=False)]
        CloudBenchmarkCandle.objects.bulk_create(
            rows, batch_size=500, update_conflicts=True,
            unique_fields=["session_date"],
            update_fields=[
                "open", "high", "low", "close", "volume",
                "provider_timestamp", "data_quality_flags",
            ],
        )
        return len(rows)

    @staticmethod
    def _chunks(items, size):
        for index in range(0, len(items), size):
            yield items[index:index + size]

    def sync_quotes(self) -> int:
        companies = list(Company.objects.filter(
            exchange="NSE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="").only(
            "id", "symbol", "upstox_instrument_key"
        ))
        by_symbol = {company.symbol: company for company in companies}
        rows = []
        parser = object.__new__(QuoteSyncService)
        for batch in self._chunks(companies, self.QUOTE_BATCH_SIZE):
            response = self.quotes.quote(",".join(
                company.upstox_instrument_key for company in batch
            ))
            for response_key, item in (getattr(response, "data", None) or {}).items():
                parsed = parser._build_quote(str(response_key), item)
                company = by_symbol.get(parsed["symbol"])
                if company is None or parsed["last_price"] <= 0:
                    continue
                rows.append(CloudQuoteSnapshot(company=company, **{
                    key: parsed[key] for key in (
                        "last_price", "open_price", "high_price", "low_price",
                        "previous_close", "change", "change_percent", "volume",
                        "provider_timestamp", "last_trade_time",
                    )
                }))
        CloudQuoteSnapshot.objects.bulk_create(
            rows, batch_size=1_000, update_conflicts=True,
            unique_fields=["company"],
            update_fields=[
                "last_price", "open_price", "high_price", "low_price",
                "previous_close", "change", "change_percent", "volume",
                "provider_timestamp", "last_trade_time",
            ],
        )
        return len(rows)

    @classmethod
    def prune_retention(cls) -> tuple[int, int]:
        table = CloudDailyCandle._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"""
                DELETE FROM {table} WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY company_id ORDER BY session_date DESC
                        ) AS row_number FROM {table}
                    ) ranked WHERE row_number > %s
                )
            """, [cls.STOCK_RETENTION_SESSIONS])
            stock_deleted = cursor.rowcount
        old_benchmark_ids = list(
            CloudBenchmarkCandle.objects.order_by("-session_date")
            .values_list("id", flat=True)[cls.BENCHMARK_RETENTION_SESSIONS:]
        )
        benchmark_deleted, _ = CloudBenchmarkCandle.objects.filter(
            id__in=old_benchmark_ids
        ).delete()
        return max(stock_deleted, 0), benchmark_deleted

    def run(self, *, history_limit: int = 0) -> CloudEODIngestionResult:
        result = CloudEODIngestionResult()
        result.active_instruments, result.suspended_instruments = self.refresh_instrument_mapping()
        result.latest_session = self.resolve_latest_session()
        stock = self.sync_stock_history(result.latest_session, limit=history_limit)
        result.history_attempted = stock["attempted"]
        result.history_current = stock["current"]
        result.history_updated = stock["updated"]
        result.candle_rows_created = stock["created"]
        result.candle_rows_updated = stock["rows_updated"]
        result.provider_empty = stock["empty"]
        result.provider_failed = stock["failed"]
        result.benchmark_rows = self.sync_benchmark(result.latest_session)
        result.quotes_updated = self.sync_quotes()
        result.candles_pruned, result.benchmark_pruned = self.prune_retention()
        return result