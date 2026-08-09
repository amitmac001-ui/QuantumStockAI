from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .prebreakout_scoring import prebreakout_scorer

if TYPE_CHECKING:
    from apps.scanner.engine.decision_engine import StockSnapshot


@dataclass(slots=True)
class PreBreakoutResult:

    is_pre_breakout: bool = False

    is_breakout: bool = False

    breakout_probability: float = 0.0

    resistance: float = 0.0

    support: float = 0.0

    distance_from_breakout: float = 0.0

    resistance_tests: int = 0

    consolidation_days: int = 0

    accumulation_score: float = 0.0

    smart_money_score: float = 0.0

    institutional_score: float = 0.0

    trend_score: float = 0.0

    volume_score: float = 0.0

    momentum_score: float = 0.0

    confidence_score: float = 0.0

    entry_low: float | None = None

    entry_high: float | None = None

    stop_loss: float | None = None

    target_1: float | None = None

    target_2: float | None = None

    target_3: float | None = None


class PreBreakoutEngine:

    PRE_BREAKOUT_DISTANCE = 2.00

    BREAKOUT_BUFFER = 0.25

    MIN_RSI = 55

    MAX_RSI = 72

    MIN_ADX = 20

    MIN_VOLUME_RATIO = 1.20

    MIN_SMART_MONEY = 70

    MIN_INSTITUTION = 60

    def scan(
        self,
        snapshot: StockSnapshot,
    ) -> PreBreakoutResult:

        result = PreBreakoutResult()

        result.resistance = self._resistance(snapshot)

        result.support = self._support(snapshot)

        result.distance_from_breakout = (
            self._distance(
                snapshot.last_price,
                result.resistance,
            )
        )

        return result

    def _distance(
        self,
        price: float,
        resistance: float,
    ) -> float:

        if resistance <= 0:
            return 999.0

        return (
            (resistance - price)
            / resistance
        ) * 100

    def _resistance(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        values = [
            snapshot.week_52_high,
            snapshot.donchian_upper,
            snapshot.bb_upper,
        ]

        values = [
            x
            for x in values
            if x > 0
        ]

        if not values:
            return 0.0

        return min(values)

    def _support(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        values = [
            snapshot.ema_20,
            snapshot.ema_50,
            snapshot.supertrend,
            snapshot.bb_lower,
        ]

        values = [
            x
            for x in values
            if x > 0
        ]

        if not values:
            return 0.0

        return max(values)

    def _ema_alignment(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        score = 0.0

        if snapshot.last_price > snapshot.ema_20:
            score += 20

        if snapshot.ema_20 > snapshot.ema_50:
            score += 20

        if snapshot.ema_50 > snapshot.ema_100:
            score += 20

        if snapshot.ema_100 > snapshot.ema_200:
            score += 20

        if snapshot.last_price > snapshot.vwap:
            score += 20

        return score

    def _rsi_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        if 58 <= snapshot.rsi <= 68:
            return 100

        if 55 <= snapshot.rsi <= 72:
            return 80

        if 50 <= snapshot.rsi <= 75:
            return 60

        return 20

    def _adx_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        if snapshot.adx >= 35:
            return 100

        if snapshot.adx >= 30:
            return 90

        if snapshot.adx >= 25:
            return 75

        if snapshot.adx >= 20:
            return 60

        return 20

    def _volume_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        ratio = snapshot.volume_surge

        if ratio >= 2.5:
            return 100

        if ratio >= 2.0:
            return 90

        if ratio >= 1.5:
            return 75

        if ratio >= 1.2:
            return 60

        return 20

    def _consolidation_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        days = snapshot.consolidation_days

        if days >= 40:
            return 100

        if days >= 30:
            return 90

        if days >= 20:
            return 75

        if days >= 10:
            return 60

        return 20

    def _accumulation_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        score = 0.0

        if snapshot.relative_strength >= 80:
            score += 25

        if snapshot.liquidity_score >= 80:
            score += 25

        if snapshot.sector_strength >= 70:
            score += 25

        if snapshot.institutional_holding_growth > 0:
            score += 25

        return score

    def _smart_money_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        score = 0.0

        if snapshot.volume_surge >= 1.5:
            score += 25

        if snapshot.adx >= 25:
            score += 25

        if snapshot.relative_strength >= 80:
            score += 25

        if snapshot.last_price > snapshot.vwap:
            score += 25

        return score

    def _institution_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        score = 0.0

        if snapshot.market_cap >= 5000:
            score += 20

        if snapshot.institutional_holding_growth > 0:
            score += 40

        if snapshot.cashflow_positive:
            score += 20

        if snapshot.roe >= 15:
            score += 20

        return score

    def _confidence_score(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        score = 0.0

        score += self._ema_alignment(snapshot) * 0.15
        score += self._rsi_score(snapshot) * 0.10
        score += self._adx_score(snapshot) * 0.10
        score += self._volume_score(snapshot) * 0.15
        score += self._consolidation_score(snapshot) * 0.10
        score += self._accumulation_score(snapshot) * 0.20
        score += self._smart_money_score(snapshot) * 0.10
        score += self._institution_score(snapshot) * 0.10

        return round(min(score, 100), 2)

    def _is_pre_breakout(
    self,
    snapshot: StockSnapshot,
) -> bool:

     resistance = self._resistance(snapshot)

     distance = self._distance(
        snapshot.last_price,
        resistance,
    )

     resistance = self._resistance(snapshot)

     return (

        snapshot.data_quality_state in {"FRESH", "PARTIAL"}

        and snapshot.weekly_trend != "BEARISH"

        and snapshot.already_extended is not True

        and distance <= 3

        and snapshot.resistance_tests >= 2

        and snapshot.consolidation_days >= 15

        and snapshot.volume_surge >= 1.2

        and snapshot.rsi >= 55

        and snapshot.adx >= 20

    )

    def _is_breakout(
    self,
    snapshot: StockSnapshot,
) -> bool:

     resistance = self._resistance(snapshot)

     return (

        snapshot.data_quality_state in {"FRESH", "PARTIAL"}

        and snapshot.last_price > resistance

        and snapshot.volume_surge >= 2

    )

    def _entry_zone(
        self,
        snapshot: StockSnapshot,
    ) -> tuple[float, float]:

        low = snapshot.last_price * 0.995

        high = snapshot.last_price * 1.005

        return (
            round(low, 2),
            round(high, 2),
        )

    def _stop_loss(
        self,
        snapshot: StockSnapshot,
    ) -> float:

        support = self._support(snapshot)

        return round(
            support,
            2,
        )

    def _targets(
        self,
        snapshot: StockSnapshot,
    ) -> tuple[float, float, float]:

        resistance = self._resistance(snapshot)

        t1 = resistance * 1.03
        t2 = resistance * 1.06
        t3 = resistance * 1.10

        return (
            round(t1, 2),
            round(t2, 2),
            round(t3, 2),
        )
    
    def analyze(
        self,
        snapshot: StockSnapshot,
    ) -> dict:

        resistance = self._resistance(snapshot)
        support = self._support(snapshot)

        distance = self._distance(
            snapshot.last_price,
            resistance,
        )

        score_result = prebreakout_scorer.score(snapshot)
        score = score_result.prebreakout_score

        entry_low, entry_high = self._entry_zone(snapshot)

        t1, t2, t3 = self._targets(snapshot)

        selected_breakout_level = snapshot.breakout_level or resistance
        selected_distance = (
            snapshot.distance_to_breakout_pct
            if snapshot.distance_to_breakout_pct is not None
            else round(distance, 2)
        )
        return {
            "pre_breakout": self._is_pre_breakout(snapshot),
            "breakout": self._is_breakout(snapshot),
            "confidence": score,
            "breakout_probability": score,
            "raw_prebreakout_score": score_result.raw_prebreakout_score,
            "prebreakout_score": score_result.prebreakout_score,
            "classification": score_result.classification,
            "component_scores": score_result.component_scores,
            "positive_signals": score_result.positive_signals,
            "risk_flags": score_result.risk_flags,
            "data_quality": score_result.data_quality,
            "applied_penalties": score_result.applied_penalties,
            "applied_caps": score_result.applied_caps,
            "resistance": resistance,
            "breakout_level": selected_breakout_level,
            "support": support,
            "distance_from_breakout": round(distance, 2),
            "distance_to_breakout_pct": selected_distance,
            "rs_rating": snapshot.rs_rating,
            "vcp_quality_score": snapshot.vcp_quality_score,
            "market_regime": snapshot.market_regime,
            "market_data_timestamp": (
                snapshot.timestamp.isoformat() if snapshot.timestamp else None
            ),
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": self._stop_loss(snapshot),
            "target_1": t1,
            "target_2": t2,
            "target_3": t3,
        }


prebreakout_engine = PreBreakoutEngine()
