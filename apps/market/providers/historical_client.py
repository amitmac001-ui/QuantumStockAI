from __future__ import annotations

import logging

import pandas as pd
from django.conf import settings
from upstox_client import (
    ApiClient,
    Configuration,
    HistoryApi,
)

from apps.upstox_auth.exceptions import TokenNotFoundError
from apps.upstox_auth.services.token_refresh_service import (
    token_refresh_service,
)

logger = logging.getLogger(__name__)

API_VERSION = "2.0"


class HistoricalClient:
    """
    Enterprise wrapper for Upstox Historical API.
    """

    def __init__(self):
        self._configure()

    def _configure(self):
        try:
            token = token_refresh_service.refresh_if_required()
        except TokenNotFoundError:
            access_token = str(settings.UPSTOX_ACCESS_TOKEN or "").strip()
        else:
            access_token = str(token.access_token or "").strip()
        if not access_token:
            raise RuntimeError("Upstox access token is not configured.")

        configuration = Configuration()
        configuration.access_token = access_token

        self.client = ApiClient(configuration)
        self.history_api = HistoryApi(self.client)

    def candles(
        self,
        instrument_key: str,
        interval: str = "day",
        from_date: str | None = None,
        to_date: str | None = None,
    ):
        if from_date:
            return self.history_api.get_historical_candle_data1(
                instrument_key=instrument_key,
                interval=interval,
                to_date=to_date,
                from_date=from_date,
                api_version=API_VERSION,
            )
        return self.history_api.get_historical_candle_data(
            instrument_key=instrument_key,
            interval=interval,
            to_date=to_date,
            api_version=API_VERSION,
        )

    def intraday(
        self,
        instrument_key: str,
        interval: str = "1minute",
    ):
        return self.history_api.get_intra_day_candle_data(
            instrument_key=instrument_key,
            interval=interval,
            api_version=API_VERSION,
        )

    def dataframe(
        self,
        candles: list,
    ) -> pd.DataFrame:
        """
        Convert Upstox candle response into OHLCV DataFrame.
        """

        df = pd.DataFrame(
            candles,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "open_interest",
            ],
        )

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        df[numeric_columns] = df[numeric_columns].apply(
            pd.to_numeric,
            errors="coerce",
        )

        df.sort_values(
            "timestamp",
            inplace=True,
        )

        df.reset_index(
            drop=True,
            inplace=True,
        )

        return df
