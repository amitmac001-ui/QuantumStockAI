from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings

from apps.companies.models import Company
from apps.core.services.scanner_data_readiness import (
    ScannerDataReadinessService,
    ScannerReadinessSnapshot,
)
from apps.market.models import (
    CloudBenchmarkCandle,
    CloudDailyCandle,
    CloudQuoteSnapshot,
)


IST = ZoneInfo("Asia/Kolkata")


def _snapshot(**overrides):
    values = {
        "mode": "cloud_compact",
        "active_eligible_instruments": 100,
        "latest_stock_session": date(2026, 8, 20),
        "latest_benchmark_session": date(2026, 8, 20),
        "expected_latest_completed_session": date(2026, 8, 20),
        "aligned_session": date(2026, 8, 20),
        "distinct_stock_instruments": 96,
        "distinct_quote_instruments": 97,
        "stock_coverage": 0.96,
        "quote_coverage": 0.97,
        "report_instruments": 91,
        "report_coverage": 0.91,
    }
    values.update(overrides)
    return ScannerReadinessSnapshot(**values)


class ScannerReadinessEvaluationTests(SimpleTestCase):
    def test_stale_session_fails_closed(self):
        snapshot = _snapshot(
            latest_stock_session=date(2026, 8, 19),
            latest_benchmark_session=date(2026, 8, 19),
            aligned_session=date(2026, 8, 19),
        )
        self.assertIn(
            "STALE_SESSION", ScannerDataReadinessService.failures(snapshot)
        )

    def test_ten_of_865_stock_coverage_fails_closed(self):
        snapshot = _snapshot(
            active_eligible_instruments=865,
            distinct_stock_instruments=10,
            distinct_quote_instruments=865,
            stock_coverage=10 / 865,
            quote_coverage=1.0,
            report_instruments=None,
            report_coverage=None,
        )
        failures = ScannerDataReadinessService.failures(snapshot)
        self.assertIn("INCOMPLETE_STOCK_COVERAGE", failures)
        self.assertNotIn("INCOMPLETE_QUOTE_COVERAGE", failures)

    def test_small_generated_report_coverage_fails_closed(self):
        snapshot = _snapshot(
            active_eligible_instruments=865,
            distinct_stock_instruments=830,
            distinct_quote_instruments=830,
            stock_coverage=830 / 865,
            quote_coverage=830 / 865,
            report_instruments=10,
            report_coverage=10 / 865,
        )
        self.assertIn(
            "INCOMPLETE_REPORT_COVERAGE",
            ScannerDataReadinessService.failures(snapshot),
        )

    def test_healthy_percentage_coverage_passes(self):
        self.assertEqual(ScannerDataReadinessService.failures(_snapshot()), [])


@override_settings(CLOUD_COMPACT_MARKET_DATA=True)
class ScannerReadinessDistinctCountTests(TestCase):
    @staticmethod
    def _company(symbol, *, active=True):
        return Company.objects.create(
            symbol=symbol,
            exchange="NSE",
            name=symbol,
            upstox_instrument_key=f"NSE_EQ|{symbol}",
            is_active=active,
            instrument_status=(
                Company.InstrumentStatus.ACTIVE
                if active else Company.InstrumentStatus.INACTIVE
            ),
        )

    @staticmethod
    def _candle(company, session):
        return CloudDailyCandle.objects.create(
            company=company,
            session_date=session,
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1_000,
        )

    @staticmethod
    def _quote(company):
        return CloudQuoteSnapshot.objects.create(
            company=company,
            last_price=101,
            open_price=100,
            high_price=102,
            low_price=99,
            previous_close=100,
            provider_timestamp=datetime(2026, 8, 20, 15, 30, tzinfo=IST),
        )

    def test_collect_counts_distinct_eligible_instruments_only(self):
        session = date(2026, 8, 20)
        first = self._company("AAA")
        second = self._company("BBB")
        inactive = self._company("OLD", active=False)
        for company in (first, second):
            self._candle(company, session - timedelta(days=1))
            self._candle(company, session)
            self._quote(company)
        # A newer inactive row and stale inactive quote must not select/count the session.
        self._candle(inactive, session + timedelta(days=1))
        self._quote(inactive)
        CloudBenchmarkCandle.objects.create(
            session_date=session,
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1_000,
        )

        snapshot = ScannerDataReadinessService.collect(
            now=datetime(2026, 8, 21, 10, 0, tzinfo=IST)
        )

        self.assertEqual(snapshot.active_eligible_instruments, 2)
        self.assertEqual(snapshot.latest_stock_session, session)
        self.assertEqual(snapshot.distinct_stock_instruments, 2)
        self.assertEqual(snapshot.distinct_quote_instruments, 2)
        self.assertEqual(snapshot.stock_coverage, 1.0)
        self.assertEqual(snapshot.quote_coverage, 1.0)
        self.assertEqual(ScannerDataReadinessService.failures(snapshot), [])
