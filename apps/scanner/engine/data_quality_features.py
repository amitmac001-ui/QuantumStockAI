from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd


@dataclass(slots=True)
class DataQualityFeatures:
    data_quality_state: str = "INVALID"
    latest_daily_session: date | None = None
    expected_daily_session: date | None = None
    lookback_sessions: int = 0
    missing_session_count: int = 0
    duplicate_session_count: int = 0
    invalid_ohlc_count: int = 0
    impossible_price_count: int = 0
    negative_volume_count: int = 0
    zero_volume_count: int = 0
    abnormal_volume_count: int = 0
    invalid_timestamp_count: int = 0
    provider_flag_count: int = 0
    data_quality_reason_codes: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class DataQualityGateV2:
    """Deterministic stock-level gate over persisted legitimate daily candles."""

    MIN_LOOKBACK = 200
    TARGET_LOOKBACK = 252
    MAX_ZERO_VOLUME_RATIO = 0.10
    ABNORMAL_VOLUME_MULTIPLE = 50.0

    @staticmethod
    def _sessions(frame: pd.DataFrame) -> pd.Series:
        if frame.empty or "timestamp" not in frame:
            return pd.Series(dtype="datetime64[ns, Asia/Kolkata]")
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        return timestamps.dt.tz_convert("Asia/Kolkata").dt.normalize()

    @classmethod
    def evaluate(
        cls,
        frame: pd.DataFrame,
        benchmark_frame: pd.DataFrame,
        latest_session: date | None,
    ) -> DataQualityFeatures:
        result = DataQualityFeatures(expected_daily_session=latest_session)
        if frame.empty:
            result.data_quality_reason_codes.extend(
                ["MISSING_CANDLE_DATA", "QUALITY_STATE_INVALID"]
            )
            return result

        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(frame.columns):
            result.data_quality_reason_codes.extend(
                ["CANDLE_FIELDS_UNAVAILABLE", "QUALITY_STATE_INVALID"]
            )
            return result

        sessions = cls._sessions(frame)
        result.lookback_sessions = int(len(frame))
        result.invalid_timestamp_count = int(sessions.isna().sum())
        valid_sessions = sessions.dropna()
        result.duplicate_session_count = int(valid_sessions.duplicated().sum())
        if not valid_sessions.empty:
            result.latest_daily_session = valid_sessions.iloc[-1].date()

        numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        )
        prices = numeric[["open", "high", "low", "close"]]
        result.impossible_price_count = int(
            (prices.isna().any(axis=1) | (prices <= 0).any(axis=1)).sum()
        )
        valid_prices = prices.notna().all(axis=1)
        result.invalid_ohlc_count = int(
            (
                valid_prices
                & (
                    (numeric["high"] < prices.max(axis=1))
                    | (numeric["low"] > prices.min(axis=1))
                )
            ).sum()
        )
        result.negative_volume_count = int((numeric["volume"] < 0).sum())
        result.zero_volume_count = int((numeric["volume"] == 0).sum())

        positive_volume = numeric.loc[numeric["volume"] > 0, "volume"]
        if not positive_volume.empty:
            rolling_median = numeric["volume"].shift(1).rolling(50, min_periods=20).median()
            abnormal = (
                rolling_median.gt(0)
                & numeric["volume"].gt(rolling_median * cls.ABNORMAL_VOLUME_MULTIPLE)
            )
            # Old legitimate spikes (corporate actions/event volume) do not make
            # the current setup partial; guard only the active base window.
            result.abnormal_volume_count = int(abnormal.tail(20).sum())

        if "provider_quality_flags" in frame:
            result.provider_flag_count = sum(
                bool(value) and value != []
                for value in frame["provider_quality_flags"]
            )

        benchmark_sessions = cls._sessions(benchmark_frame).dropna().drop_duplicates()
        if not valid_sessions.empty and not benchmark_sessions.empty:
            first = valid_sessions.iloc[0]
            expected = set(benchmark_sessions.loc[benchmark_sessions >= first].tail(
                cls.TARGET_LOOKBACK
            ))
            actual = set(valid_sessions.tail(cls.TARGET_LOOKBACK))
            result.missing_session_count = len(expected.difference(actual))

        invalid = any(
            (
                result.invalid_timestamp_count,
                result.duplicate_session_count,
                result.invalid_ohlc_count,
                result.impossible_price_count,
                result.negative_volume_count,
            )
        )
        stale = bool(
            latest_session
            and result.latest_daily_session
            and result.latest_daily_session < latest_session
        )
        partial = bool(
            result.lookback_sessions < cls.MIN_LOOKBACK
            or result.missing_session_count > 0
            or result.provider_flag_count > 0
            or result.abnormal_volume_count > 0
            or (
                result.lookback_sessions > 0
                and result.zero_volume_count / result.lookback_sessions
                > cls.MAX_ZERO_VOLUME_RATIO
            )
        )

        if invalid:
            result.data_quality_state = "INVALID"
        elif stale:
            result.data_quality_state = "STALE"
        elif partial:
            result.data_quality_state = "PARTIAL"
        else:
            result.data_quality_state = "FRESH"

        reasons = []
        checks = (
            (result.lookback_sessions < cls.MIN_LOOKBACK, "INSUFFICIENT_LOOKBACK"),
            (result.missing_session_count > 0, "MISSING_DAILY_SESSIONS"),
            (result.duplicate_session_count > 0, "DUPLICATE_DAILY_SESSIONS"),
            (result.invalid_ohlc_count > 0, "INCONSISTENT_OHLC"),
            (result.impossible_price_count > 0, "IMPOSSIBLE_PRICE"),
            (result.negative_volume_count > 0, "NEGATIVE_VOLUME"),
            (result.zero_volume_count > 0, "ZERO_VOLUME_PRESENT"),
            (result.abnormal_volume_count > 0, "ABNORMAL_VOLUME_PRESENT"),
            (result.invalid_timestamp_count > 0, "INVALID_SESSION_TIMESTAMP"),
            (result.provider_flag_count > 0, "PROVIDER_QUALITY_FLAGS_PRESENT"),
            (stale, "STALE_DAILY_HISTORY"),
        )
        reasons.extend(code for detected, code in checks if detected)
        reasons.append(f"QUALITY_STATE_{result.data_quality_state}")
        result.data_quality_reason_codes = list(dict.fromkeys(reasons))
        return result


data_quality_gate_v2 = DataQualityGateV2()
