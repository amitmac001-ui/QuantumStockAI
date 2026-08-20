from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase
from django.core.management import call_command
from io import StringIO

from apps.core.services.technical_scanner_publisher import (
    TechnicalScannerProjectionBuilder,
    TechnicalScannerPublisher,
)
from apps.scanner.engine.technical_scanner_features import TechnicalScannerFeatureExtractor
from apps.scanner.engine.decision_engine import ScanReport, StockSnapshot
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class _Blank(SimpleNamespace):
    def __getattr__(self, name):
        return None


class _Sheet:
    row_count = 10_000

    def __init__(self, failures=0):
        self.failures = failures
        self.updates = []
        self.clears = []

    def batch_update(self, updates, **kwargs):
        if self.failures:
            self.failures -= 1
            raise TimeoutError("temporary")
        self.updates.append((updates, kwargs))

    def batch_clear(self, ranges):
        self.clears.append(ranges)


def _report(symbol: str, score: int):
    snapshot = _Blank(
        exchange="NSE", symbol=symbol, company_name=symbol,
        last_price=100.0, data_quality_state="FRESH",
        latest_daily_session=date(2026, 8, 20),
        provider_timestamp=datetime(2026, 8, 21, 4, tzinfo=dt_timezone.utc),
        technical_scanner_fields={}, setup_reason_codes=[], setup_risk_flags=[],
    )
    return _Blank(
        snapshot=snapshot, evidence_family_scores={}, component_scores={},
        overall_score=score, overall_rank_score=score,
        readiness_score=score, prebreakout_classification="WATCH",
        final_decision="WATCH", decision_reason="fixture",
        positive_signals=[], prebreakout_risk_flags=[],
        top_positive_reasons=[], top_risk_reasons=[], strategies=[],
    )


class TechnicalScannerFeatureTests(SimpleTestCase):
    @staticmethod
    def frame():
        rows = 210
        close = [100.0] * rows
        close[-2:] = [99.0, 101.0]
        return pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=rows, freq="D"),
            "close": close,
            "sma_20": [100.0] * rows,
            "ema_20": [100.0] * rows,
            "ema_50": [100.0] * rows,
            "ema_100": [100.0] * rows,
            "ema_200": [100.0] * rows,
            "macd": [0.0] * (rows - 2) + [-0.1, 0.1],
            "macd_signal": [0.0] * rows,
            "macd_histogram": [0.0] * (rows - 1) + [0.1],
            "bb_upper": [110.0] * rows, "bb_middle": [100.0] * rows,
            "bb_lower": [90.0] * rows,
            "atr": [2.0] * (rows - 1) + [1.5], "adx": [25.0] * rows,
            "plus_di": [30.0] * rows, "minus_di": [15.0] * rows,
        })

    def test_causal_crosses_and_output_schema(self):
        values = TechnicalScannerFeatureExtractor.extract(self.frame())
        self.assertIs(values["sma_20_bullish_cross"], True)
        self.assertIs(values["ema_20_bullish_cross"], True)
        self.assertIs(values["macd_bullish_cross"], True)
        self.assertIs(values["macd_bearish_cross"], False)
        self.assertEqual(values["last_committed_bar_close"], 101.0)
        self.assertIsNotNone(values["rsi_5"])

    def test_missing_history_has_no_fake_zero(self):
        self.assertEqual(
            TechnicalScannerFeatureExtractor.extract(pd.DataFrame()),
            {"technical_data_available": False},
        )

    def test_vwap_transition_requires_committed_values(self):
        self.assertEqual(
            TechnicalScannerFeatureExtractor.committed_vwap_transition(99, 102, 100, 101),
            (True, False),
        )
        self.assertEqual(
            TechnicalScannerFeatureExtractor.committed_vwap_transition(None, 102, 100, 101),
            (None, None),
        )

    def test_future_row_does_not_change_bounded_snapshot(self):
        frame = self.frame()
        before = TechnicalScannerFeatureExtractor.extract(frame)
        future = frame.iloc[-1:].copy()
        future["close"] = 10_000
        bounded = TechnicalScannerFeatureExtractor.extract(
            pd.concat([frame, future], ignore_index=True).iloc[:-1]
        )
        self.assertEqual(before, bounded)


class TechnicalScannerPublisherTests(SimpleTestCase):
    @patch("apps.core.management.commands.publish_technical_scanner.TechnicalScannerPublisher")
    @patch("apps.core.management.commands.publish_technical_scanner.LiveScanOverlayService.overlay_reports")
    @patch("apps.core.management.commands.publish_technical_scanner.ScanReportCacheService.load_valid")
    def test_management_dry_run_never_constructs_google_publisher(
        self, load_mock, overlay_mock, publisher_mock
    ):
        reports = [_report("AAA", 80)]
        load_mock.return_value = (reports, {"scanner_session": "2026-08-20"})
        overlay_mock.return_value = reports
        output = StringIO()
        call_command("publish_technical_scanner", "--dry-run", stdout=output)
        publisher_mock.assert_not_called()
        self.assertIn("TECHNICAL_SCANNER_DRY_RUN_SUCCESS", output.getvalue())

    def test_stable_rows_preserve_rank_and_deduplicate(self):
        rows = TechnicalScannerProjectionBuilder.rows(
            [_report("ZZZ", 99), _report("AAA", 80), _report("AAA", 1)],
            published_at=datetime(2026, 8, 21, 4, 1, tzinfo=dt_timezone.utc),
        )
        ticker = TechnicalScannerProjectionBuilder.HEADERS.index("Ticker")
        rank = TechnicalScannerProjectionBuilder.HEADERS.index("Rank")
        self.assertEqual([row[ticker] for row in rows], ["AAA", "ZZZ"])
        self.assertEqual([row[rank] for row in rows], [2, 1])
        self.assertTrue(all(len(row) == len(TechnicalScannerProjectionBuilder.HEADERS) for row in rows))

    @patch("apps.core.services.technical_scanner_publisher.time.sleep", return_value=None)
    @patch.object(TechnicalScannerProjectionBuilder, "rows")
    def test_chunked_write_retries_transient_failure(self, rows_mock, _sleep):
        rows_mock.return_value = [
            ["DATA_UNAVAILABLE"] * len(TechnicalScannerProjectionBuilder.HEADERS)
            for _ in range(501)
        ]
        publisher = object.__new__(TechnicalScannerPublisher)
        publisher.sheet = _Sheet(failures=1)
        result = publisher.publish([])
        self.assertEqual((result.rows, result.chunks), (501, 2))
        self.assertEqual(len(publisher.sheet.updates[0][0]), 2)

    @patch.object(TechnicalScannerProjectionBuilder, "rows", return_value=[])
    def test_permanent_sheet_failure_does_not_mutate_reports(self, _rows):
        reports = [_report("AAA", 80)]
        publisher = object.__new__(TechnicalScannerPublisher)
        publisher.sheet = _Sheet()
        publisher.sheet.batch_update = lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("bad request")
        )
        with self.assertRaises(ValueError):
            publisher.publish(reports)
        self.assertEqual(reports[0].overall_score, 80)

    def test_cache_roundtrip_is_atomic_and_session_bound(self):
        with TemporaryDirectory() as directory:
            cache = ScanReportCacheService(Path(directory) / "scan.json")
            snapshot = StockSnapshot(
                symbol="AAA", latest_daily_session=date(2026, 8, 20),
                technical_scanner_fields={"rsi_14": 55.0},
            )
            report = ScanReport(
                snapshot=snapshot, strategies=[], overall_score=80, passed_count=0,
                entry_zone=None, stop_loss=None, targets=[], risk_reward=0,
                should_alert=False, is_pre_breakout=False, is_breakout=False,
                breakout_probability=0, resistance=0, support=0,
                distance_from_breakout=0, confidence_score=0,
                raw_prebreakout_score=0, prebreakout_score=0,
                prebreakout_classification="WATCH", component_scores={},
                positive_signals=[], prebreakout_risk_flags=[],
                prebreakout_data_quality=[], prebreakout_applied_penalties={},
                prebreakout_applied_caps=[],
            )
            projected = TechnicalScannerProjectionBuilder.rows(
                [report],
                published_at=datetime(2026, 8, 21, 4, 1, tzinfo=dt_timezone.utc),
            )
            self.assertEqual(len(projected[0]), len(TechnicalScannerProjectionBuilder.HEADERS))
            cache.save(
                [report], session=date(2026, 8, 20),
                session_context={"scanner_session": "2026-08-20"},
            )
            loaded, context = cache.load(expected_session=date(2026, 8, 20))
            self.assertEqual(loaded[0].snapshot.symbol, "AAA")
            self.assertEqual(loaded[0].snapshot.technical_scanner_fields["rsi_14"], 55.0)
            self.assertEqual(context["scanner_session"], "2026-08-20")
            self.assertFalse(cache.path.with_suffix(".json.tmp").exists())
