import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.market.realtime import quote_group


class MarketConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.subscriptions = set()
        self.subscription_groups = set()

        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "market.connected",
                    "version": 1,
                    "sent_at": timezone.now().isoformat(),
                    "data": {"status": "CONNECTED"},
                }
            )
        )

    async def disconnect(self, close_code):
        if hasattr(self, "subscription_groups"):
            for group in self.subscription_groups:
                await self.channel_layer.group_discard(group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            message = json.loads(text_data or "{}")
        except (TypeError, ValueError):
            await self.close(code=4400)
            return
        if message.get("type") != "market.subscribe":
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "market.error",
                        "version": 1,
                        "sent_at": timezone.now().isoformat(),
                        "data": {"code": "UNSUPPORTED_MESSAGE"},
                    }
                )
            )
            return
        instruments = message.get("instruments") or []
        if not isinstance(instruments, list) or len(instruments) > 100:
            await self.close(code=4400)
            return
        subscriptions = {
            str(instrument).strip().upper()
            for instrument in instruments
            if isinstance(instrument, str) and str(instrument).strip()
        }
        groups = {quote_group(instrument) for instrument in subscriptions}
        for group in self.subscription_groups - groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        for group in groups - self.subscription_groups:
            await self.channel_layer.group_add(group, self.channel_name)
        self.subscriptions = subscriptions
        self.subscription_groups = groups
        await self.send(
            text_data=json.dumps(
                {
                    "type": "market.subscribed",
                    "version": 1,
                    "sent_at": timezone.now().isoformat(),
                    "data": {"count": len(self.subscriptions)},
                }
            )
        )

    async def market_message(self, event):
        data = dict(event.get("data") or {})
        symbol = str(data.get("symbol") or "").upper()
        instrument_key = str(data.get("instrument_key") or "").upper()
        if self.subscriptions and not self.subscriptions.intersection(
            {symbol, instrument_key}
        ):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "market.tick",
                    "version": 1,
                    "sent_at": timezone.now().isoformat(),
                    "data": data,
                }
            )
        )
