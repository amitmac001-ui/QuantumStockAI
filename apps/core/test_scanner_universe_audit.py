from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.companies.models import Company
from apps.core.services.scanner_universe_audit import ScannerUniverseAuditService
from apps.market.models import CloudDailyCandle, CloudQuoteSnapshot


class ScannerUniverseAuditTests(TestCase):
    @staticmethod
    def _company(
        symbol: str,
        *,
        exchange: str = "NSE",
        key: str = "NSE_EQ|SHARED",
        active: bool = True,
        status: str = Company.InstrumentStatus.ACTIVE,
        series: str = "EQ",
    ) -> Company:
        return Company.objects.create(
            symbol=symbol,
            exchange=exchange,
            name=symbol,
            isin="INE002A01018",
            upstox_instrument_key=key,
            is_active=active,
            instrument_status=status,
            series=series,
        )

    @staticmethod
    def _candle(company: Company, session: date) -> None:
        CloudDailyCandle.objects.create(
            company=company,
            session_date=session,
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1_000,
        )

    @staticmethod
    def _quote(company: Company) -> None:
        CloudQuoteSnapshot.objects.create(
            company=company,
            last_price=101,
            open_price=100,
            high_price=102,
            low_price=99,
            previous_close=100,
        )

    def setUp(self):
        self.stock_only = self._company("AAA")
        self.quote_only = self._company("BBB")
        self._company(
            "OLD",
            active=False,
            status=Company.InstrumentStatus.INACTIVE,
            key="NSE_EQ|OLD",
        )
        self._company("BSECO", exchange="BSE", key="BSE_EQ|BSECO")
        self._company("NOKEY", key="")
        self._candle(self.stock_only, date(2026, 8, 19))
        self._candle(self.stock_only, date(2026, 8, 20))
        self._quote(self.quote_only)

    def test_counts_distinct_eligible_instruments_and_data_intersections(self):
        audit = ScannerUniverseAuditService.collect()

        self.assertEqual(audit["company_rows"]["total"], 5)
        self.assertEqual(
            audit["current_eligibility"]["company_rows_matching_rule"], 2
        )
        self.assertEqual(
            audit["current_eligibility"]["distinct_symbols_matching_rule"], 2
        )
        self.assertEqual(
            audit["current_eligibility"]["distinct_instrument_keys_matching_rule"], 1
        )
        self.assertEqual(
            audit["current_eligibility"]["company_rows_with_nse_eq_key"], 2
        )
        self.assertEqual(
            audit["identity_counts"]["duplicate_instrument_keys"]["groups"], 1
        )
        market_data = audit["persisted_market_data"]
        self.assertEqual(market_data["stock_data_intersection_with_eligible"], 1)
        self.assertEqual(market_data["quote_data_intersection_with_eligible"], 1)
        self.assertEqual(market_data["eligible_stock_without_quote"], 1)
        self.assertEqual(market_data["eligible_quote_without_stock"], 1)
        self.assertEqual(market_data["eligible_with_neither_stock_nor_quote"], 0)
        self.assertEqual(market_data["eligible_stock_instruments_on_latest_session"], 1)

    def test_collect_executes_select_queries_only(self):
        before = list(
            Company.objects.order_by("symbol").values_list(
                "symbol", "is_active", "instrument_status", "updated_at"
            )
        )
        with CaptureQueriesContext(connection) as queries:
            ScannerUniverseAuditService.collect()
        after = list(
            Company.objects.order_by("symbol").values_list(
                "symbol", "is_active", "instrument_status", "updated_at"
            )
        )

        self.assertEqual(before, after)
        forbidden = ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "CREATE ")
        mutating_queries = [
            query["sql"] for query in queries.captured_queries
            if any(token in query["sql"].upper() for token in forbidden)
        ]
        self.assertEqual(mutating_queries, [])

    def test_indian_isin_checksum_validation_is_explicit(self):
        self.assertTrue(
            ScannerUniverseAuditService._is_checksum_valid_isin("INE002A01018")
        )
        self.assertFalse(
            ScannerUniverseAuditService._is_checksum_valid_isin("INE002A01019")
        )
