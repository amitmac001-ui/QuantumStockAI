from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean, median
from typing import TYPE_CHECKING, Iterable

from django.conf import settings
from django.db import transaction

from apps.companies.models import Company
from apps.market.models import CloudDailyCandle, MarketOHLC
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
if TYPE_CHECKING:
    from apps.scanner.engine.decision_engine import ScanReport
from apps.scanner.models import PreBreakoutSetupOutcome


@dataclass(frozen=True, slots=True)
class OutcomeTrackingResult:
    captured: int = 0
    already_recorded: int = 0
    evaluated: int = 0
    completed: int = 0


class PreBreakoutOutcomeService:
    HORIZONS = (1, 3, 5, 10, 20)
    SETUP_CLASSIFICATIONS = frozenset({"DEVELOPING", "STRONG", "HIGH_QUALITY"})

    @staticmethod
    def _decimal(value) -> Decimal | None:
        return None if value is None else Decimal(str(round(float(value), 4)))

    @classmethod
    @transaction.atomic
    def capture(
        cls, reports: Iterable[ScanReport], evaluation_session: date
    ) -> OutcomeTrackingResult:
        captured = already = 0
        for report in reports:
            snapshot = report.snapshot
            qualifies = bool(
                report.is_pre_breakout
                or report.prebreakout_classification in cls.SETUP_CLASSIFICATIONS
            )
            if (
                not qualifies
                or snapshot.breakout_level is None
                or float(snapshot.last_price or 0) <= 0
                or snapshot.data_quality_state in {"STALE", "INVALID"}
                or "STALE_MARKET_DATA" in snapshot.data_quality
            ):
                continue
            _, created = PreBreakoutSetupOutcome.objects.get_or_create(
                symbol=snapshot.symbol,
                exchange=snapshot.exchange,
                evaluation_session=evaluation_session,
                defaults={
                    "evaluation_price": cls._decimal(snapshot.last_price),
                    "pivot": cls._decimal(snapshot.breakout_level),
                    "raw_score": report.raw_prebreakout_score,
                    "final_score": report.prebreakout_score,
                    "classification": report.prebreakout_classification,
                    "data_quality_state": snapshot.data_quality_state,
                    "feature_snapshot": {
                        "weekly_trend": snapshot.weekly_trend,
                        "daily_weekly_alignment": snapshot.daily_weekly_alignment,
                        "rs_rating": snapshot.rs_rating,
                        "rs_acceleration": snapshot.rs_acceleration,
                        "rs_line_leading_price": snapshot.rs_line_leading_price,
                        "volume_dry_up_near_pivot": snapshot.volume_dry_up_near_pivot,
                        "base_quality_score": snapshot.base_quality_score,
                        "progressively_smaller_contractions": (
                            snapshot.progressively_smaller_contractions
                        ),
                        "market_regime": snapshot.market_regime,
                        "setup_lifecycle": snapshot.setup_lifecycle,
                        "setup_readiness_score": snapshot.setup_readiness_score,
                        "demand_pressure_score": snapshot.demand_pressure_score,
                        "supply_pressure_score": snapshot.supply_pressure_score,
                        "accumulation_distribution_balance": (
                            snapshot.accumulation_distribution_balance
                        ),
                        "pullback_volume_contracting": (
                            snapshot.pullback_volume_contracting
                        ),
                        "resistance_absorption_detected": (
                            snapshot.resistance_absorption_detected
                        ),
                        "selling_pressure_declining": snapshot.selling_pressure_declining,
                        "demand_expansion_detected": snapshot.demand_expansion_detected,
                        "overhead_supply_score": snapshot.overhead_supply_score,
                        "overhead_supply_clear": snapshot.overhead_supply_clear,
                        "overhead_supply_heavy": bool(
                            snapshot.overhead_supply_score is not None
                            and snapshot.overhead_supply_score >= 55
                        ),
                        "nearest_overhead_resistance": (
                            snapshot.nearest_overhead_resistance
                        ),
                        "distance_to_overhead_resistance_pct": (
                            snapshot.distance_to_overhead_resistance_pct
                        ),
                        "overhead_resistance_count": snapshot.overhead_resistance_count,
                        "failed_breakout_count": snapshot.failed_breakout_count,
                        "recent_failed_breakout": snapshot.recent_failed_breakout,
                        "days_since_failed_breakout": snapshot.days_since_failed_breakout,
                        "same_zone_failure_count": snapshot.same_zone_failure_count,
                        "repeated_failed_breakout": bool(
                            snapshot.same_zone_failure_count is not None
                            and snapshot.same_zone_failure_count >= 2
                        ),
                        "failure_severity": snapshot.failure_severity,
                        "sector_context_status": snapshot.sector_context_status,
                        "setup_reason_codes": list(snapshot.setup_reason_codes),
                        "setup_risk_flags": list(snapshot.setup_risk_flags),
                        "reason_codes": list(report.positive_signals),
                        "risk_flags": list(report.prebreakout_risk_flags),
                    },
                },
            )
            captured += int(created)
            already += int(not created)
        return OutcomeTrackingResult(captured=captured, already_recorded=already)

    @classmethod
    def _return(cls, price: float, close: float) -> Decimal:
        return cls._decimal((close / price - 1) * 100)

    @classmethod
    def evaluate_pending(cls) -> OutcomeTrackingResult:
        evaluated = completed = 0
        setups = list(PreBreakoutSetupOutcome.objects.filter(is_complete=False))
        cloud_candles: dict[int, list[CloudDailyCandle]] = {}
        company_ids: dict[tuple[str, str], int] = {}
        if settings.CLOUD_COMPACT_MARKET_DATA and setups:
            keys = {(setup.symbol, setup.exchange) for setup in setups}
            symbols = {key[0] for key in keys}
            companies = Company.objects.filter(symbol__in=symbols).only(
                "id", "symbol", "exchange"
            )
            company_ids = {
                (company.symbol, company.exchange): company.id for company in companies
                if (company.symbol, company.exchange) in keys
            }
            compact = CloudDailyCandle.objects.filter(
                company_id__in=company_ids.values()
            ).select_related("company").order_by("company_id", "session_date")
            for candle in compact.iterator(chunk_size=5_000):
                cloud_candles.setdefault(candle.company_id, []).append(candle)
        for setup in setups:
            if settings.CLOUD_COMPACT_MARKET_DATA:
                company_id = company_ids.get((setup.symbol, setup.exchange))
                candles = [
                    candle for candle in cloud_candles.get(company_id, [])
                    if candle.session_date > setup.evaluation_session
                ][:20]
            else:
                evaluation_time = DailyHistorySyncService.canonical_session_timestamp(
                    setup.evaluation_session
                )
                candles = list(MarketOHLC.objects.filter(
                    symbol=setup.symbol,
                    exchange=setup.exchange,
                    interval=MarketOHLC.Interval.D1,
                    candle_time__gt=evaluation_time,
                ).order_by("candle_time")[:20])
            if not candles:
                continue
            price = float(setup.evaluation_price)
            pivot = float(setup.pivot) if setup.pivot is not None else None
            updates = []
            for horizon in cls.HORIZONS:
                if len(candles) >= horizon:
                    field = f"return_{horizon}d"
                    setattr(setup, field, cls._return(price, float(candles[horizon - 1].close)))
                    updates.append(field)
            highs = [float(candle.high) for candle in candles]
            lows = [float(candle.low) for candle in candles]
            setup.maximum_favorable_excursion = cls._decimal((max(highs) / price - 1) * 100)
            setup.maximum_adverse_excursion = cls._decimal((min(lows) / price - 1) * 100)
            breakout_index = next(
                (index for index, candle in enumerate(candles) if pivot and float(candle.high) >= pivot),
                None,
            )
            if breakout_index is not None:
                setup.breakout_occurred = True
                setup.breakout_session = DailyHistorySyncService.session_date(
                    candles[breakout_index].candle_time
                )
                setup.sessions_to_breakout = breakout_index + 1
                setup.failed_breakout = any(
                    float(candle.close) < pivot for candle in candles[breakout_index:]
                )
            elif len(candles) >= 20:
                setup.breakout_occurred = False
                setup.failed_breakout = False
            setup.evaluated_through_session = DailyHistorySyncService.session_date(
                candles[-1].candle_time
            )
            setup.is_complete = len(candles) >= 20
            setup.save(update_fields=[
                *updates, "maximum_favorable_excursion", "maximum_adverse_excursion",
                "breakout_occurred", "breakout_session", "sessions_to_breakout",
                "failed_breakout", "evaluated_through_session", "is_complete", "updated_at",
            ])
            evaluated += 1
            completed += int(setup.is_complete)
        return OutcomeTrackingResult(evaluated=evaluated, completed=completed)
    @staticmethod
    def _score_bucket(score: int) -> str:
        if score >= 85:
            return "85-100"
        if score >= 70:
            return "70-84"
        if score >= 55:
            return "55-69"
        return "0-54"

    @staticmethod
    def _group_summary(rows, key_getter) -> dict:
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(str(key_getter(row) or "UNKNOWN"), []).append(row)
        result = {}
        for key, items in sorted(groups.items()):
            completed = [item for item in items if item["is_complete"]]
            breakouts = sum(item["breakout_occurred"] is True for item in completed)
            result[key] = {
                "setups": len(items),
                "completed": len(completed),
                "breakouts": breakouts,
                "breakout_rate": round(100 * breakouts / len(completed), 2)
                if completed else 0.0,
                "failed_breakouts": sum(
                    item["failed_breakout"] is True for item in completed
                ),
            }
        return result

    @classmethod
    def summary(cls) -> dict:
        rows = list(PreBreakoutSetupOutcome.objects.values(
            "classification", "final_score", "feature_snapshot", "is_complete",
            "breakout_occurred", "failed_breakout",
            "maximum_favorable_excursion", "maximum_adverse_excursion",
        ))
        completed = [row for row in rows if row["is_complete"]]
        breakouts = sum(row["breakout_occurred"] is True for row in completed)
        mfe = [float(row["maximum_favorable_excursion"]) for row in completed
               if row["maximum_favorable_excursion"] is not None]
        mae = [float(row["maximum_adverse_excursion"]) for row in completed
               if row["maximum_adverse_excursion"] is not None]
        return {
            "setups_captured": len(rows),
            "completed_outcomes": len(completed),
            "pending_outcomes": len(rows) - len(completed),
            "breakout_success_count": breakouts,
            "breakout_success_rate": round(100 * breakouts / len(completed), 2)
            if completed else 0.0,
            "failed_breakout_count": sum(
                row["failed_breakout"] is True for row in completed
            ),
            "average_mfe": round(mean(mfe), 4) if mfe else None,
            "median_mfe": round(median(mfe), 4) if mfe else None,
            "average_mae": round(mean(mae), 4) if mae else None,
            "median_mae": round(median(mae), 4) if mae else None,
            "by_classification": cls._group_summary(
                rows, lambda row: row["classification"]
            ),
            "by_market_regime": cls._group_summary(
                rows,
                lambda row: (row["feature_snapshot"] or {}).get("market_regime"),
            ),
            "by_score_bucket": cls._group_summary(
                rows, lambda row: cls._score_bucket(row["final_score"])
            ),
        }
