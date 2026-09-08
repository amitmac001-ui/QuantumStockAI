from __future__ import annotations

import gzip
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from typing import Any

import requests
from django.db import connection, transaction
from django.db.models import Count, Max
from django.utils import timezone

from apps.companies.models import Company
from apps.companies.services.instrument_classification import (
    InstrumentClassificationService,
)
from apps.market.models import (
    CloudBenchmarkCandle,
    CloudDailyCandle,
    CloudQuoteSnapshot,
)
from apps.market.providers.historical_client import HistoricalClient
from apps.market.providers.upstox_client import UpstoxClient
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.market.services.market_service import MarketService
from apps.market.services.quote_normalizer import QuoteNormalizer
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
    quotes_requested: int = 0
    quotes_skipped: int = 0
    quote_batches_failed: int = 0
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
    INITIAL_CALENDAR_DAYS = 1_150
    HISTORY_BATCH_LIMIT = 500
    QUOTE_BATCH_SIZE = 200
    WRITE_BATCH_SIZE = 5_000
    REQUEST_INTERVAL_SECONDS = 0.25
    MINIMUM_INSTRUMENT_MASTER_ROWS = 1_000
    MINIMUM_SCANNER_HISTORY_SESSIONS = 252

    def __init__(self, *, historical=None, quotes=None, http=None, now=None, sleep=None):
        self.historical = historical
        self.quotes = quotes
        self.http = http or requests.Session()
        self.sleep = sleep or time.sleep
        self.now = now
        self.history = (
            DailyHistorySyncService(
                self.historical, now=now, sleep=self.sleep,
                request_interval_seconds=self.REQUEST_INTERVAL_SECONDS,
            )
            if self.historical is not None else None
        )

    def _ensure_provider_clients(self):
        if self.historical is None:
            self.historical = HistoricalClient()
        if self.quotes is None:
            self.quotes = UpstoxClient()
        if self.history is None:
            self.history = DailyHistorySyncService(
                self.historical, now=self.now, sleep=self.sleep,
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
        selected: dict[str, dict[str, Any]] = {}
        for row in active_rows:
            if row.get("segment") != "NSE_EQ":
                continue
            symbol = str(row.get("trading_symbol") or "").strip().upper()
            isin = str(row.get("isin") or "").strip().upper()
            instrument_key = str(row.get("instrument_key") or "").strip()
            instrument_type = str(row.get("instrument_type") or "").strip().upper()
            # Scanner universe is normal NSE cash equity only.
            if instrument_type != "EQ" or not symbol or not isin or not instrument_key:
                continue
            selected[symbol] = row

        if len(selected) < self.MINIMUM_INSTRUMENT_MASTER_ROWS:
            raise RuntimeError("Upstox NSE instrument master is unexpectedly incomplete.")

        existing = {
            company.symbol: company
            for company in Company.objects.filter(symbol__in=selected).iterator(chunk_size=2_000)
        }
        creates, updates = [], []
        update_fields = [
            "exchange", "isin", "upstox_instrument_key", "name", "series",
            "provider_segment", "provider_instrument_type",
            "provider_security_type", "security_category",
            "is_active", "instrument_status", "instrument_status_reason",
        ]
        for symbol, row in selected.items():
            segment = str(row.get("segment") or "").strip().upper()
            instrument_type = str(row.get("instrument_type") or "").strip().upper()
            security_type = str(row.get("security_type") or "").strip().upper()
            isin = str(row.get("isin") or "").strip().upper()
            values = {
                "exchange": "NSE",
                "isin": isin,
                "upstox_instrument_key": str(row.get("instrument_key") or "").strip(),
                "name": str(row.get("name") or row.get("short_name") or symbol).strip(),
                "series": instrument_type,
                "provider_segment": segment,
                "provider_instrument_type": instrument_type,
                "provider_security_type": security_type,
                "security_category": InstrumentClassificationService.classify(
                    segment=segment,
                    instrument_type=instrument_type,
                    security_type=security_type,
                    isin=isin,
                ),
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
        }.difference(selected_keys)
        suspended = 0
        if suspended_keys:
            suspended = Company.objects.filter(
                upstox_instrument_key__in=suspended_keys
            ).exclude(
                upstox_instrument_key__in=selected_keys
            ).update(
                is_active=False,
                instrument_status=Company.InstrumentStatus.SUSPENDED,
                instrument_status_reason=(
                    "Absent from active master and present in Upstox suspended archive"
                ),
            )
        active_count = Company.scanner_eligible().count()
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
    def _deduplicate_rows(rows, key):
        """Keep the last provider row for each conflict key, preserving key order."""
        deduplicated = {}
        for row in rows:
            deduplicated[key(row)] = row
        return list(deduplicated.values())

    @staticmethod
    def _flush_stock_rows(rows: list[CloudDailyCandle]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        rows = CloudEODIngestionService._deduplicate_rows(
            rows, lambda row: (row.company_id, row.session_date)
        )
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

    def sync_stock_history(
        self, latest_session: date, *, limit: int = 0,
        include_insufficient: bool = False,
    ) -> dict[str, int]:
        companies = list(Company.scanner_eligible().annotate(
            cloud_history_sessions=Count("cloud_daily_candles", distinct=True),
            cloud_latest_session=Max("cloud_daily_candles__session_date"),
        ).only(
            "id", "symbol", "exchange", "upstox_instrument_key",
            "history_sync_last_attempt_at", "history_sync_last_success_session",
            "three_year_high", "three_year_high_session",
            "three_year_window_start", "three_year_observations",
        ))
        history_state = {
            company.id: (company.cloud_latest_session, company.cloud_history_sessions)
            for company in companies
        }
        latest_map = {company_id: state[0] for company_id, state in history_state.items()}
        pending = [
            company for company in companies
            if (
                (
                    history_state[company.id][1]
                    < self.MINIMUM_SCANNER_HISTORY_SESSIONS
                    or latest_map.get(company.id) is None
                    or latest_map[company.id] < latest_session
                )
                if include_insufficient else (
                    latest_map.get(company.id) is None
                    or latest_map[company.id] < latest_session
                )
            )
        ]
        pending.sort(key=lambda company: (
            (
                company.history_sync_last_attempt_at is not None
                if include_insufficient else False
            ),
            (
                company.history_sync_last_attempt_at
                or datetime.min.replace(tzinfo=datetime_timezone.utc)
                if include_insufficient else datetime.min.replace(
                    tzinfo=datetime_timezone.utc
                )
            ),
            history_state[company.id][1] != 0 if include_insufficient else False,
            (
                history_state.get(company.id, (None, 0))[1]
                >= self.MINIMUM_SCANNER_HISTORY_SESSIONS
            ) if include_insufficient else False,
            history_state.get(company.id, (None, 0))[1] if include_insufficient else 0,
            latest_map.get(company.id) or date.min,
            company.history_sync_last_attempt_at is not None,
            company.history_sync_last_attempt_at or datetime.min.replace(
                tzinfo=datetime_timezone.utc
            ),
            company.symbol,
        ))
        processable = pending[: (limit or self.HISTORY_BATCH_LIMIT)]
        counters = {"attempted": 0, "current": len(companies) - len(pending), "updated": 0,
                    "created": 0, "rows_updated": 0, "empty": 0, "failed": 0}
        buffer: list[CloudDailyCandle] = []
        high_summaries: list[Company] = []
        attempted_companies = []
        for company in processable:
            counters["attempted"] += 1
            company.history_sync_last_attempt_at = timezone.now()
            attempted_companies.append(company)
            insufficient = include_insufficient and (
                history_state.get(company.id, (None, 0))[1]
                < self.MINIMUM_SCANNER_HISTORY_SESSIONS
            )
            start = (
                latest_session - timedelta(days=self.INITIAL_CALENDAR_DAYS)
                if insufficient or latest_map.get(company.id) is None
                else latest_map[company.id] + timedelta(days=1)
            )
            try:
                response = self.history._request(company.upstox_instrument_key, start, latest_session)
                frame = self.history._frame_from_response(response)
                clean = self.history._clean_frame(frame, start=start, end=latest_session)
                if clean.empty:
                    counters["empty"] += 1
                    continue
                buffer.extend(self._stock_objects(company, clean))
                highest_index = clean["high"].idxmax()
                candidate_high = self._decimal(clean.loc[highest_index, "high"])
                candidate_session = clean.loc[highest_index, "session_date"]
                if (
                    company.three_year_high is None
                    or candidate_high >= company.three_year_high
                    or len(clean) >= 500
                ):
                    company.three_year_high = candidate_high
                    company.three_year_high_session = candidate_session
                if len(clean) >= 500:
                    company.three_year_window_start = clean["session_date"].min()
                    company.three_year_observations = len(clean)
                high_summaries.append(company)
                counters["updated"] += 1
                company.history_sync_last_success_session = max(clean["session_date"])
                if len(buffer) >= self.WRITE_BATCH_SIZE:
                    created, updated = self._flush_stock_rows(buffer)
                    counters["created"] += created
                    counters["rows_updated"] += updated
                    buffer.clear()
            except Exception:
                counters["failed"] += 1
        if attempted_companies:
            Company.objects.bulk_update(
                attempted_companies,
                ["history_sync_last_attempt_at", "history_sync_last_success_session"],
                batch_size=1_000,
            )
        created, updated = self._flush_stock_rows(buffer)
        counters["created"] += created
        counters["rows_updated"] += updated
        if high_summaries:
            Company.objects.bulk_update(
                high_summaries,
                [
                    "three_year_high", "three_year_high_session",
                    "three_year_window_start", "three_year_observations",
                ],
                batch_size=1_000,
            )
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
        rows = self._deduplicate_rows(rows, lambda row: row.session_date)
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

    def _request_quote_batch(self, instrument_keys):
        for attempt in range(1, DailyHistorySyncService.MAX_RETRIES + 1):
            try:
                return self.quotes.quote(",".join(instrument_keys))
            except Exception as exc:
                if (
                    attempt >= DailyHistorySyncService.MAX_RETRIES
                    or not DailyHistorySyncService._retryable(exc)
                ):
                    raise
                self.sleep(min(2 ** (attempt - 1), 8))

    def sync_quotes(self) -> dict[str, int]:
        companies = list(Company.scanner_eligible().only(
            "id", "symbol", "exchange", "name", "upstox_instrument_key"
        ))
        identities = {
            company.upstox_instrument_key: (
                company.symbol, company.exchange, company.name, company
            )
            for company in companies
        }
        identities.update({
            key: (symbol, exchange, name, None)
            for key, (symbol, exchange, name) in QuoteSyncService.INDEX_INSTRUMENTS.items()
        })
        rows = []
        index_quotes = []
        counters = {
            "requested": len(identities), "updated": 0, "skipped": 0,
            "batches_failed": 0,
        }
        for batch in self._chunks(list(identities), self.QUOTE_BATCH_SIZE):
            try:
                response = self._request_quote_batch(batch)
            except Exception:
                counters["batches_failed"] += 1
                counters["skipped"] += len(batch)
                continue
            data = getattr(response, "data", None) or {}
            for instrument_key in batch:
                symbol, exchange, name, company = identities[instrument_key]
                response_key, item = QuoteSyncService._response_item_for_key(
                    data, instrument_key, symbol
                )
                if item is None:
                    counters["skipped"] += 1
                    continue
                try:
                    parsed = QuoteNormalizer.normalize(
                        response_key=str(response_key), item=item,
                        instrument_key=instrument_key, symbol_hint=symbol,
                        company=company, company_name=name, exchange=exchange,
                    )
                except Exception:
                    counters["skipped"] += 1
                    continue
                if parsed["last_price"] <= 0:
                    counters["skipped"] += 1
                    continue
                if company is None:
                    index_quotes.append(parsed)
                else:
                    rows.append(CloudQuoteSnapshot(company=company, **{
                        key: parsed[key] for key in (
                            "last_price", "open_price", "high_price", "low_price",
                            "previous_close", "change", "change_percent", "volume",
                            "provider_timestamp", "last_trade_time", "market_status",
                            "provider_state",
                        )
                    }))
        CloudQuoteSnapshot.objects.bulk_create(
            rows, batch_size=1_000, update_conflicts=True,
            unique_fields=["company"],
            update_fields=[
                "last_price", "open_price", "high_price", "low_price",
                "previous_close", "change", "change_percent", "volume",
                "provider_timestamp", "last_trade_time", "market_status",
                "provider_state",
            ],
        )
        if index_quotes:
            MarketService.bulk_save(index_quotes)
        counters["updated"] = len(rows) + len(index_quotes)
        return counters

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
        self._ensure_provider_clients()
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
        quote_result = self.sync_quotes()
        result.quotes_updated = quote_result["updated"]
        result.quotes_requested = quote_result["requested"]
        result.quotes_skipped = quote_result["skipped"]
        result.quote_batches_failed = quote_result["batches_failed"]
        result.candles_pruned, result.benchmark_pruned = self.prune_retention()
        return result
