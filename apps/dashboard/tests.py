from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.companies.models import Company
from apps.dashboard.services.dashboard_service import DashboardService
from apps.dashboard.services.stock_detail_service import StockDetailService
from apps.market.models import MarketOHLC, MarketQuote
from apps.scanner.engine.decision_engine import ScanReport, StockSnapshot, StrategyResult
from apps.scanner.models import PreBreakoutSetupOutcome


IST = ZoneInfo("Asia/Kolkata")


def sample_report(*, session=date(2026, 9, 4), symbol="ALPHA"):
    snapshot = StockSnapshot(
        symbol=symbol,
        company_name="Alpha Industries",
        sector="Industrials",
        industry="Machinery",
        last_price=110,
        open_price=105,
        high_price=112,
        low_price=104,
        previous_close=100,
        volume=120_000,
        week_52_high=120,
        rs_rating=84,
        distance_to_breakout_pct=1.2,
        atr_contracting=True,
        volume_dry_up=True,
        up_down_volume_ratio=1.7,
        accumulation_distribution_balance=18.2,
        liquidity_score=76,
        base_duration_sessions=42,
        base_high=112,
        base_low=99.5,
        base_depth_pct=11.5,
        breakout_level=112,
        data_quality_state="VALID",
        latest_daily_session=session,
        setup_lifecycle="BREAKOUT_READY",
    )
    return ScanReport(
        snapshot=snapshot,
        strategies=[StrategyResult("Minervini", True, 82, 10, ["Trend aligned"])],
        overall_score=82,
        passed_count=1,
        entry_zone=(109, 112),
        stop_loss=102,
        targets=[124],
        risk_reward=2.0,
        should_alert=True,
        is_pre_breakout=True,
        is_breakout=False,
        breakout_probability=78,
        resistance=112,
        support=102,
        distance_from_breakout=1.2,
        confidence_score=81,
        raw_prebreakout_score=80,
        prebreakout_score=80,
        prebreakout_classification="STRONG",
        component_scores={},
        positive_signals=["NEAR_PIVOT"],
        prebreakout_risk_flags=[],
        prebreakout_data_quality=[],
        prebreakout_applied_penalties={},
        prebreakout_applied_caps=[],
    )


class WebsiteAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="trader",
            email="trader@example.com",
            password="strong-password-123",
        )

    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/login/?next=/", fetch_redirect_response=False)

    def test_signup_creates_and_logs_in_user(self):
        response = self.client.post("/signup/", {
            "email": "new@example.com", "username": "new-trader",
            "password1": "Strong-pass-456", "password2": "Strong-pass-456",
        })
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(get_user_model().objects.filter(email="new@example.com").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_dashboard_and_logout_session_flow(self):
        response = self.client.post(
            "/login/",
            {"username": self.user.email, "password": "strong-password-123"},
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "QuantumStock Priority Stocks")
        self.assertNotContains(dashboard, "Guaranteed Buy")
        self.assertNotContains(dashboard, "Sure-shot")

        logout = self.client.post("/logout/")
        self.assertRedirects(logout, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class DashboardAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="api-trader",
            email="api@example.com",
            password="strong-password-123",
        )
        self.client.force_login(self.user)

    def test_home_api_schema_and_no_fake_market_values(self):
        response = self.client.get("/api/v1/dashboard/home/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "meta", "indices", "top_movers", "sectors", "breadth",
                "priority_stocks", "prebreakout_opportunities", "capabilities",
            },
        )
        self.assertEqual(payload["top_movers"]["gainers"], [])
        self.assertEqual(payload["top_movers"]["losers"], [])
        self.assertTrue(all(item["price"] is None for item in payload["indices"]["items"]))
        self.assertEqual(payload["capabilities"]["news"], "DATA_UNAVAILABLE")

    def test_home_api_rejects_anonymous_session(self):
        self.client.logout()
        response = self.client.get("/api/v1/dashboard/home/")
        self.assertIn(response.status_code, {401, 403})

    def test_three_persisted_indices_are_projected_without_company_rows(self):
        timestamp = datetime(2026, 9, 4, 15, 30, tzinfo=IST)
        definitions = [
            ("NIFTY 50", "NSE", "NSE_INDEX|Nifty 50", 25000),
            ("SENSEX", "BSE", "BSE_INDEX|SENSEX", 81000),
            ("NIFTY BANK", "NSE", "NSE_INDEX|Nifty Bank", 52000),
        ]
        for symbol, exchange, key, price in definitions:
            MarketQuote.objects.create(
                symbol=symbol, exchange=exchange, company_name=symbol,
                instrument_key=key, last_price=price, open_price=price - 100,
                high_price=price + 100, low_price=price - 200,
                previous_close=price - 50, change=50, change_percent=0.2,
                provider_timestamp=timestamp,
            )
        payload = DashboardService.home(
            now=datetime(2026, 9, 4, 17, 0, tzinfo=IST)
        )
        self.assertEqual(
            [item["price"] for item in payload["indices"]["items"]],
            [25000.0, 81000.0, 52000.0],
        )
        self.assertTrue(
            all(item["status"] == "MARKET_CLOSED" for item in payload["indices"]["items"])
        )

    def test_search_uses_persisted_companies_and_reports_unavailable_types(self):
        Company.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            isin="INE000A01001",
            upstox_instrument_key="NSE_EQ|INE000A01001",
            name="Alpha Industries",
            sector="Industrials",
            industry="Machinery",
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        response = self.client.get("/api/v1/dashboard/search/?q=Alpha")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["symbol"], "ALPHA")
        self.assertEqual(payload["results"][0]["url"], "/stock/ALPHA/")
        self.assertEqual(payload["capabilities"]["ipo"], "DATA_UNAVAILABLE")
        self.assertEqual(payload["capabilities"]["news"], "DATA_UNAVAILABLE")

    def test_movers_breadth_and_sectors_use_fresh_persisted_quotes(self):
        Company.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            isin="INE000A01001",
            upstox_instrument_key="NSE_EQ|INE000A01001",
            name="Alpha Industries",
            sector="Industrials",
            industry="Machinery",
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        MarketQuote.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            company_name="Alpha Industries",
            last_price=105,
            previous_close=100,
            change=5,
            change_percent=5,
            provider_timestamp=datetime(2026, 9, 4, 9, 59, tzinfo=IST),
        )
        with patch.object(DashboardService, "_load_reports", return_value=([], {}, None, "unavailable")):
            payload = DashboardService.home(
                now=datetime(2026, 9, 4, 10, 0, tzinfo=IST)
            )
        self.assertEqual(payload["top_movers"]["gainers"][0]["symbol"], "ALPHA")
        self.assertEqual(payload["breadth"]["advances"], 1)
        self.assertEqual(payload["breadth"]["coverage_percent"], 100.0)
        self.assertEqual(payload["sectors"]["items"][0]["sector"], "Industrials")

    def test_priority_and_prebreakout_sections_use_cached_report(self):
        Company.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            isin="INE000A01001",
            upstox_instrument_key="NSE_EQ|INE000A01001",
            name="Alpha Industries",
            sector="Industrials",
            industry="Machinery",
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        report = sample_report()
        now = datetime(2026, 9, 4, 17, 0, tzinfo=IST)
        with patch.object(
            DashboardService,
            "_load_reports",
            return_value=([report], {"scanner_session": date(2026, 9, 4)}, date(2026, 9, 4), None),
        ):
            payload = DashboardService.home(now=now)
        self.assertEqual(payload["priority_stocks"]["items"][0]["symbol"], "ALPHA")
        self.assertEqual(
            payload["prebreakout_opportunities"]["items"][0]["state"],
            "PRE-BREAKOUT READY",
        )
        self.assertEqual(
            payload["meta"]["scanner_stages"]["items"],
            [{"stage": "PRE-BREAKOUT READY", "count": 1}],
        )
        self.assertLessEqual(len(payload["priority_stocks"]["items"]), 6)
        self.assertLessEqual(len(payload["prebreakout_opportunities"]["items"]), 6)

    def test_dashboard_renders_reusable_scanner_card(self):
        report = sample_report()
        with patch.object(
            DashboardService,
            "_load_reports",
            return_value=([report], {}, date(2026, 9, 4), None),
        ):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Industries")
        self.assertContains(response, "PRE-BREAKOUT READY")
        self.assertContains(response, "Chart unavailable")

    def test_stale_scanner_session_is_never_presented_as_live(self):
        report = sample_report(session=date(2026, 9, 3))
        now = datetime(2026, 9, 4, 17, 0, tzinfo=IST)
        with patch.object(
            DashboardService,
            "_load_reports",
            return_value=([report], {}, date(2026, 9, 3), None),
        ):
            payload = DashboardService.home(now=now)
        self.assertEqual(payload["priority_stocks"]["status"], "STALE")
        self.assertEqual(payload["prebreakout_opportunities"]["status"], "STALE")


class StockDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="xray-trader",
            email="xray@example.com",
            password="strong-password-123",
        )
        self.client.force_login(self.user)
        self.company = Company.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            isin="INE000A01001",
            upstox_instrument_key="NSE_EQ|INE000A01001",
            name="Alpha Industries",
            sector="Industrials",
            industry="Machinery",
            provider_segment="NSE_EQ",
            provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        self.latest = datetime(2026, 9, 4, 15, 30, tzinfo=IST)
        MarketQuote.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            company=self.company,
            instrument_key=self.company.upstox_instrument_key,
            company_name=self.company.name,
            last_price=110,
            open_price=105,
            high_price=112,
            low_price=104,
            previous_close=100,
            change=10,
            change_percent=10,
            volume=120_000,
            provider_timestamp=self.latest,
            last_trade_time=self.latest,
        )

    def candle(self, *, days_ago, open_price, high, low, close, volume):
        return MarketOHLC.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            interval=MarketOHLC.Interval.D1,
            candle_time=self.latest - timedelta(days=days_ago),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

    def test_stock_page_route_serializes_only_real_persisted_candles(self):
        self.candle(days_ago=1, open_price=101, high=108, low=99, close=106, volume=1111)
        self.candle(days_ago=0, open_price=106, high=112, low=104, close=110, volume=2222)
        with patch.object(StockDetailService, "_load_report", return_value=(sample_report(), {})):
            response = self.client.get("/stock/ALPHA/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Industries")
        self.assertContains(response, "Real daily candlestick and volume chart")
        candles = response.context["stock"]["chart"]["candles"]
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["open"], 101.0)
        self.assertEqual(candles[1]["volume"], 2222)

    def test_time_range_filtering_uses_latest_persisted_session(self):
        self.candle(days_ago=100, open_price=90, high=92, low=88, close=91, volume=900)
        self.candle(days_ago=5, open_price=100, high=104, low=99, close=103, volume=1000)
        with patch.object(StockDetailService, "_load_report", return_value=(None, {})):
            one_month = StockDetailService.detail("ALPHA", range_code="1M")
            maximum = StockDetailService.detail("ALPHA", range_code="MAX")
        self.assertEqual([item["close"] for item in one_month["chart"]["candles"]], [103.0])
        self.assertEqual([item["close"] for item in maximum["chart"]["candles"]], [91.0, 103.0])

    def test_missing_data_is_explicit_and_no_candles_are_generated(self):
        empty = Company.objects.create(
            symbol="EMPTY",
            exchange="NSE",
            upstox_instrument_key="NSE_EQ|INE000A01002",
            name="Empty Industries",
            provider_segment="NSE_EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )
        with patch.object(StockDetailService, "_load_report", return_value=(None, {})):
            payload = StockDetailService.detail(empty.symbol)
            response = self.client.get("/stock/EMPTY/")
        self.assertEqual(payload["quote"]["status"], "DATA_UNAVAILABLE")
        self.assertEqual(payload["chart"]["status"], "DATA_UNAVAILABLE")
        self.assertEqual(payload["chart"]["candles"], [])
        self.assertEqual(payload["scanner"]["status"], "DATA_UNAVAILABLE")
        self.assertContains(response, "No persisted daily OHLC candles exist")

    def test_scanner_metrics_and_levels_are_mapped_without_recalculation(self):
        report = sample_report()
        with patch.object(StockDetailService, "_load_report", return_value=(report, {})):
            payload = StockDetailService.detail("ALPHA")
        scanner = payload["scanner"]
        self.assertEqual(scanner["lifecycle"], "PRE-BREAKOUT READY")
        self.assertEqual(scanner["metrics"]["rs_rating"], 84)
        self.assertEqual(scanner["metrics"]["quantum_score"], 82)
        self.assertEqual(scanner["levels"]["pivot"], 112.0)
        self.assertEqual(scanner["levels"]["support"], 102.0)
        self.assertEqual(scanner["levels"]["base_high"], 112.0)
        self.assertEqual(scanner["levels"]["base_low"], 99.5)

    def test_chart_marker_mapping_uses_persisted_outcome(self):
        PreBreakoutSetupOutcome.objects.create(
            symbol="ALPHA",
            exchange="NSE",
            evaluation_session=date(2026, 8, 28),
            evaluation_price=104,
            pivot=108,
            raw_score=70,
            final_score=68,
            classification="WATCH",
            data_quality_state="VALID",
            breakout_occurred=True,
            breakout_session=date(2026, 9, 2),
        )
        with patch.object(StockDetailService, "_load_report", return_value=(sample_report(), {})):
            payload = StockDetailService.detail("ALPHA")
        self.assertIn(
            {"date": "2026-09-02", "state": "BREAKOUT CONFIRMED"},
            payload["markers"],
        )
        self.assertIn(
            {"date": "2026-09-04", "state": "PRE-BREAKOUT READY"},
            payload["markers"],
        )

    def test_card_links_to_stock_xray_and_api_rejects_bad_range(self):
        with patch.object(
            DashboardService,
            "_load_reports",
            return_value=([sample_report()], {}, date(2026, 9, 4), None),
        ):
            dashboard = self.client.get("/")
        self.assertContains(dashboard, 'data-stock-url="/stock/ALPHA/"')
        self.assertContains(dashboard, 'href="/stock/ALPHA/"')
        response = self.client.get("/api/v1/dashboard/stocks/ALPHA/?range=INVALID")
        self.assertEqual(response.status_code, 400)
