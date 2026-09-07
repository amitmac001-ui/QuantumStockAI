from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.companies.models import Company
from apps.market.providers.upstox_client import UpstoxClient
from apps.market.services.market_service import MarketService
from apps.market.services.quote_normalizer import QuoteNormalizer
from apps.market.realtime import quote_group

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QuoteSyncResult:
    requested: int = 0
    batches: int = 0
    batches_failed: int = 0
    quotes_updated: int = 0
    skipped: int = 0
    failed_instruments: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.quotes_updated / self.requested if self.requested else 0.0


class QuoteSyncService:
    BATCH_SIZE = 200
    MAX_RETRIES = 3
    INDEX_INSTRUMENTS = {
        "NSE_INDEX|Nifty 50": ("NIFTY 50", "NSE", "NIFTY 50"),
        "BSE_INDEX|SENSEX": ("SENSEX", "BSE", "SENSEX"),
        "NSE_INDEX|Nifty Bank": ("NIFTY BANK", "NSE", "NIFTY BANK"),
    }

    def __init__(self, *, client=None, market=None, channel_layer=None, sleep=None):
        self.client = client or UpstoxClient()
        self.market = market or MarketService()
        self.channel_layer = (
            get_channel_layer() if channel_layer is None else channel_layer
        )
        self.sleep = sleep or time.sleep

    @staticmethod
    def _chunks(items, size):
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @staticmethod
    def _wire_quote(quote):
        payload = {
            key: value for key, value in dict(quote).items()
            if key != "company"
        }
        for field in ("provider_timestamp", "last_trade_time"):
            value = payload.get(field)
            payload[field] = value.isoformat() if value else None
        return payload

    def _request(self, instrument_keys: list[str]):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self.client.quote(",".join(instrument_keys))
            except Exception as exc:
                status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
                try:
                    status = int(status) if status is not None else None
                except (TypeError, ValueError):
                    status = None
                retryable = status is None or status == 429 or status >= 500
                if attempt >= self.MAX_RETRIES or not retryable:
                    raise
                self.sleep(min(2 ** (attempt - 1), 8))

    @classmethod
    def default_instruments(cls) -> list[str]:
        equities = list(
            Company.scanner_eligible().values_list("upstox_instrument_key", flat=True)
        )
        return [*equities, *cls.INDEX_INSTRUMENTS]

    @classmethod
    def _identities(cls, instrument_keys: list[str]):
        companies = {
            company.upstox_instrument_key: company
            for company in Company.objects.filter(
                upstox_instrument_key__in=instrument_keys
            ).only("id", "symbol", "exchange", "name", "upstox_instrument_key")
        }
        identities = {}
        for key in instrument_keys:
            company = companies.get(key)
            if company:
                identities[key] = (company.symbol, company.exchange, company.name, company)
            elif key in cls.INDEX_INSTRUMENTS:
                symbol, exchange, name = cls.INDEX_INSTRUMENTS[key]
                identities[key] = (symbol, exchange, name, None)
        return identities

    @staticmethod
    def _response_item_for_key(data, instrument_key, symbol):
        for candidate in (instrument_key, instrument_key.replace("|", ":")):
            if candidate in data:
                return candidate, data[candidate]
        wanted = symbol.upper()
        for response_key, item in data.items():
            item_symbol = str(getattr(item, "symbol", "") or "").strip().upper()
            response_symbol = str(response_key).split(":")[-1].upper()
            if item_symbol == wanted or response_symbol == wanted:
                return response_key, item
        return None, None

    def sync(self, instruments=None) -> QuoteSyncResult:
        instrument_keys = list(dict.fromkeys(instruments or self.default_instruments()))
        result = QuoteSyncResult(requested=len(instrument_keys))
        identities = self._identities(instrument_keys)

        for batch in self._chunks(instrument_keys, self.BATCH_SIZE):
            result.batches += 1
            try:
                response = self._request(batch)
            except Exception as exc:
                result.batches_failed += 1
                result.failed_instruments += len(batch)
                result.failures.append(
                    f"batch_size={len(batch)} error={type(exc).__name__}"
                )
                logger.exception(
                    "Upstox quote batch failed; continuing with remaining batches"
                )
                continue

            data = getattr(response, "data", None) or {}
            quotes = []
            for instrument_key in batch:
                identity = identities.get(instrument_key)
                if identity is None:
                    result.skipped += 1
                    continue
                symbol, exchange, company_name, company = identity
                response_key, item = self._response_item_for_key(
                    data, instrument_key, symbol
                )
                if item is None:
                    result.skipped += 1
                    continue
                try:
                    quote = QuoteNormalizer.normalize(
                        response_key=str(response_key),
                        item=item,
                        instrument_key=instrument_key,
                        symbol_hint=symbol,
                        company=company,
                        company_name=company_name,
                        exchange=exchange,
                    )
                    if quote["last_price"] <= 0:
                        result.skipped += 1
                        continue
                    quotes.append(quote)
                except Exception:
                    result.failed_instruments += 1
                    logger.exception("Quote normalization failed for %s", instrument_key)

            if not quotes:
                continue
            self.market.bulk_save(quotes)
            result.quotes_updated += len(quotes)
            if self.channel_layer:
                async_to_sync(self._broadcast)(
                    self.channel_layer,
                    [self._wire_quote(quote) for quote in quotes],
                )
        return result

    @staticmethod
    async def _broadcast(channel_layer, wire_quotes):
        await asyncio.gather(
            *(
                channel_layer.group_send(
                    quote_group(quote.get("instrument_key") or quote.get("symbol")),
                    {"type": "market_message", "data": quote},
                )
                for quote in wire_quotes
            )
        )
