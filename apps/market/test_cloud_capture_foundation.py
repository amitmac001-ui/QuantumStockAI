from datetime import date, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
from django.db import IntegrityError, OperationalError, transaction
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.companies.models import Company
from apps.companies.services.listing_date_recovery import ListingDateRecoveryService
from apps.market.models import CloudBenchmarkCandle, CloudDailyCandle, CloudQuoteSnapshot
from apps.market.providers.historical_client import HistoricalClient
from apps.market.providers.upstox_client import UpstoxClient
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService
from apps.market.services.quote_normalizer import QuoteNormalizer
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.cloud_snapshot_cycle_service import CloudSnapshotCycleService
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
        parsed = QuoteNormalizer.normalize(
            response_key="NSE_EQ:ACTIVE", item=item,
            instrument_key="NSE_EQ|ACTIVE", symbol_hint="ACTIVE",
        )
        self.assertEqual(parsed["symbol"], "ACTIVE")
        self.assertEqual(parsed["previous_close"], 100)
        self.assertEqual(parsed["change_percent"], 5)
        self.assertEqual(parsed["provider_timestamp"].isoformat(), "2026-08-07T15:30:00+05:30")
        self.assertIsNotNone(parsed["last_trade_time"])


class RepairScannerHistoryCommandTests(SimpleTestCase):
    @patch("apps.market.management.commands.repair_scanner_history.connection")
    @patch("apps.market.management.commands.repair_scanner_history.ListingDateRecoveryService")
    @patch("apps.market.management.commands.repair_scanner_history.CloudEODIngestionService")
    def test_entirely_unavailable_batch_fails_instead_of_reporting_success(
        self, service_class, listing_dates, database_connection
    ):
        database_connection.vendor = "postgresql"
        service = service_class.return_value
        service.resolve_latest_session.return_value = date(2026, 8, 7)
        service.sync_benchmark.return_value = 0
        service.sync_stock_history.return_value = {
            "attempted": 2, "current": 0, "updated": 0,
            "created": 0, "rows_updated": 0, "empty": 2, "failed": 0,
        }

        with self.assertRaises(CommandError):
            call_command("repair_scanner_history", limit=2, stdout=StringIO())


class ListingDateRecoveryTests(TestCase):
    def test_recovers_missing_date_by_isin_without_overwriting_existing_date(self):
        missing = Company.objects.create(
            symbol="RECOVER", exchange="NSE", name="Recover",
            isin="INE000000011", upstox_instrument_key="NSE_EQ|INE000000011",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        existing = Company.objects.create(
            symbol="KEEP", exchange="NSE", name="Keep", isin="INE000000012",
            upstox_instrument_key="NSE_EQ|INE000000012", is_active=True,
            series="EQ", listing_date=date(2001, 1, 1),
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        csv_file = StringIO(
            "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,ISIN NUMBER\n"
            "RECOVER,Recover,EQ,06-OCT-2008,INE000000011\n"
            "KEEP,Keep,EQ,07-NOV-2009,INE000000012\n"
        )
        with patch("pathlib.Path.open", return_value=csv_file):
            result = ListingDateRecoveryService.recover("official.csv")

        missing.refresh_from_db()
        existing.refresh_from_db()
        self.assertEqual(missing.listing_date, date(2008, 10, 6))
        self.assertEqual(existing.listing_date, date(2001, 1, 1))
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(result["source"], "bundled_official_nse_master")

    def test_current_official_nse_download_can_be_used(self):
        company = Company.objects.create(
            symbol="CURRENT", exchange="NSE", name="Current",
            isin="INE000000031", upstox_instrument_key="NSE_EQ|INE000000031",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        response = Mock()
        response.content = (
            b"SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,ISIN NUMBER\n"
            b"CURRENT,Current,EQ,12-SEP-2025,INE000000031\n"
        )
        http = Mock()
        http.get.return_value = response

        result = ListingDateRecoveryService.recover(
            "fallback.csv", source_url="https://nse.example/EQUITY_L.csv", http=http
        )

        company.refresh_from_db()
        self.assertEqual(company.listing_date, date(2025, 9, 12))
        self.assertEqual(result["source"], "https://nse.example/EQUITY_L.csv")
        response.raise_for_status.assert_called_once_with()

    def test_symbol_fallback_rejects_conflicting_isin(self):
        company = Company.objects.create(
            symbol="RENAMED", exchange="NSE", name="Renamed",
            isin="INE000000021", upstox_instrument_key="NSE_EQ|INE000000021",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        csv_file = StringIO(
            "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,ISIN NUMBER\n"
            "RENAMED,Old issuer,EQ,06-OCT-2008,INE999999999\n"
        )
        with patch("pathlib.Path.open", return_value=csv_file):
            result = ListingDateRecoveryService.recover("official.csv")

        company.refresh_from_db()
        self.assertIsNone(company.listing_date)
        self.assertEqual(result["unresolved"], 1)

class FakeHistory:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.ranges = []
    def candles(self, *, instrument_key, interval, from_date, to_date):
        self.calls.append(instrument_key)
        self.ranges.append((from_date, to_date))
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
            series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        self.suspended = Company.objects.create(
            symbol="SUSP", exchange="NSE", name="Suspended", isin="INE000000002",
            upstox_instrument_key="NSE_EQ|SUSP", is_active=False,
            series="EQ",
            instrument_status=Company.InstrumentStatus.SUSPENDED,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )

    @staticmethod
    def row(session="2026-08-07T00:00:00+05:30"):
        return [session, 100, 105, 99, 103, 1000, 0]

    def service(self, rows):
        return CloudEODIngestionService(
            historical=FakeHistory(rows), quotes=Mock(), sleep=lambda _: None,
            now=datetime(2026, 8, 7, 17, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    @patch("apps.market.services.cloud_eod_ingestion_service.UpstoxClient")
    def test_direct_quote_sync_initializes_provider_and_persists_equity(self, client_class):
        item = SimpleNamespace(
            symbol="ACTIVE", last_price=105, net_change=5, volume=1234,
            timestamp="2026-08-07T15:30:00+05:30",
            last_trade_time=1786096800000,
            ohlc=SimpleNamespace(open=101, high=106, low=100, close=100),
        )
        client_class.return_value.quote.return_value = SimpleNamespace(
            data={"NSE_EQ:ACTIVE": item}
        )
        service = CloudEODIngestionService(sleep=lambda _: None)

        result = service.sync_quotes()

        client_class.assert_called_once_with()
        self.assertEqual(result["equities_updated"], 1)
        self.assertTrue(CloudQuoteSnapshot.objects.filter(company=self.active).exists())

    def test_quote_batch_failure_returns_sanitized_diagnostic(self):
        class ProviderFailure(Exception):
            status = 401

        client = Mock()
        client.quote.side_effect = ProviderFailure("secret-token-must-not-appear")
        service = CloudEODIngestionService(quotes=client, sleep=lambda _: None)

        result = service.sync_quotes()

        self.assertGreater(result["batches_failed"], 0)
        self.assertEqual(result["equities_updated"], 0)
        self.assertIn("ProviderFailure status=401", result["failures"][0])
        self.assertNotIn("secret-token", str(result))

    @patch(
        "apps.market.management.commands.refresh_scanner_quotes."
        "CloudEODIngestionService.sync_quotes"
    )
    def test_quote_refresh_coverage_uses_authoritative_scanner_universe(self, sync):
        Company.objects.create(
            symbol="LEGACY", exchange="NSE", name="Legacy",
            isin="INE000000099", upstox_instrument_key="NSE_EQ|LEGACY",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            security_category=Company.SecurityCategory.OTHER,
        )
        sync.return_value = {
            "updated": 1, "equities_updated": 1, "indexes_updated": 0,
            "batches_failed": 0, "skipped": 0, "failures": [],
        }
        output = StringIO()

        call_command("refresh_scanner_quotes", stdout=output)

        self.assertIn("eligible=1 updated=1 coverage_pct=100.00", output.getvalue())

    def test_current_active_master_wins_over_overlapping_suspended_feed(self):
        active_rows = [
            {
                "segment": "NSE_EQ",
                "name": "Active",
                "isin": self.active.isin,
                "instrument_type": "EQ",
                "instrument_key": self.active.upstox_instrument_key,
                "trading_symbol": self.active.symbol,
            }
        ]
        active_rows.extend(
            {
                "segment": "NSE_EQ",
                "name": f"Company {index}",
                "isin": f"INE{index:09d}",
                "instrument_type": "EQ",
                "instrument_key": f"NSE_EQ|INE{index:09d}",
                "trading_symbol": f"EQ{index:04d}",
            }
            for index in range(999)
        )
        suspended_rows = [
            {"instrument_key": self.active.upstox_instrument_key},
            {"instrument_key": self.suspended.upstox_instrument_key},
        ]
        service = self.service([])
        service._download_json_gzip = Mock(
            side_effect=[active_rows, suspended_rows]
        )

        active_count, suspended_count = service.refresh_instrument_mapping()

        self.active.refresh_from_db()
        self.suspended.refresh_from_db()
        self.assertEqual(active_count, 1_000)
        self.assertEqual(suspended_count, 1)
        self.assertTrue(self.active.is_active)
        self.assertEqual(
            self.active.instrument_status, Company.InstrumentStatus.ACTIVE
        )
        self.assertFalse(self.suspended.is_active)
        self.assertEqual(
            self.suspended.instrument_status, Company.InstrumentStatus.SUSPENDED
        )

    def test_incremental_history_excludes_suspended_and_is_idempotent(self):
        service = self.service([self.row()])
        first = service.sync_stock_history(date(2026, 8, 7), limit=10)
        second = service.sync_stock_history(date(2026, 8, 7), limit=10)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["attempted"], 0)
        self.assertEqual(service.historical.calls, ["NSE_EQ|ACTIVE"])
        self.assertEqual(CloudDailyCandle.objects.count(), 1)

    def test_incremental_history_prioritizes_the_stalest_company(self):
        older = Company.objects.create(
            symbol="OLDER", exchange="NSE", name="Older",
            isin="INE000000003", upstox_instrument_key="NSE_EQ|OLDER",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        CloudDailyCandle.objects.create(
            company=self.active, session_date=date(2026, 8, 6),
            open=100, high=105, low=99, close=103, volume=1000,
        )
        CloudDailyCandle.objects.create(
            company=older, session_date=date(2026, 8, 1),
            open=100, high=105, low=99, close=103, volume=1000,
        )
        service = self.service([self.row()])

        service.sync_stock_history(date(2026, 8, 7), limit=1)

        self.assertEqual(service.historical.calls, ["NSE_EQ|OLDER"])

    def test_repair_prioritizes_zero_then_underfilled_and_skips_mature(self):
        underfilled = Company.objects.create(
            symbol="UNDER", exchange="NSE", name="Underfilled",
            isin="INE000000003", upstox_instrument_key="NSE_EQ|UNDER",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        mature = Company.objects.create(
            symbol="MATURE", exchange="NSE", name="Mature",
            isin="INE000000004", upstox_instrument_key="NSE_EQ|MATURE",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        sessions = pd.bdate_range(end="2026-08-07", periods=252)
        CloudDailyCandle.objects.bulk_create([
            CloudDailyCandle(
                company=mature, session_date=session.date(),
                open=100, high=105, low=99, close=103, volume=1000,
            ) for session in sessions
        ])
        CloudDailyCandle.objects.bulk_create([
            CloudDailyCandle(
                company=underfilled, session_date=session.date(),
                open=100, high=105, low=99, close=103, volume=1000,
            ) for session in sessions[-10:]
        ])
        service = self.service([self.row()])

        result = service.sync_stock_history(
            date(2026, 8, 7), limit=3, include_insufficient=True
        )

        self.assertEqual(result["attempted"], 2)
        self.assertEqual(
            service.historical.calls, ["NSE_EQ|ACTIVE", "NSE_EQ|UNDER"]
        )
        expected_start = date(2026, 8, 7) - timedelta(
            days=service.INITIAL_CALENDAR_DAYS
        )
        self.assertEqual(
            service.historical.ranges,
            [(expected_start.isoformat(), "2026-08-07")] * 2,
        )

    def test_repair_updates_stale_mature_history_after_gaps(self):
        sessions = pd.bdate_range(end="2026-08-06", periods=252)
        CloudDailyCandle.objects.bulk_create([
            CloudDailyCandle(
                company=self.active, session_date=session.date(),
                open=100, high=105, low=99, close=103, volume=1000,
            ) for session in sessions
        ])
        service = self.service([self.row()])

        result = service.sync_stock_history(
            date(2026, 8, 7), limit=1, include_insufficient=True
        )

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(service.historical.calls, ["NSE_EQ|ACTIVE"])
        self.assertEqual(service.historical.ranges, [("2026-08-07", "2026-08-07")])

    def test_history_repair_preserves_company_eligibility(self):
        original = (
            self.active.is_active,
            self.active.instrument_status,
            self.active.provider_segment,
            self.active.provider_instrument_type,
            self.active.provider_security_type,
            self.active.security_category,
        )

        self.service([self.row()]).sync_stock_history(
            date(2026, 8, 7), limit=1, include_insufficient=True
        )

        self.active.refresh_from_db()
        self.assertEqual(
            (
                self.active.is_active,
                self.active.instrument_status,
                self.active.provider_segment,
                self.active.provider_instrument_type,
                self.active.provider_security_type,
                self.active.security_category,
            ),
            original,
        )

    def test_repair_does_not_starve_unattempted_underfilled_stock(self):
        underfilled = Company.objects.create(
            symbol="UNDER", exchange="NSE", name="Underfilled",
            isin="INE000000003", upstox_instrument_key="NSE_EQ|UNDER",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        sessions = pd.bdate_range(end="2026-08-07", periods=10)
        CloudDailyCandle.objects.bulk_create([
            CloudDailyCandle(
                company=underfilled, session_date=session.date(),
                open=100, high=105, low=99, close=103, volume=1000,
            ) for session in sessions
        ])
        self.active.history_sync_last_attempt_at = datetime(
            2026, 8, 7, 12, tzinfo=ZoneInfo("Asia/Kolkata")
        )
        self.active.save(update_fields=["history_sync_last_attempt_at"])
        service = self.service([self.row()])

        service.sync_stock_history(
            date(2026, 8, 7), limit=1, include_insufficient=True
        )

        self.assertEqual(service.historical.calls, ["NSE_EQ|UNDER"])

    def test_repair_prioritizes_attempted_underfilled_before_stale_mature(self):
        mature = Company.objects.create(
            symbol="MATURE", exchange="NSE", name="Mature",
            isin="INE000000004", upstox_instrument_key="NSE_EQ|MATURE",
            is_active=True, series="EQ",
            instrument_status=Company.InstrumentStatus.ACTIVE,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        for company, count in ((self.active, 10), (mature, 252)):
            sessions = pd.bdate_range(end="2026-08-06", periods=count)
            CloudDailyCandle.objects.bulk_create([
                CloudDailyCandle(
                    company=company, session_date=session.date(),
                    open=100, high=105, low=99, close=103, volume=1000,
                ) for session in sessions
            ])
        self.active.history_sync_last_attempt_at = datetime(
            2026, 8, 6, 12, tzinfo=ZoneInfo("Asia/Kolkata")
        )
        self.active.save(update_fields=["history_sync_last_attempt_at"])
        service = self.service([self.row()])

        service.sync_stock_history(
            date(2026, 8, 7), limit=1, include_insufficient=True
        )

        self.assertEqual(service.historical.calls, ["NSE_EQ|ACTIVE"])

    @patch("apps.market.services.cloud_eod_ingestion_service.close_old_connections")
    @patch("apps.market.services.cloud_eod_ingestion_service.connection.close")
    def test_transient_database_write_is_retried_once(
        self, close_connection, close_old_connections
    ):
        callback = Mock(side_effect=[OperationalError("connection terminated"), "ok"])

        result = CloudEODIngestionService._retry_database_write(callback)

        self.assertEqual(result, "ok")
        self.assertEqual(callback.call_count, 2)
        close_connection.assert_called_once_with()
        close_old_connections.assert_called_once_with()

    def test_current_active_master_wins_over_historical_suspended_archive(self):
        service = self.service([])
        service.MINIMUM_INSTRUMENT_MASTER_ROWS = 1
        active_row = {
            "segment": "NSE_EQ", "trading_symbol": "ALPHA",
            "isin": "INE002A01018", "instrument_key": "NSE_EQ|INE002A01018",
            "instrument_type": "EQ", "security_type": "NORMAL",
            "name": "Alpha Limited",
        }
        with patch.object(
            service, "_download_json_gzip", side_effect=[[active_row], [active_row]]
        ):
            eligible, suspended = service.refresh_instrument_mapping()
        alpha = Company.objects.get(symbol="ALPHA")
        self.assertEqual(eligible, 1)
        self.assertEqual(suspended, 0)
        self.assertTrue(alpha.is_active)
        self.assertEqual(alpha.instrument_status, Company.InstrumentStatus.ACTIVE)
        self.assertEqual(
            alpha.security_category, Company.SecurityCategory.OPERATING_EQUITY
        )

    def test_empty_response_never_fabricates_a_candle(self):
        result = self.service([]).sync_stock_history(date(2026, 8, 7), limit=10)
        self.assertEqual(result["empty"], 1)
        self.assertEqual(CloudDailyCandle.objects.count(), 0)

    def test_full_seed_persists_compact_three_year_high_summary(self):
        sessions = pd.bdate_range(end="2026-08-07", periods=500)
        rows = [
            [
                session.isoformat(), 100, 100 + index / 10, 99, 100,
                1_000, 0,
            ]
            for index, session in enumerate(sessions)
        ]
        self.service(rows).sync_stock_history(date(2026, 8, 7), limit=10)
        self.active.refresh_from_db()
        self.assertEqual(self.active.three_year_observations, 500)
        self.assertEqual(float(self.active.three_year_high), 149.9)
        self.assertEqual(
            self.active.three_year_high_session, sessions[-1].date()
        )

    def test_history_limit_rotates_past_first_500_after_empty_responses(self):
        Company.objects.bulk_create([
            Company(
                symbol=f"S{index:03d}", exchange="NSE", name=f"Stock {index}",
                isin=f"INE{index:09d}"[-12:],
                upstox_instrument_key=f"NSE_EQ|S{index:03d}",
                provider_segment="NSE_EQ", provider_instrument_type="EQ",
                provider_security_type="NORMAL",
                security_category=Company.SecurityCategory.OPERATING_EQUITY,
            )
            for index in range(500)
        ])
        service = self.service([])
        first = service.sync_stock_history(date(2026, 8, 7), limit=500)
        second = service.sync_stock_history(date(2026, 8, 7), limit=1)
        self.assertEqual(first["attempted"], 500)
        self.assertEqual(second["attempted"], 1)
        self.assertEqual(service.historical.calls[-1], "NSE_EQ|S499")

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

    def test_stock_upsert_deduplicates_same_company_and_session(self):
        session = date(2026, 8, 7)
        rows = [
            CloudDailyCandle(
                company=self.active, session_date=session,
                open=100, high=105, low=99, close=101, volume=1_000,
            ),
            CloudDailyCandle(
                company=self.active, session_date=session,
                open=100, high=106, low=98, close=104, volume=1_200,
            ),
        ]

        created, updated = CloudEODIngestionService._flush_stock_rows(rows)

        candle = CloudDailyCandle.objects.get(
            company=self.active, session_date=session
        )
        self.assertEqual((created, updated), (1, 0))
        self.assertEqual(candle.close, 104)
        self.assertEqual(candle.volume, 1_200)

    def test_benchmark_upsert_deduplicates_same_session(self):
        service = self.service([
            self.row(),
            ["2026-08-07T00:00:00+05:30", 100, 106, 98, 104, 1200, 0],
        ])

        written = service.sync_benchmark(date(2026, 8, 7))

        candle = CloudBenchmarkCandle.objects.get(session_date=date(2026, 8, 7))
        self.assertEqual(written, 1)
        self.assertEqual(candle.close, 104)
        self.assertEqual(candle.volume, 1_200)

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
class CloudSnapshotDatabaseReconnectTests(SimpleTestCase):
    @patch("apps.scanner.services.cloud_snapshot_cycle_service.close_old_connections")
    @patch("apps.scanner.services.cloud_snapshot_cycle_service.connection.close")
    def test_database_phase_reconnects_and_retries_once(
        self, close_connection, close_old_connections
    ):
        callback = Mock(side_effect=[OperationalError("stale connection"), "ok"])

        result = CloudSnapshotCycleService._database_phase(callback)

        self.assertEqual(result, "ok")
        self.assertEqual(callback.call_count, 2)
        close_connection.assert_called_once_with()
        self.assertEqual(close_old_connections.call_count, 2)
