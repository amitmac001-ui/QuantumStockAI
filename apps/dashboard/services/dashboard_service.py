from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from apps.companies.models import Company
from apps.market.models import CloudDailyCandle, CloudQuoteSnapshot, MarketOHLC, MarketQuote
from apps.market.services.market_status_service import MarketStatusService
from apps.scanner.engine.decision_engine import ScanReport
from apps.scanner.services.scan_report_cache_service import InvalidScanCache, ScanReportCacheService


class DashboardService:
    """Read-only dashboard projection over persisted quote/candle/scanner data."""

    CARD_LIMIT = 6
    MOVER_LIMIT = 5
    CHART_LIMIT = 30
    BATCH_COHERENCE_SECONDS = 15 * 60
    IST = ZoneInfo("Asia/Kolkata")

    INDEX_DEFINITIONS = (
        {
            "key": "nifty_50",
            "label": "NIFTY 50",
            "aliases": ("NIFTY 50", "NIFTY"),
            "instrument_key": "NSE_INDEX|Nifty 50",
        },
        {
            "key": "sensex",
            "label": "SENSEX",
            "aliases": ("SENSEX",),
            "instrument_key": "BSE_INDEX|SENSEX",
        },
        {
            "key": "banknifty",
            "label": "BANKNIFTY",
            "aliases": ("NIFTY BANK", "BANKNIFTY", "NIFTYBANK"),
            "instrument_key": "NSE_INDEX|Nifty Bank",
        },
    )

    @staticmethod
    def _float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp(quote: Any) -> datetime | None:
        return getattr(quote, "provider_timestamp", None)

    @staticmethod
    def _eligible_queryset():
        return Company.scanner_eligible()

    @classmethod
    def _companies(cls) -> dict[tuple[str, str], Company]:
        return {
            (company.exchange.upper(), company.symbol.upper()): company
            for company in cls._eligible_queryset().only(
                "id", "symbol", "exchange", "name", "sector", "industry",
                "upstox_instrument_key",
            )
        }

    @classmethod
    def _equity_quotes(
        cls, companies: dict[tuple[str, str], Company]
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = CloudQuoteSnapshot.objects.filter(
                company_id__in=[company.id for company in companies.values()]
            ).select_related("company")
            for quote in queryset:
                records.append(cls._quote_record(quote, quote.company))
            return records

        symbols = [company.symbol for company in companies.values()]
        queryset = MarketQuote.objects.filter(exchange="NSE", symbol__in=symbols)
        for quote in queryset:
            company = companies.get((quote.exchange.upper(), quote.symbol.upper()))
            if company is not None:
                records.append(cls._quote_record(quote, company))
        return records

    @classmethod
    def _quote_record(cls, quote: Any, company: Company | None = None) -> dict[str, Any]:
        symbol = str(quote.symbol).upper()
        exchange = str(quote.exchange).upper()
        return {
            "symbol": symbol,
            "exchange": exchange,
            "company": (
                company.name if company else str(getattr(quote, "company_name", symbol))
            ),
            "sector": str(company.sector or "") if company else "",
            "industry": str(company.industry or "") if company else "",
            "instrument_key": company.upstox_instrument_key if company else None,
            "price": cls._float(quote.last_price),
            "open": cls._float(quote.open_price),
            "high": cls._float(quote.high_price),
            "low": cls._float(quote.low_price),
            "previous_close": cls._float(quote.previous_close),
            "change": cls._float(quote.change),
            "change_percent": cls._float(quote.change_percent),
            "volume": cls._integer(quote.volume),
            "provider_timestamp": cls._timestamp(quote),
            "last_trade_time": getattr(quote, "last_trade_time", None),
        }

    @classmethod
    def _indices(cls, status_service: MarketStatusService) -> dict[str, Any]:
        aliases = {
            alias.upper()
            for definition in cls.INDEX_DEFINITIONS
            for alias in definition["aliases"]
        }
        stored = {
            quote.symbol.upper(): quote
            for quote in MarketQuote.objects.filter(symbol__in=aliases)
        }
        items = []
        for definition in cls.INDEX_DEFINITIONS:
            quote = next(
                (
                    stored.get(alias.upper())
                    for alias in definition["aliases"]
                    if stored.get(alias.upper())
                ),
                None,
            )
            if quote is None:
                freshness = status_service.for_provider_timestamp(None)
                item = {
                    "key": definition["key"],
                    "label": definition["label"],
                    "instrument_key": definition["instrument_key"],
                    "symbol": None,
                    "price": None,
                    "change": None,
                    "change_percent": None,
                }
            else:
                trade_session = (
                    quote.last_trade_time.astimezone(cls.IST).date()
                    if quote.last_trade_time else None
                )
                freshness = status_service.for_provider_timestamp(
                    quote.provider_timestamp, session=trade_session
                )
                item = {
                    "key": definition["key"],
                    "label": definition["label"],
                    "instrument_key": definition["instrument_key"],
                    "symbol": quote.symbol,
                    "price": cls._float(quote.last_price),
                    "change": cls._float(quote.change),
                    "change_percent": cls._float(quote.change_percent),
                }
            item.update(status=freshness.status, freshness=freshness.as_dict())
            items.append(item)
        available = [item for item in items if item["price"] is not None]
        status = cls._combined_status([item["status"] for item in available])
        return {
            "status": status if available else MarketStatusService.DATA_UNAVAILABLE,
            "items": items,
        }

    @staticmethod
    def _combined_status(states: Iterable[str]) -> str:
        states = list(states)
        if not states:
            return MarketStatusService.DATA_UNAVAILABLE
        for state in (
            MarketStatusService.STALE,
            MarketStatusService.DATA_UNAVAILABLE,
            MarketStatusService.LIVE,
            MarketStatusService.MARKET_CLOSED,
        ):
            if state in states:
                return state
        return MarketStatusService.DATA_UNAVAILABLE

    @classmethod
    def _quote_freshness(
        cls,
        records: list[dict[str, Any]],
        status_service: MarketStatusService,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        timestamps = [
            record["provider_timestamp"]
            for record in records
            if record["provider_timestamp"]
        ]
        latest = max(timestamps) if timestamps else None
        trade_sessions = [
            record["last_trade_time"].astimezone(cls.IST).date()
            for record in records
            if record["last_trade_time"]
        ]
        freshness = status_service.for_provider_timestamp(
            latest, session=max(trade_sessions) if trade_sessions else None
        )
        if latest is None:
            return freshness.as_dict(), []

        coherent = [
            record
            for record in records
            if record["provider_timestamp"] is not None
            and abs((latest - record["provider_timestamp"]).total_seconds())
            <= cls.BATCH_COHERENCE_SECONDS
            and (record["price"] or 0) > 0
        ]
        if freshness.status == MarketStatusService.STALE:
            coherent = []
        return freshness.as_dict(), coherent

    @classmethod
    def _top_movers(
        cls,
        records: list[dict[str, Any]],
        freshness: dict[str, Any],
    ) -> dict[str, Any]:
        usable = [record for record in records if record["change_percent"] is not None]
        gainers = sorted(
            (record for record in usable if record["change_percent"] > 0),
            key=lambda item: (item["change_percent"], item["volume"] or 0),
            reverse=True,
        )[: cls.MOVER_LIMIT]
        losers = sorted(
            (record for record in usable if record["change_percent"] < 0),
            key=lambda item: (item["change_percent"], -(item["volume"] or 0)),
        )[: cls.MOVER_LIMIT]
        return {
            "status": freshness["status"],
            "freshness": freshness,
            "gainers": [cls._public_quote(record) for record in gainers],
            "losers": [cls._public_quote(record) for record in losers],
        }

    @staticmethod
    def _public_quote(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in record.items()
            if key not in {"provider_timestamp", "last_trade_time"}
        }

    @classmethod
    def _breadth_and_sectors(
        cls,
        records: list[dict[str, Any]],
        *,
        eligible_count: int,
        freshness: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        advances = sum(1 for record in records if (record["change_percent"] or 0) > 0)
        declines = sum(1 for record in records if (record["change_percent"] or 0) < 0)
        unchanged = sum(1 for record in records if record["change_percent"] == 0)
        covered = len(records)
        coverage = round((covered / eligible_count * 100), 2) if eligible_count else 0.0
        aggregate: dict[str, list[float]] = defaultdict(list)
        for record in records:
            sector = record["sector"].strip()
            if sector and record["change_percent"] is not None:
                aggregate[sector].append(record["change_percent"])
        sector_items = [
            {
                "sector": sector,
                "average_change_percent": round(sum(values) / len(values), 2),
                "covered_instruments": len(values),
            }
            for sector, values in aggregate.items()
        ]
        sector_items.sort(
            key=lambda item: (item["average_change_percent"], item["covered_instruments"]),
            reverse=True,
        )
        status = freshness["status"] if records else (
            freshness["status"]
            if freshness["status"] == MarketStatusService.STALE
            else MarketStatusService.DATA_UNAVAILABLE
        )
        breadth = {
            "status": status,
            "freshness": freshness,
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "covered_instruments": covered,
            "eligible_instruments": eligible_count,
            "coverage_percent": coverage,
        }
        sectors = {
            "status": status if sector_items else MarketStatusService.DATA_UNAVAILABLE,
            "freshness": freshness,
            "classified_instruments": sum(item["covered_instruments"] for item in sector_items),
            "covered_instruments": covered,
            "eligible_instruments": eligible_count,
            "coverage_percent": coverage,
            "items": sector_items,
        }
        return breadth, sectors

    @classmethod
    def _load_reports(cls) -> tuple[list[ScanReport], dict[str, Any], date | None, str | None]:
        try:
            reports, context = ScanReportCacheService().load_valid()
        except InvalidScanCache as exc:
            return [], {}, None, str(exc)
        session = cls._date(context.get("scanner_session"))
        if session is None and reports:
            session = cls._date(reports[0].snapshot.latest_daily_session)
        return reports, context, session, None

    @staticmethod
    def _setup_state(report: ScanReport) -> str:
        snapshot = report.snapshot
        lifecycle = str(snapshot.setup_lifecycle or "").upper()
        if lifecycle == "EXTENDED_AFTER_BREAKOUT":
            return "CLIMBING"
        if report.is_breakout:
            return "BREAKOUT CONFIRMED"
        mapping = {
            "FAILED_BREAKOUT": "FAILED ATTEMPT",
            "BREAKOUT_IN_PROGRESS": "BREAKOUT ATTEMPT",
            "BREAKOUT_READY": "PRE-BREAKOUT READY",
            "NEAR_PIVOT": "FORMING",
            "TIGHTENING": "FORMING",
            "CONTRACTING": "FORMING",
            "BASE_BUILDING": "FORMING",
        }
        return mapping.get(lifecycle, report.prebreakout_classification or report.status)

    @classmethod
    def _stage_summary(
        cls,
        reports: list[ScanReport],
        scanner_session: date | None,
        cache_error: str | None,
        status_service: MarketStatusService,
    ) -> dict[str, Any]:
        freshness = status_service.for_scanner_session(scanner_session).as_dict()
        if cache_error:
            freshness["reason"] = cache_error
        supported_order = (
            "FORMING",
            "PRE-BREAKOUT READY",
            "BREAKOUT ATTEMPT",
            "BREAKOUT CONFIRMED",
            "CLIMBING",
            "FAILED ATTEMPT",
        )
        counts = Counter(cls._setup_state(report) for report in reports)
        items = [
            {"stage": stage, "count": counts[stage]}
            for stage in supported_order
            if counts[stage] > 0
        ]
        status = freshness["status"] if reports else (
            MarketStatusService.STALE
            if cache_error and "stale" in cache_error.lower()
            else MarketStatusService.DATA_UNAVAILABLE
        )
        return {"status": status, "freshness": freshness, "items": items}

    @classmethod
    def _report_card(cls, report: ScanReport) -> dict[str, Any]:
        stock = report.snapshot
        distance_52w = None
        if stock.week_52_high and stock.week_52_high > 0:
            distance_52w = round(
                ((stock.week_52_high - stock.last_price) / stock.week_52_high) * 100,
                2,
            )
        risks = list(
            dict.fromkeys(
                [
                    *report.prebreakout_risk_flags,
                    *stock.setup_risk_flags,
                    *stock.failed_breakout_risk_flags,
                ]
            )
        )[:5]
        quality = list(dict.fromkeys(report.prebreakout_data_quality))[:5]
        return {
            "symbol": stock.symbol,
            "exchange": stock.exchange,
            "company": stock.company_name or stock.symbol,
            "sector": stock.sector or None,
            "industry": stock.industry or None,
            "instrument_key": None,
            "price": cls._float(stock.last_price),
            "change": cls._float(stock.change),
            "change_percent": cls._float(stock.change_percent),
            "session": cls._date(stock.latest_daily_session),
            "open": cls._float(stock.open_price),
            "high": cls._float(stock.high_price),
            "low": cls._float(stock.low_price),
            "close": cls._float(stock.last_price),
            "volume": cls._integer(stock.volume),
            "pivot": cls._float(stock.breakout_level or report.resistance),
            "resistance": cls._float(report.resistance),
            "rs_rating": cls._integer(stock.rs_rating),
            "distance_from_pivot_percent": cls._float(
                stock.distance_to_breakout_pct
                if stock.distance_to_breakout_pct is not None
                else report.distance_from_breakout
            ),
            "atr_tightening": stock.atr_contracting,
            "atr_contraction_ratio": cls._float(stock.atr_contraction_ratio),
            "volume_dry_up": stock.volume_dry_up,
            "up_down_volume_ratio": cls._float(stock.up_down_volume_ratio),
            "accumulation_distribution_balance": cls._float(
                stock.accumulation_distribution_balance
            ),
            "distance_from_52w_high_percent": distance_52w,
            "prebreakout_score": report.prebreakout_score,
            "overall_score": report.overall_score,
            "breakout_probability": cls._float(report.breakout_probability),
            "state": cls._setup_state(report),
            "engine_classification": report.prebreakout_classification,
            "positive_evidence": list(
                dict.fromkeys([*report.positive_signals, *stock.setup_reason_codes])
            )[:5],
            "risk_flags": risks,
            "quality_flags": quality,
            "chart": [],
        }

    @classmethod
    def _attach_company_keys(
        cls,
        cards: list[dict[str, Any]],
        companies: dict[tuple[str, str], Company],
    ) -> None:
        for card in cards:
            company = companies.get((card["exchange"].upper(), card["symbol"].upper()))
            if company:
                card["instrument_key"] = company.upstox_instrument_key

    @classmethod
    def _attach_charts(cls, cards: list[dict[str, Any]]) -> None:
        symbols = {card["symbol"] for card in cards}
        if not symbols:
            return
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = (
                CloudDailyCandle.objects.filter(company__symbol__in=symbols)
                .select_related("company")
                .order_by("company__symbol", "-session_date")
            )
            for candle in queryset.iterator(chunk_size=1_000):
                bucket = grouped[candle.company.symbol]
                if len(bucket) < cls.CHART_LIMIT:
                    bucket.append(cls._candle(candle, candle.session_date))
        else:
            queryset = MarketOHLC.objects.filter(
                exchange="NSE",
                interval=MarketOHLC.Interval.D1,
                symbol__in=symbols,
            ).order_by("symbol", "-candle_time")
            for candle in queryset.iterator(chunk_size=1_000):
                bucket = grouped[candle.symbol]
                if len(bucket) < cls.CHART_LIMIT:
                    bucket.append(cls._candle(candle, candle.candle_time.date()))
        for card in cards:
            card["chart"] = list(reversed(grouped.get(card["symbol"], [])))

    @classmethod
    def _candle(cls, candle: Any, session: date) -> dict[str, Any]:
        return {
            "date": session.isoformat(),
            "open": cls._float(candle.open),
            "high": cls._float(candle.high),
            "low": cls._float(candle.low),
            "close": cls._float(candle.close),
            "volume": cls._integer(candle.volume),
        }

    @classmethod
    def _scanner_sections(
        cls,
        reports: list[ScanReport],
        scanner_session: date | None,
        cache_error: str | None,
        status_service: MarketStatusService,
        companies: dict[tuple[str, str], Company],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        freshness = status_service.for_scanner_session(scanner_session).as_dict()
        if cache_error:
            freshness["reason"] = cache_error
        ranked = sorted(
            reports,
            key=lambda report: (
                report.overall_score,
                report.prebreakout_score,
                report.confidence_score,
            ),
            reverse=True,
        )
        priority_reports = [report for report in ranked if report.overall_score >= 70][
            : cls.CARD_LIMIT
        ]
        prebreakout_reports = [
            report for report in ranked if report.is_pre_breakout or report.is_breakout
        ][: cls.CARD_LIMIT]
        report_by_symbol = {
            report.snapshot.symbol: report
            for report in [*priority_reports, *prebreakout_reports]
        }
        all_cards = [cls._report_card(report) for report in report_by_symbol.values()]
        cls._attach_company_keys(all_cards, companies)
        cls._attach_charts(all_cards)
        by_symbol = {card["symbol"]: card for card in all_cards}
        priority = [by_symbol[report.snapshot.symbol] for report in priority_reports]
        prebreakout = [by_symbol[report.snapshot.symbol] for report in prebreakout_reports]
        status = freshness["status"] if reports else (
            MarketStatusService.STALE
            if cache_error and "stale" in cache_error.lower()
            else MarketStatusService.DATA_UNAVAILABLE
        )
        return (
            {"status": status, "freshness": freshness, "items": priority},
            {"status": status, "freshness": freshness, "items": prebreakout},
        )

    @classmethod
    def home(cls, *, now: datetime | None = None) -> dict[str, Any]:
        status_service = MarketStatusService(now=now)
        companies = cls._companies()
        quotes = cls._equity_quotes(companies)
        quote_freshness, coherent_quotes = cls._quote_freshness(quotes, status_service)
        reports, _cache_context, scanner_session, cache_error = cls._load_reports()
        priority, prebreakout = cls._scanner_sections(
            reports, scanner_session, cache_error, status_service, companies
        )
        stage_summary = cls._stage_summary(
            reports, scanner_session, cache_error, status_service
        )
        breadth, sectors = cls._breadth_and_sectors(
            coherent_quotes,
            eligible_count=len(companies),
            freshness=quote_freshness,
        )
        latest_provider = max(
            (
                quote["provider_timestamp"]
                for quote in quotes
                if quote["provider_timestamp"]
            ),
            default=None,
        )
        latest_trade_session = max(
            (
                quote["last_trade_time"].astimezone(cls.IST).date()
                for quote in quotes
                if quote["last_trade_time"]
            ),
            default=None,
        )
        meta = status_service.market_meta(
            provider_timestamp=latest_provider,
            provider_session=latest_trade_session,
            scanner_session=scanner_session,
        )
        meta["scanner_stages"] = stage_summary
        return {
            "meta": meta,
            "indices": cls._indices(status_service),
            "top_movers": cls._top_movers(coherent_quotes, quote_freshness),
            "sectors": sectors,
            "breadth": breadth,
            "priority_stocks": priority,
            "prebreakout_opportunities": prebreakout,
            "capabilities": {
                "stock_search": "AVAILABLE",
                "sector_search": "AVAILABLE",
                "index_search": "AVAILABLE",
                "ipo": MarketStatusService.DATA_UNAVAILABLE,
                "news": MarketStatusService.DATA_UNAVAILABLE,
                "persistent_watchlist": MarketStatusService.DATA_UNAVAILABLE,
            },
        }

    @classmethod
    def dashboard_context(cls) -> dict[str, Any]:
        return {"dashboard": cls.home()}

    @classmethod
    def search(cls, query: str, *, limit: int = 12) -> dict[str, Any]:
        term = str(query or "").strip()
        capabilities = {
            "stock": "AVAILABLE",
            "sector": "AVAILABLE",
            "index": "AVAILABLE",
            "ipo": MarketStatusService.DATA_UNAVAILABLE,
            "news": MarketStatusService.DATA_UNAVAILABLE,
        }
        if len(term) < 2:
            return {"query": term, "results": [], "capabilities": capabilities}

        eligible = cls._eligible_queryset()
        stocks = list(
            eligible.filter(Q(symbol__icontains=term) | Q(name__icontains=term))
            .values("symbol", "name", "exchange", "sector", "industry")
            .order_by("symbol")[:limit]
        )
        results = [
            {
                "type": "stock",
                "label": stock["symbol"],
                "description": stock["name"],
                "symbol": stock["symbol"],
                "url": reverse(
                    "dashboard:stock-detail",
                    kwargs={"symbol": stock["symbol"]},
                ),
                "exchange": stock["exchange"],
                "sector": stock["sector"] or None,
                "industry": stock["industry"] or None,
            }
            for stock in stocks
        ]
        remaining = max(limit - len(results), 0)
        if remaining:
            sectors = list(
                eligible.filter(sector__icontains=term)
                .exclude(sector="")
                .values_list("sector", flat=True)
                .distinct()
                .order_by("sector")[:remaining]
            )
            results.extend(
                {
                    "type": "sector",
                    "label": sector,
                    "description": "Persisted company sector",
                }
                for sector in sectors
            )
        remaining = max(limit - len(results), 0)
        if remaining:
            known_indices = {
                alias
                for definition in cls.INDEX_DEFINITIONS
                for alias in definition["aliases"]
            }
            index_quotes = MarketQuote.objects.filter(
                symbol__icontains=term,
                symbol__in=known_indices,
            ).values("symbol", "exchange")[:remaining]
            results.extend(
                {
                    "type": "index",
                    "label": item["symbol"],
                    "description": f"{item['exchange']} index",
                    "symbol": item["symbol"],
                    "exchange": item["exchange"],
                }
                for item in index_quotes
            )
        return {"query": term, "results": results[:limit], "capabilities": capabilities}
