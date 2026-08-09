from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.companies.models import Company
from apps.market.models import MarketOHLC
from apps.market.services.benchmark_history_service import BenchmarkHistoryService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.cloud_outcome_cycle_service import CloudOutcomeCycleService
from apps.scanner.services.cloud_outcome_seed_service import CloudOutcomeSeedService


IST = ZoneInfo("Asia/Kolkata")


class FakeHistoricalClient:
    def __init__(self, stock_rows):
        self.stock_rows = stock_rows
        self.calls = []

    def candles(self, *, instrument_key, interval, from_date, to_date):
        self.calls.append((instrument_key, from_date, to_date))
        return SimpleNamespace(data=SimpleNamespace(candles=[instrument_key]))

    def dataframe(self, candles):
        key = candles[0]
        if key == BenchmarkHistoryService.INSTRUMENT_KEY:
            rows = [["2026-08-07T00:00:00+05:30", 100, 101, 99, 100, 1000, 0]]
        else:
            rows = self.stock_rows
        return pd.DataFrame(rows, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "open_interest"
        ]).assign(timestamp=lambda frame: pd.to_datetime(frame["timestamp"]))


class CloudOutcomePersistenceTests(TestCase):
    signal_session = date(2026, 7, 10)

    def setUp(self):
        Company.objects.create(
            symbol="TEST", exchange="NSE", name="Test Ltd",
            upstox_instrument_key="NSE_EQ|TEST", is_active=True,
        )
        self.outcome = PreBreakoutSetupOutcome.objects.create(
            symbol="TEST", exchange="NSE", evaluation_session=self.signal_session,
            evaluation_price=Decimal("100"), pivot=Decimal("105"), raw_score=70,
            final_score=72, classification="STRONG", data_quality_state="FRESH",
            feature_snapshot={"market_regime": "HEALTHY", "signal_only": True},
        )

    @staticmethod
    def stock_rows(include_signal=False):
        sessions = list(pd.bdate_range("2026-07-13", "2026-08-07"))
        rows = []
        if include_signal:
            rows.append(["2026-07-10T00:00:00+05:30", 99, 999, 1, 500, 1, 0])
        for index, session in enumerate(sessions):
            close = 101 + index
            rows.append([
                session.strftime("%Y-%m-%dT00:00:00+05:30"), close - 1,
                close + 1, close - 2, close, 1000 + index, 0,
            ])
        return rows

    def run_cycle(self, rows=None):
        client = FakeHistoricalClient(self.stock_rows() if rows is None else rows)
        now = datetime.combine(date(2026, 8, 7), time(17, 0), tzinfo=IST)
        return CloudOutcomeCycleService(client, now=now).run(), client

    def test_forward_candles_complete_pending_outcome_idempotently(self):
        first, client = self.run_cycle()
        self.outcome.refresh_from_db()
        self.assertFalse(first.capture_enabled)
        self.assertEqual(first.candles_created, 20)
        self.assertEqual(first.outcomes_completed, 1)
        self.assertTrue(self.outcome.is_complete)
        self.assertEqual(self.outcome.feature_snapshot, {"market_regime": "HEALTHY", "signal_only": True})
        self.assertGreaterEqual(self.outcome.breakout_session, date(2026, 7, 13))
        self.assertEqual(MarketOHLC.objects.filter(symbol="TEST").count(), 20)
        second, _ = self.run_cycle()
        self.assertEqual(second.candles_created, 0)
        self.assertEqual(MarketOHLC.objects.filter(symbol="TEST").count(), 20)
        self.assertEqual(client.calls[0][0], BenchmarkHistoryService.INSTRUMENT_KEY)

    def test_signal_session_candle_is_never_used_as_a_future_label(self):
        result, _ = self.run_cycle(self.stock_rows(include_signal=True))
        self.assertEqual(result.candles_created, 20)
        self.assertFalse(MarketOHLC.objects.filter(
            symbol="TEST", candle_time__date=self.signal_session
        ).exists())

    def test_suspended_instrument_is_not_requested(self):
        Company.objects.filter(symbol="TEST").update(
            is_active=False,
            instrument_status=Company.InstrumentStatus.SUSPENDED,
        )
        result, client = self.run_cycle()
        self.assertEqual(result.symbols_without_key, 1)
        self.assertEqual(result.symbols_requested, 0)
        self.assertEqual(len(client.calls), 1)  # Session benchmark only.

    def test_provider_empty_response_does_not_fabricate_candles(self):
        result, _ = self.run_cycle([])
        self.assertEqual(result.provider_empty_responses, 1)
        self.assertEqual(result.candles_created, 0)
        self.assertFalse(MarketOHLC.objects.filter(symbol="TEST").exists())
        self.outcome.refresh_from_db()
        self.assertFalse(self.outcome.is_complete)

    def test_database_unique_key_rejects_duplicate_setup(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PreBreakoutSetupOutcome.objects.create(
                symbol="TEST", exchange="NSE", evaluation_session=self.signal_session,
                evaluation_price=100, raw_score=1, final_score=1,
                classification="STRONG", data_quality_state="FRESH",
            )

    def test_seed_round_trip_is_checksum_verified_and_idempotent(self):
        with TemporaryDirectory() as directory:
            seed = Path(directory) / "outcomes.json"
            exported = CloudOutcomeSeedService.export_to(seed)
            self.assertEqual(exported, {"companies": 1, "outcomes": 1})
            PreBreakoutSetupOutcome.objects.all().delete()
            Company.objects.all().delete()
            first = CloudOutcomeSeedService.import_from(seed)
            second = CloudOutcomeSeedService.import_from(seed)
            verified = CloudOutcomeSeedService.verify_against(seed)
        self.assertEqual(first["outcomes_created"], 1)
        self.assertEqual(second["outcomes_created"], 0)
        self.assertEqual(PreBreakoutSetupOutcome.objects.count(), 1)
        self.assertEqual(verified["missing"], 0)
        self.assertEqual(verified["mismatched"], 0)
        self.assertEqual(verified["duplicates"], 0)

    def test_workflow_has_lock_schedule_and_no_capture_command(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "prebreakout-outcomes.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "45 10 * * 1-5"', workflow)
        self.assertIn("group: prebreakout-outcome-post-market", workflow)
        self.assertIn("python manage.py run_cloud_outcome_cycle", workflow)
        self.assertNotIn("--capture", workflow)
