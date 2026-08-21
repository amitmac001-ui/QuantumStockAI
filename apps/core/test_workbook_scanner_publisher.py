from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.services.workbook_scanner_publisher import (
    DATA_UNAVAILABLE,
    NOT_SUPPORTED,
    EmptyScannerReportSet,
    SwingPrebreakoutProjection,
    TechnicalScannerWorkbookProjection,
    WorkbookScannerPublisher,
    WorkbookScannerReportSet,
    WorksheetHeaderMismatch,
)


TECHNICAL_HEADERS = (
    "Company", "Ticker", "Price", "Updated At", "20 SMA", "Cross 20 SMA",
    "20 EMA", "Cross 20 EMA", "50 SMA", "Cross 50 SMA", "50 EMA",
    "Cross 50 EMA", "100 SMA", "Cross 100 SMA", "100 EMA",
    "Cross 100 EMA", "200 SMA", "Cross 200 SMA", "200 EMA",
    "Cross 200 EMA", "VWAP", "RSI 5", "RSI 9", "RSI 14", "RSI 21",
    "RS 1M", "RS 3M", "RS 6M", "RS 12M", "MACD", "MACD Signal",
    "MACD Hist", "MACD Bullish Cross", "BB Upper", "BB Mid", "BB Lower",
    "ATR 14", "ADX 14", "VCP", "Flat Base", "Cup & Handle",
    "Double Bottom", "Ascending Triangle", "Bull Flag", "Darvas Box",
    "Head & Shoulders", "Pattern Score", "Data Status", "Source", "Notes",
)

SWING_HEADERS = (
    "Rank", "Company", "Ticker", "Sector", "Price ₹", "Pattern",
    "Pattern Confidence", "Pivot ₹", "Distance to Pivot %",
    "Breakout Readiness %", "Decision", "Entry Trigger ₹", "Stop Loss ₹",
    "Target 1 ₹", "Risk:Reward", "RS 1M", "RS 3M", "RS 6M", "RS 12M",
    "RS Leadership", "RSI 14", "MACD Bull Cross", "Above VWAP",
    "20/50/200 MA Trend", "ATR Compression", "BB Squeeze", "ADX 14",
    "Volume Dry-Up", "Volume Expansion Trigger", "Latest Order Catalyst",
    "Order Value ₹ Cr", "Latest Result", "Result Strength",
    "Corporate Catalyst", "Risk Flags", "Why Ranked", "Trigger Needed",
    "Invalidation", "Data Status", "Updated At",
)


class _Blank(SimpleNamespace):
    def __getattr__(self, name):
        return None


class _Sheet:
    row_count = 10_000

    def __init__(self, headers, failures=0):
        self.headers = list(headers)
        self.failures = failures
        self.header_reads = 0
        self.updates = []
        self.clears = []

    def row_values(self, row):
        self.header_reads += 1
        return list(self.headers)

    def batch_update(self, updates, **kwargs):
        if self.failures:
            self.failures -= 1
            raise TimeoutError("temporary")
        self.updates.append((updates, kwargs))

    def batch_clear(self, ranges):
        self.clears.append(ranges)


def _report(symbol="AAA", *, price=125.5):
    observed = datetime(2026, 8, 21, 4, 0, tzinfo=dt_timezone.utc)
    technical = {
        "sma_20": 120.0, "price_vs_sma_20": "ABOVE",
        "sma_20_bullish_cross": True,
        "ema_20": 121.0, "ema_20_bullish_cross": False,
        "sma_50": 115.0, "price_vs_sma_50": "ABOVE",
        "sma_50_bullish_cross": False,
        "ema_50": 116.0, "ema_50_bullish_cross": False,
        "sma_100": 110.0, "sma_100_bullish_cross": False,
        "ema_100": 111.0, "ema_100_bullish_cross": False,
        "sma_200": 100.0, "price_vs_sma_200": "ABOVE",
        "sma_200_bullish_cross": False,
        "ema_200": 101.0, "ema_200_bullish_cross": False,
        "rsi_5": 61.0, "rsi_9": 60.0, "rsi_14": 59.0, "rsi_21": 58.0,
        "macd": 1.2, "macd_signal": 1.0, "macd_histogram": 0.2,
        "macd_bullish_cross": True,
        "bb_upper": 130.0, "bb_middle": 120.0, "bb_lower": 110.0,
        "atr_14": 2.5, "atr_contracting": True, "adx_14": 27.0,
    }
    snapshot = _Blank(
        exchange="NSE", symbol=symbol, company_name=f"{symbol} Ltd", sector="Industrials",
        last_price=price, provider_timestamp=observed, calculation_timestamp=observed,
        latest_daily_session=date(2026, 8, 20), data_quality_state="FRESH",
        technical_scanner_fields=technical,
        rs_1m_pct=3.0, rs_3m_pct=8.0, rs_6m_pct=15.0, rs_12m_pct=25.0,
        rs_trend_status="LEADING", vcp_detected=True, flat_base=False,
        ascending_triangle=False, darvas_consolidation=False,
        base_quality_score=82, breakout_level=128.0,
        distance_to_breakout_pct=1.99, setup_readiness_score=78,
        bollinger_squeeze=True, volume_dry_up_near_pivot=True,
        volume_expansion=False, setup_reason_codes=["CLOSE_ABOVE_PIVOT"],
        setup_risk_flags=["MARKET_CONTEXT_WEAK"], data_quality_reason_codes=[],
        base_risk_flags=[], vcp_risk_flags=[],
    )
    return _Blank(
        snapshot=snapshot, prebreakout_classification="READY",
        stop_loss=118.0, targets=[140.0], risk_reward=2.1,
        positive_signals=["VCP", "RS_LEADING"],
        prebreakout_risk_flags=["MARKET_CONTEXT_WEAK"], overall_score=84,
    )


def _value(headers, row, name):
    return row[headers.index(name)]


class WorkbookProjectionTests(SimpleTestCase):
    def test_exact_header_contracts(self):
        self.assertEqual(TechnicalScannerWorkbookProjection.HEADERS, TECHNICAL_HEADERS)
        self.assertEqual(SwingPrebreakoutProjection.HEADERS, SWING_HEADERS)
        self.assertEqual(len(TECHNICAL_HEADERS), 50)
        self.assertEqual(len(SWING_HEADERS), 40)

    def test_representative_field_mappings(self):
        now = datetime(2026, 8, 21, 4, 1, tzinfo=dt_timezone.utc)
        report = _report(price=Decimal("125.5000"))
        technical = TechnicalScannerWorkbookProjection.rows([report], projected_at=now)[0]
        swing = SwingPrebreakoutProjection.rows([report], projected_at=now)[0]
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "Price"), 125.5)
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "20 SMA"), 120.0)
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "Cross 20 SMA"), "YES")
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "Pattern Score"), 82)
        self.assertEqual(_value(SWING_HEADERS, swing, "Pivot ₹"), 128.0)
        self.assertEqual(_value(SWING_HEADERS, swing, "Breakout Readiness %"), 78)
        self.assertEqual(_value(SWING_HEADERS, swing, "20/50/200 MA Trend"), "20:ABOVE | 50:ABOVE | 200:ABOVE")
        self.assertEqual(_value(SWING_HEADERS, swing, "Volume Dry-Up"), "YES")

    def test_unavailable_not_supported_and_no_fake_zeroes(self):
        report = _report(price=0)
        report.snapshot.technical_scanner_fields = {}
        report.snapshot.base_quality_score = None
        report.snapshot.vcp_detected = None
        report.snapshot.flat_base = None
        report.snapshot.ascending_triangle = None
        report.snapshot.darvas_consolidation = None
        report.snapshot.setup_readiness_score = None
        report.stop_loss = None
        report.targets = []
        report.risk_reward = 0
        technical = TechnicalScannerWorkbookProjection.rows([report])[0]
        swing = SwingPrebreakoutProjection.rows([report])[0]
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "Price"), DATA_UNAVAILABLE)
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "20 SMA"), DATA_UNAVAILABLE)
        self.assertEqual(_value(TECHNICAL_HEADERS, technical, "VWAP"), NOT_SUPPORTED)
        self.assertEqual(_value(SWING_HEADERS, swing, "Risk:Reward"), DATA_UNAVAILABLE)
        self.assertEqual(_value(SWING_HEADERS, swing, "Above VWAP"), NOT_SUPPORTED)
        for name in (
            "Latest Order Catalyst", "Order Value ₹ Cr", "Latest Result",
            "Result Strength", "Corporate Catalyst",
        ):
            self.assertEqual(_value(SWING_HEADERS, swing, name), DATA_UNAVAILABLE)
        self.assertNotIn(0, technical)
        self.assertNotIn(0, swing)

    def test_stable_rank_order_and_duplicate_tickers(self):
        reports = [_report("ZZZ"), _report("AAA"), _report("ZZZ")]
        swing = SwingPrebreakoutProjection.rows(reports)
        technical = TechnicalScannerWorkbookProjection.rows(reports)
        self.assertEqual([_value(SWING_HEADERS, row, "Ticker") for row in swing], ["ZZZ", "AAA"])
        self.assertEqual([_value(SWING_HEADERS, row, "Rank") for row in swing], [1, 2])
        self.assertEqual([_value(TECHNICAL_HEADERS, row, "Ticker") for row in technical], ["AAA", "ZZZ"])

    def test_future_provider_timestamp_is_not_reported_fresh(self):
        report = _report()
        projected_at = datetime(2026, 8, 21, 3, 0, tzinfo=dt_timezone.utc)
        row = TechnicalScannerWorkbookProjection.rows(
            [report], projected_at=projected_at
        )[0]
        self.assertEqual(_value(TECHNICAL_HEADERS, row, "Data Status"), "STALE")

    def test_empty_result_is_fail_closed(self):
        with self.assertRaises(EmptyScannerReportSet):
            WorkbookScannerReportSet.build([])


class WorkbookPublisherSafetyTests(SimpleTestCase):
    @staticmethod
    def _report_set(rows=1):
        technical = [[DATA_UNAVAILABLE] * 50 for _ in range(rows)]
        swing = [[DATA_UNAVAILABLE] * 40 for _ in range(rows)]
        status = TECHNICAL_HEADERS.index("Data Status")
        for row in technical:
            row[status] = "OK"
        return WorkbookScannerReportSet(
            technical_rows=technical,
            swing_rows=swing,
            projected_at=datetime(2026, 8, 21, 4, tzinfo=dt_timezone.utc),
        )

    @staticmethod
    def _publisher(technical, swing):
        publisher = object.__new__(WorkbookScannerPublisher)
        publisher.technical_tab = "Technical Scanner"
        publisher.swing_tab = "Swing Prebreakout"
        publisher.technical_sheet = technical
        publisher.swing_sheet = swing
        return publisher

    def test_second_header_mismatch_aborts_before_any_write(self):
        technical = _Sheet(TECHNICAL_HEADERS)
        swing = _Sheet([*SWING_HEADERS[:-1], "Wrong Header"])
        publisher = self._publisher(technical, swing)
        with self.assertRaises(WorksheetHeaderMismatch):
            publisher.publish(self._report_set())
        self.assertEqual(technical.updates, [])
        self.assertEqual(swing.updates, [])
        self.assertEqual(technical.clears, [])

    @patch("apps.core.services.workbook_scanner_publisher.time.sleep", return_value=None)
    def test_chunked_write_retries_and_clears_only_after_success(self, _sleep):
        technical = _Sheet(TECHNICAL_HEADERS, failures=1)
        swing = _Sheet(SWING_HEADERS)
        publisher = self._publisher(technical, swing)
        result = publisher.publish(self._report_set(rows=501))
        self.assertEqual(result.technical.chunks, 3)
        self.assertEqual(len(technical.updates), 3)
        self.assertEqual(len(swing.updates), 3)
        self.assertEqual(len(technical.clears), 1)
        self.assertEqual(len(swing.clears), 1)

    def test_empty_publish_never_reads_headers_or_writes(self):
        technical = _Sheet(TECHNICAL_HEADERS)
        swing = _Sheet(SWING_HEADERS)
        publisher = self._publisher(technical, swing)
        empty = WorkbookScannerReportSet([], [], datetime.now(dt_timezone.utc))
        with self.assertRaises(EmptyScannerReportSet):
            publisher.publish(empty)
        self.assertEqual(technical.header_reads, 0)
        self.assertEqual(technical.updates, [])

    def test_failed_replacement_never_clears_trailing_rows(self):
        technical = _Sheet(TECHNICAL_HEADERS)
        swing = _Sheet(SWING_HEADERS)
        technical.batch_update = lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("permanent failure")
        )
        publisher = self._publisher(technical, swing)
        with self.assertRaises(ValueError):
            publisher.publish(self._report_set())
        self.assertEqual(technical.clears, [])
        self.assertEqual(swing.updates, [])
        self.assertEqual(swing.clears, [])

    def test_unrelated_tab_is_never_modified(self):
        technical = _Sheet(TECHNICAL_HEADERS)
        swing = _Sheet(SWING_HEADERS)
        unrelated = _Sheet(["User", "Owned"])
        self._publisher(technical, swing).publish(self._report_set())
        self.assertEqual(unrelated.header_reads, 0)
        self.assertEqual(unrelated.updates, [])
        self.assertEqual(unrelated.clears, [])


class WorkbookDryRunCommandTests(SimpleTestCase):
    @patch("apps.core.services.google_sheet_base.gspread.authorize")
    @patch("apps.core.services.google_sheet_base.Credentials.from_service_account_info")
    @patch("apps.core.services.google_sheet_base.Credentials.from_service_account_file")
    @patch("apps.core.management.commands.publish_workbook_scanners.WorkbookScannerPublisher")
    @patch("apps.core.management.commands.publish_workbook_scanners.LiveScanOverlayService.overlay_reports")
    @patch("apps.core.management.commands.publish_workbook_scanners.ScanReportCacheService.load_valid")
    def test_dry_run_never_constructs_google_credentials_client_or_publisher(
        self, load, overlay, publisher, from_file, from_info, authorize
    ):
        reports = [_report()]
        reports[0].snapshot.provider_timestamp = timezone.now()
        load.return_value = (
            reports,
            {
                "scanner_session": "2026-08-20",
                "cache_generated_at": datetime(2026, 8, 21, 4, tzinfo=dt_timezone.utc),
            },
        )
        overlay.return_value = reports
        output = StringIO()
        call_command("publish_workbook_scanners", "--dry-run", stdout=output)
        publisher.assert_not_called()
        from_file.assert_not_called()
        from_info.assert_not_called()
        authorize.assert_not_called()
        value = output.getvalue()
        self.assertIn("TECHNICAL_SCANNER_WORKBOOK_DRY_RUN_RESULT", value)
        self.assertIn("SWING_PREBREAKOUT_DRY_RUN_RESULT", value)
        self.assertIn("provider_calls=0 sheet_writes=0", value)

    @patch("apps.core.management.commands.publish_workbook_scanners.WorkbookScannerPublisher")
    @patch("apps.core.management.commands.publish_workbook_scanners.LiveScanOverlayService.overlay_reports")
    @patch("apps.core.management.commands.publish_workbook_scanners.ScanReportCacheService.load_valid")
    def test_stale_dry_run_fails_without_constructing_google_publisher(
        self, load, overlay, publisher
    ):
        reports = [_report()]
        reports[0].snapshot.provider_timestamp = datetime(
            2026, 8, 19, 4, tzinfo=dt_timezone.utc
        )
        load.return_value = (
            reports,
            {
                "scanner_session": "2026-08-19",
                "cache_generated_at": datetime(
                    2026, 8, 19, 5, tzinfo=dt_timezone.utc
                ),
            },
        )
        overlay.return_value = reports
        with self.assertRaisesMessage(
            CommandError, "WORKBOOK_SCANNERS_DRY_RUN_NOT_READY freshness=STALE"
        ):
            call_command("publish_workbook_scanners", "--dry-run")
        publisher.assert_not_called()
