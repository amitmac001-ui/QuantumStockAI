from __future__ import annotations

import pandas as pd
from upstox_client import ApiClient, Configuration, HistoryV3Api

from apps.upstox_auth.services.read_only_credential_service import (
    read_only_credential_service,
)


class HistoricalClient:
    """Read-only Upstox V3 historical/intraday wrapper."""

    INTERVALS = {
        "day": ("days", 1),
        "week": ("weeks", 1),
        "month": ("months", 1),
        "1minute": ("minutes", 1),
        "30minute": ("minutes", 30),
    }

    def __init__(self):
        configuration = Configuration()
        configuration.access_token = read_only_credential_service.resolve()
        self.client = ApiClient(configuration)
        self.history_api = HistoryV3Api(self.client)

    @classmethod
    def _unit_interval(cls, interval: str) -> tuple[str, int]:
        try:
            return cls.INTERVALS[interval]
        except KeyError as exc:
            raise ValueError(f"Unsupported Upstox V3 interval: {interval}") from exc

    def candles(self, instrument_key: str, interval: str = "day", from_date: str | None = None, to_date: str | None = None):
        unit, numeric_interval = self._unit_interval(interval)
        if not to_date:
            raise ValueError("to_date is required for historical candles.")
        if from_date:
            return self.history_api.get_historical_candle_data1(
                instrument_key, unit, numeric_interval, to_date, from_date
            )
        return self.history_api.get_historical_candle_data(
            instrument_key, unit, numeric_interval, to_date
        )

    def intraday(self, instrument_key: str, interval: str = "1minute"):
        unit, numeric_interval = self._unit_interval(interval)
        return self.history_api.get_intra_day_candle_data(
            instrument_key, unit, numeric_interval
        )

    @staticmethod
    def dataframe(candles: list) -> pd.DataFrame:
        frame = pd.DataFrame(candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "open_interest",
        ])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        columns = ["open", "high", "low", "close", "volume"]
        frame[columns] = frame[columns].apply(pd.to_numeric, errors="coerce")
        return frame.sort_values("timestamp").reset_index(drop=True)