from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase, override_settings

from apps.market.consumers import MarketConsumer
from apps.market.realtime import quote_group
from apps.companies.models import Company
from apps.market.models import MarketQuote
from apps.market.services.market_status_service import MarketStatusService
from apps.market.services.quote_sync import QuoteSyncService


IST = ZoneInfo("Asia/Kolkata")
IN_MEMORY_CHANNELS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class MarketStatusServiceTests(SimpleTestCase):
    def test_live_requires_a_fresh_provider_timestamp(self):
        now = datetime(2026, 9, 4, 10, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(
            now - timedelta(seconds=60)
        )
        self.assertEqual(status.status, "LIVE")

    def test_stale_provider_timestamp_is_not_live_during_trading_window(self):
        now = datetime(2026, 9, 4, 10, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(
            now - timedelta(minutes=10)
        )
        self.assertEqual(status.status, "STALE")

    def test_latest_completed_snapshot_is_market_closed_after_hours(self):
        now = datetime(2026, 9, 4, 17, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(
            datetime(2026, 9, 4, 15, 30, tzinfo=IST)
        )
        self.assertEqual(status.status, "MARKET_CLOSED")

    def test_weekend_snapshot_uses_exchange_trade_session(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(
            now - timedelta(minutes=1),
            session=date(2026, 9, 4),
        )
        self.assertEqual(status.status, "MARKET_CLOSED")

    def test_weekend_provider_refresh_is_market_closed_not_live_or_stale(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(
            now - timedelta(minutes=1),
            session=date(2026, 9, 6),
        )
        self.assertEqual(status.status, "MARKET_CLOSED")

    def test_missing_timestamp_is_data_unavailable(self):
        now = datetime(2026, 9, 4, 10, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_provider_timestamp(None)
        self.assertEqual(status.status, "DATA_UNAVAILABLE")
        self.assertIsNone(status.provider_timestamp)

    def test_old_scanner_session_is_stale(self):
        now = datetime(2026, 9, 4, 17, 0, tzinfo=IST)
        status = MarketStatusService(now=now).for_scanner_session(date(2026, 9, 3))
        self.assertEqual(status.status, "STALE")


class QuotePayloadTests(SimpleTestCase):
    def test_wire_payload_contains_timestamps_but_no_credentials(self):
        timestamp = datetime(2026, 9, 4, 10, 0, tzinfo=IST)
        payload = QuoteSyncService._wire_quote(
            {
                "symbol": "ALPHA",
                "instrument_key": "NSE_EQ|INE000A01001",
                "last_price": 100,
                "provider_state": "MARKET_CLOSED",
                "provider_timestamp": timestamp,
                "last_trade_time": timestamp,
            }
        )
        self.assertEqual(payload["provider_timestamp"], timestamp.isoformat())
        self.assertNotIn("access_token", payload)
        self.assertNotIn("client_secret", payload)
        self.assertNotIn("company", payload)
        self.assertTrue({
            "symbol", "instrument_key", "last_price",
            "provider_timestamp", "last_trade_time", "provider_state",
        }.issubset(payload))


class QuoteSyncPersistenceTests(TestCase):
    @staticmethod
    def item(symbol, price=105):
        return SimpleNamespace(
            symbol=symbol,
            last_price=price,
            net_change=5,
            volume=12_345,
            timestamp="2026-09-04T15:30:00+05:30",
            last_trade_time=1788516000000,
            ohlc=SimpleNamespace(open=101, high=106, low=100, close=100),
        )

    @staticmethod
    def company(symbol, key):
        return Company.objects.create(
            symbol=symbol, exchange="NSE", name=f"{symbol} Limited",
            isin=key.split("|")[-1], upstox_instrument_key=key,
            provider_segment="NSE_EQ", provider_instrument_type="EQ",
            provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
        )

    def test_complete_normalized_quote_is_persisted_before_broadcast(self):
        company = self.company("ALPHA", "NSE_EQ|INE000000001")
        client = Mock()
        client.quote.return_value = SimpleNamespace(
            data={company.upstox_instrument_key: self.item("ALPHA")}
        )
        service = QuoteSyncService(client=client, channel_layer=False, sleep=lambda _: None)
        result = service.sync([company.upstox_instrument_key])
        quote = MarketQuote.objects.get(symbol="ALPHA")
        self.assertEqual(result.quotes_updated, 1)
        self.assertEqual(quote.company, company)
        self.assertEqual(quote.instrument_key, company.upstox_instrument_key)
        self.assertEqual(float(quote.last_price), 105)
        self.assertEqual(float(quote.open_price), 101)
        self.assertEqual(float(quote.high_price), 106)
        self.assertEqual(float(quote.low_price), 100)
        self.assertEqual(float(quote.previous_close), 100)
        self.assertEqual(float(quote.change), 5)
        self.assertEqual(float(quote.change_percent), 5)
        self.assertEqual(quote.volume, 12_345)
        self.assertIsNotNone(quote.provider_timestamp)
        self.assertIsNotNone(quote.last_trade_time)

    def test_failed_batch_does_not_abort_later_batch(self):
        first = self.company("AAA", "NSE_EQ|INE000000001")
        second = self.company("ZZZ", "NSE_EQ|INE000000002")

        class ProviderError(Exception):
            status = 400

        client = Mock()
        client.quote.side_effect = [
            ProviderError("invalid first batch"),
            SimpleNamespace(data={second.upstox_instrument_key: self.item("ZZZ")}),
        ]
        service = QuoteSyncService(client=client, channel_layer=False, sleep=lambda _: None)
        service.BATCH_SIZE = 1
        result = service.sync([first.upstox_instrument_key, second.upstox_instrument_key])
        self.assertEqual(result.batches_failed, 1)
        self.assertEqual(result.quotes_updated, 1)
        self.assertFalse(MarketQuote.objects.filter(symbol="AAA").exists())
        self.assertTrue(MarketQuote.objects.filter(symbol="ZZZ").exists())

    def test_three_indices_persist_without_fake_company_rows(self):
        client = Mock()
        client.quote.return_value = SimpleNamespace(data={
            key: self.item(symbol)
            for key, (symbol, _exchange, _name) in QuoteSyncService.INDEX_INSTRUMENTS.items()
        })
        service = QuoteSyncService(client=client, channel_layer=False, sleep=lambda _: None)
        result = service.sync(list(QuoteSyncService.INDEX_INSTRUMENTS))
        self.assertEqual(result.quotes_updated, 3)
        self.assertEqual(MarketQuote.objects.filter(company__isnull=True).count(), 3)
        self.assertSetEqual(
            set(MarketQuote.objects.values_list("instrument_key", flat=True)),
            set(QuoteSyncService.INDEX_INSTRUMENTS),
        )


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS)
class MarketWebSocketTests(SimpleTestCase):
    def test_anonymous_connection_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(MarketConsumer.as_asgi(), "/ws/market/")
            communicator.scope["user"] = AnonymousUser()
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_authenticated_tick_uses_normalized_schema(self):
        async def scenario():
            communicator = WebsocketCommunicator(MarketConsumer.as_asgi(), "/ws/market/")
            communicator.scope["user"] = SimpleNamespace(is_authenticated=True)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            connected_message = await communicator.receive_json_from()
            self.assertEqual(connected_message["type"], "market.connected")

            await communicator.send_json_to(
                {
                    "type": "market.subscribe",
                    "instruments": ["NSE_EQ|INE000A01001"],
                }
            )
            subscribed = await communicator.receive_json_from()
            self.assertEqual(subscribed["type"], "market.subscribed")

            await get_channel_layer().group_send(
                quote_group("NSE_EQ|INE000A01001"),
                {
                    "type": "market_message",
                    "data": {
                        "symbol": "ALPHA",
                        "instrument_key": "NSE_EQ|INE000A01001",
                        "last_price": 100.5,
                        "provider_timestamp": "2026-09-04T10:00:00+05:30",
                    },
                },
            )
            message = await communicator.receive_json_from()
            self.assertEqual(message["type"], "market.tick")
            self.assertEqual(message["version"], 1)
            self.assertEqual(message["data"]["symbol"], "ALPHA")
            self.assertNotIn("access_token", message["data"])
            await communicator.disconnect()

        async_to_sync(scenario)()
