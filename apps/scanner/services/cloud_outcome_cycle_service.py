from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from django.db.models import Max, Min
from django.utils import timezone

from apps.companies.models import Company
from apps.market.models import MarketOHLC
from apps.market.providers.historical_client import HistoricalClient
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.prebreakout_outcome_service import PreBreakoutOutcomeService


@dataclass(slots=True)
class CloudOutcomeCycleResult:
    capture_enabled: bool = False
    latest_legitimate_session: date | None = None
    pending_setups: int = 0
    symbols_requested: int = 0
    symbols_without_key: int = 0
    provider_empty_responses: int = 0
    provider_failures: int = 0
    candles_created: int = 0
    candles_updated: int = 0
    outcomes_evaluated: int = 0
    outcomes_completed: int = 0
    skipped_reason: str | None = None
    failure_symbols: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        output = asdict(self)
        if self.latest_legitimate_session is not None:
            output["latest_legitimate_session"] = self.latest_legitimate_session.isoformat()
        return output


class CloudOutcomeCycleService:
    """Persist only genuine forward D1 candles for already-captured setups.

    This service deliberately has no scanner/capture path. Signal-time feature
    snapshots must already exist and are never recomputed here.
    """

    def __init__(self, client: HistoricalClient | None = None, *, now=None):
        self.client = client or HistoricalClient()
        self.now = now or timezone.now()
        self.history = DailyHistorySyncService(
            self.client,
            now=self.now,
        )

    @staticmethod
    def _pending_ranges() -> dict[tuple[str, str], date]:
        rows = (
            PreBreakoutSetupOutcome.objects.filter(is_complete=False)
            .values("symbol", "exchange")
            .annotate(first_session=Min("evaluation_session"))
        )
        return {
            (str(row["symbol"]).upper(), str(row["exchange"]).upper()): row["first_session"]
            for row in rows
        }

    @staticmethod
    def _company_keys(symbols: set[str]) -> dict[tuple[str, str], str]:
        rows = Company.objects.filter(
            symbol__in=symbols,
            is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).values("symbol", "exchange", "upstox_instrument_key")
        return {
            (str(row["symbol"]).upper(), str(row["exchange"]).upper()): str(
                row["upstox_instrument_key"] or ""
            ).strip()
            for row in rows
        }

    @staticmethod
    def _latest_stored(keys: set[tuple[str, str]]) -> dict[tuple[str, str], date]:
        if not keys:
            return {}
        symbols = {key[0] for key in keys}
        rows = (
            MarketOHLC.objects.filter(
                symbol__in=symbols,
                interval=MarketOHLC.Interval.D1,
            )
            .values("symbol", "exchange")
            .annotate(latest=Max("candle_time"))
        )
        return {
            (str(row["symbol"]).upper(), str(row["exchange"]).upper()):
            DailyHistorySyncService.session_date(row["latest"])
            for row in rows
            if (str(row["symbol"]).upper(), str(row["exchange"]).upper()) in keys
        }

    def run(self) -> CloudOutcomeCycleResult:
        result = CloudOutcomeCycleResult()
        result.pending_setups = PreBreakoutSetupOutcome.objects.filter(
            is_complete=False
        ).count()
        if result.pending_setups == 0:
            result.skipped_reason = "NO_PENDING_OUTCOMES"
            return result

        try:
            latest_session, _ = self.history.resolve_latest_completed_session()
        except Exception:
            result.skipped_reason = "LEGITIMATE_EOD_SESSION_UNAVAILABLE"
            return result
        result.latest_legitimate_session = latest_session

        ranges = self._pending_ranges()
        company_keys = self._company_keys({key[0] for key in ranges})
        latest_stored = self._latest_stored(set(ranges))
        for key, signal_session in sorted(ranges.items()):
            instrument_key = company_keys.get(key, "")
            if not instrument_key:
                result.symbols_without_key += 1
                continue
            start = signal_session + timedelta(days=1)
            if key in latest_stored:
                start = max(start, latest_stored[key] + timedelta(days=1))
            if start > latest_session:
                continue
            result.symbols_requested += 1
            try:
                response = self.history._request(instrument_key, start, latest_session)
                frame = self.history._frame_from_response(response)
                if frame.empty:
                    result.provider_empty_responses += 1
                    continue
                created, updated = DailyHistorySyncService.persist_stock_frame(
                    symbol=key[0],
                    exchange=key[1],
                    frame=frame,
                    start=start,
                    end=latest_session,
                )
                result.candles_created += created
                result.candles_updated += updated
            except Exception:
                result.provider_failures += 1
                result.failure_symbols.append(key[0])

        evaluated = PreBreakoutOutcomeService.evaluate_pending()
        result.outcomes_evaluated = evaluated.evaluated
        result.outcomes_completed = evaluated.completed
        return result


cloud_outcome_cycle_service_class = CloudOutcomeCycleService
