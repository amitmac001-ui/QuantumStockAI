from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
from django.test import TestCase

from apps.companies.models import Company
from apps.market.models import MarketOHLC
from apps.market.services.daily_history_sync_service import DailyHistorySyncService


IST = ZoneInfo("Asia/Kolkata")


class DailyHistoryBackfillSchedulingTests(TestCase):
    @staticmethod
    def company(symbol="ALPHA"):
        return Company.objects.create(
            symbol=symbol,
            exchange="NSE",
            name=f"{symbol} Limited",
            isin="INE000000001",
            upstox_instrument_key="NSE_EQ|INE000000001",
            provider_segment="NSE_EQ",
            provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )

    @staticmethod
    def candle(symbol, session):
        return MarketOHLC(
            symbol=symbol,
            exchange="NSE",
            interval=MarketOHLC.Interval.D1,
            candle_time=datetime.combine(session, datetime.min.time(), tzinfo=IST),
            provider_timestamp=datetime.combine(
                session, datetime.min.time(), tzinfo=IST
            ),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1_000,
        )

    def test_fresh_but_shallow_history_is_backfilled_from_full_window(self):
        latest_session = date(2026, 9, 4)
        company = self.company()
        self.candle(company.symbol, latest_session).save()
        client = Mock()
        client.candles.return_value = SimpleNamespace(
            data=SimpleNamespace(candles=[])
        )
        client.dataframe.return_value = pd.DataFrame([{
            "timestamp": pd.Timestamp("2026-09-04T00:00:00+05:30"),
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 1_000,
        }])

        result = DailyHistorySyncService(
            client=client, request_interval_seconds=0
        ).sync(latest_session=latest_session, limit=1)

        self.assertEqual(result.stocks_updated, 1)
        self.assertEqual(
            client.candles.call_args.kwargs["from_date"],
            (latest_session - timedelta(days=420)).isoformat(),
        )

    def test_fresh_history_with_252_sessions_is_not_requested(self):
        latest_session = date(2026, 9, 4)
        company = self.company()
        MarketOHLC.objects.bulk_create([
            self.candle(company.symbol, latest_session - timedelta(days=offset))
            for offset in range(252)
        ])
        client = Mock()

        result = DailyHistorySyncService(
            client=client, request_interval_seconds=0
        ).sync(latest_session=latest_session, limit=1)

        self.assertEqual(result.already_current, 1)
        self.assertEqual(result.stocks_updated, 0)
        client.candles.assert_not_called()
