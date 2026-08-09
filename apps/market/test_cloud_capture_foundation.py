from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings

from apps.companies.models import Company
from apps.market.models import CloudBenchmarkCandle, CloudDailyCandle
from apps.market.providers.historical_client import HistoricalClient
from apps.market.providers.upstox_client import UpstoxClient
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.prebreakout_outcome_service import PreBreakoutOutcomeService
from apps.upstox_auth.services.read_only_credential_service import ReadOnlyCredentialService


class ReadOnlyProviderTests(SimpleTestCase):
    @override_settings(UPSTOX_ANALYTICS_TOKEN="analytics", UPSTOX_ACCESS_TOKEN="fallback")
    @patch("apps.upstox_auth.services.read_only_credential_service.token_refresh_service.refresh_if_required")
    def test_analytics_token_is_preferred_without_oauth_lookup(self, refresh):
        self.assertEqual(ReadOnlyCredentialService().resolve(), "analytics")
        refresh.assert_not_called()

    @override_settings(UPSTOX_ANALYTICS_TOKEN="analytics")
    @patch("apps.market.providers.historical_client.HistoryV3Api")
    @patch("apps.market.providers.historical_client.ApiClient")
    @patch("apps.market.providers.historical_client.Configuration")
    def test_history_uses_v3_contract(self, configuration, api_client, history_api):
        configured = SimpleNamespace(access_token=None)
        configuration.return_value = configured
        api = history_api.return_value
        client = HistoricalClient()
        client.candles("NSE_EQ|TEST", "day", "2026-01-01", "2026-08-07")
        client.intraday("NSE_EQ|TEST", "1minute")
        self.assertEqual(configured.access_token, "analytics")
        api.get_historical_candle_data1.assert_called_once_with(
            "NSE_EQ|TEST", "days", 1, "2026-08-07", "2026-01-01"
        )
        api.get_intra_day_candle_data.assert_called_once_with(
            "NSE_EQ|TEST", "minutes", 1
        )

    @override_settings(UPSTOX_ANALYTICS_TOKEN="analytics")
    @patch("apps.market.providers.upstox_client.MarketQuoteV3Api")
    @patch("apps.market.providers.upstox_client.MarketQuoteApi")
    @patch("apps.market.providers.upstox_client.ApiClient")
    @patch("apps.market.providers.upstox_client.Configuration")
    def test_quote_routes_full_quote_to_v2_and_ltp_ohlc_to_v3(
        self, configuration, api_client, quote_api, quote_v3_api
    ):
        configured = SimpleNamespace(access_token=None)
        configuration.return_value = configured
        client = UpstoxClient()
        client.quote("NSE_EQ|TEST")
        client.ltp("NSE_EQ|TEST")
        client.ohlc("NSE_EQ|TEST", "1d")
        quote_api.return_value.get_full_market_quote.assert_called_once_with(
            symbol="NSE_EQ|TEST", api_version="2.0"
        )
        quote_v3_api.return_value.get_ltp.assert_called_once_with(
            instrument_key="NSE_EQ|TEST"
        )
        quote_v3_api.return_value.get_market_quote_ohlc.assert_called_once_with(
            interval="1d", instrument_key="NSE_EQ|TEST"
        )
    def test_cloud_quote_parser_preserves_provider_times(self):
        item = SimpleNamespace(
            symbol="NA", last_price=105, net_change=5, volume=1234,
            timestamp="2026-08-07T15:30:00+05:30",
            last_trade_time=1786096800000,
            ohlc=SimpleNamespace(open=101, high=106, low=100, close=100),
        )
        parsed = CloudEODIngestionService._build_cloud_quote("NSE_EQ:ACTIVE", item)
        self.assertEqual(parsed["symbol"], "ACTIVE")
        self.assertEqual(parsed["previous_close"], 100)
        self.assertEqual(parsed["change_percent"], 5)
        self.assertEqual(parsed["provider_timestamp"].isoformat(), "2026-08-07T15:30:00+05:30")
        self.assertIsNotNone(parsed["last_trade_time"])

class FakeHistory:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def candles(self, *, instrument_key, interval, from_date, to_date):
        self.calls.append(instrument_key)
        return SimpleNamespace(data=SimpleNamespace(candles=self.rows))
    def dataframe(self, candles):
        return pd.DataFrame(candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "open_interest"
        ])


class CloudCompactPersistenceTests(TestCase):
    def setUp(self):
        self.active = Company.objects.create(
            symbol="ACTIVE", exchange="NSE", name="Active", isin="INE000000001",
            upstox_instrument_key="NSE_EQ|ACTIVE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        )
        self.suspended = Company.objects.create(
            symbol="SUSP", exchange="NSE", name="Suspended", isin="INE000000002",
            upstox_instrument_key="NSE_EQ|SUSP", is_active=False,
            instrument_status=Company.InstrumentStatus.SUSPENDED,
        )

    @staticmethod
    def row(session="2026-08-07T00:00:00+05:30"):
        return [session, 100, 105, 99, 103, 1000, 0]

    def service(self, rows):
        return CloudEODIngestionService(
            historical=FakeHistory(rows), quotes=Mock(), sleep=lambda _: None,
            now=datetime(2026, 8, 7, 17, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    def test_incremental_history_excludes_suspended_and_is_idempotent(self):
        service = self.service([self.row()])
        first = service.sync_stock_history(date(2026, 8, 7), limit=10)
        second = service.sync_stock_history(date(2026, 8, 7), limit=10)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["attempted"], 0)
        self.assertEqual(service.historical.calls, ["NSE_EQ|ACTIVE"])
        self.assertEqual(CloudDailyCandle.objects.count(), 1)

    def test_empty_response_never_fabricates_a_candle(self):
        result = self.service([]).sync_stock_history(date(2026, 8, 7), limit=10)
        self.assertEqual(result["empty"], 1)
        self.assertEqual(CloudDailyCandle.objects.count(), 0)

    def test_session_normalization_and_duplicate_key(self):
        clean = self.service([]).history._clean_frame(
            pd.DataFrame([self.row()], columns=[
                "timestamp", "open", "high", "low", "close", "volume", "open_interest"
            ]), start=date(2026, 8, 7), end=date(2026, 8, 7)
        )
        self.assertEqual(clean.iloc[0]["session_date"], date(2026, 8, 7))
        CloudDailyCandle.objects.create(
            company=self.active, session_date=date(2026, 8, 7),
            open=100, high=105, low=99, close=103, volume=1000,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CloudDailyCandle.objects.create(
                company=self.active, session_date=date(2026, 8, 7),
                open=100, high=105, low=99, close=103, volume=1000,
            )

    def test_retention_keeps_only_272_sessions(self):
        sessions = pd.bdate_range("2025-01-01", periods=273)
        CloudDailyCandle.objects.bulk_create([
            CloudDailyCandle(
                company=self.active, session_date=session.date(),
                open=100, high=101, low=99, close=100, volume=1000,
            ) for session in sessions
        ])
        CloudEODIngestionService.prune_retention()
        self.assertEqual(CloudDailyCandle.objects.filter(company=self.active).count(), 272)
        self.assertEqual(
            CloudDailyCandle.objects.filter(company=self.active).earliest("session_date").session_date,
            sessions[1].date(),
        )

    @override_settings(CLOUD_COMPACT_MARKET_DATA=True)
    def test_pending_evaluation_uses_only_forward_sessions(self):
        outcome = PreBreakoutSetupOutcome.objects.create(
            symbol="ACTIVE", exchange="NSE", evaluation_session=date(2026, 8, 6),
            evaluation_price=100, pivot=105, raw_score=70, final_score=72,
            classification="STRONG", data_quality_state="FRESH",
            feature_snapshot={"immutable": True},
        )
        for session, high, close in [
            (date(2026, 8, 6), 999, 500),
            (date(2026, 8, 7), 106, 104),
        ]:
            CloudDailyCandle.objects.create(
                company=self.active, session_date=session,
                open=100, high=high, low=99, close=close, volume=1000,
            )
        result = PreBreakoutOutcomeService.evaluate_pending()
        outcome.refresh_from_db()
        self.assertEqual(result.evaluated, 1)
        self.assertEqual(outcome.return_1d, 4)
        self.assertEqual(outcome.breakout_session, date(2026, 8, 7))
        self.assertEqual(outcome.feature_snapshot, {"immutable": True})
        self.assertFalse(outcome.is_complete)

    @override_settings(CLOUD_COMPACT_MARKET_DATA=True)
    def test_benchmark_loader_reads_compact_rows(self):
        CloudBenchmarkCandle.objects.create(
            session_date=date(2026, 8, 7), open=100, high=101,
            low=99, close=100, volume=1000,
        )
        from apps.market.services.benchmark_history_service import BenchmarkHistoryService
        frame = BenchmarkHistoryService.load_ohlcv_frame()
        self.assertEqual(frame.iloc[-1]["timestamp"], date(2026, 8, 7))