"""DB-independent Upstox -> LIVE_MARKET lightweight cloud refresh."""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from datetime import datetime, time as clock_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import gspread
import requests
from google.oauth2.service_account import Credentials

IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN, NSE_CLOSE = clock_time(9, 15), clock_time(15, 30)
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
QUOTES_URL = "https://api.upstox.com/v2/market-quote/quotes"
SCOPES = ("https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive")


def log(event: str, **values: Any) -> None:
    print(json.dumps({"event": event, **values}, sort_keys=True), flush=True)


def load_config() -> dict[str, Any]:
    raw = os.environ.get("CLOUD_SYNC_CONFIG", "").strip()
    if not raw:
        raise RuntimeError("CLOUD_SYNC_CONFIG secret is not configured")
    config = json.loads(raw)
    required = ("upstox_access_token", "google_sheet_id", "google_service_account")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"CLOUD_SYNC_CONFIG is missing: {', '.join(missing)}")
    return config


def session_is_open(now: datetime) -> bool:
    local_time = now.time().replace(tzinfo=None)
    return now.weekday() < 5 and NSE_OPEN <= local_time <= NSE_CLOSE


def get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=45, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Provider request failed: {type(last_error).__name__}") from last_error


def open_sheets(config: dict[str, Any]):
    credentials = Credentials.from_service_account_info(config["google_service_account"], scopes=SCOPES)
    book = gspread.authorize(credentials).open_by_key(config["google_sheet_id"])
    return book.worksheet("LIVE_MARKET"), book.worksheet("LIVE_STATUS")


def read_verified_rows(live_sheet):
    rows = live_sheet.get_all_values()
    if not rows or len(rows[0]) < 25 or rows[0][1].strip() != "Symbol":
        raise RuntimeError("LIVE_MARKET layout is not the verified 25+ column layout")
    symbols = [row[1].strip().upper() for row in rows[1:] if len(row) > 1 and row[1].strip()]
    if len(symbols) != len(set(symbols)):
        raise RuntimeError("Duplicate LIVE_MARKET symbols detected; publish stopped")
    return rows, symbols


def load_instruments(session: requests.Session, wanted: set[str]) -> dict[str, str]:
    instruments = json.loads(gzip.decompress(get(session, INSTRUMENTS_URL).content))
    mapped: dict[str, str] = {}
    for item in instruments:
        symbol = str(item.get("trading_symbol") or item.get("tradingsymbol") or "").upper()
        key = str(item.get("instrument_key") or "")
        if symbol in wanted and key and item.get("segment") == "NSE_EQ":
            mapped.setdefault(symbol, key)
    return mapped


def batches(values: list[str], size: int = 200):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    if numeric > 10_000_000_000:
        numeric /= 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc)


def fetch_fresh_quotes(session, token: str, mapping: dict[str, str], now: datetime):
    key_to_symbol = {key: symbol for symbol, key in mapping.items()}
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    output: dict[str, dict[str, Any]] = {}
    for batch in batches(list(key_to_symbol)):
        payload = get(session, QUOTES_URL, headers=headers, params={"instrument_key": ",".join(batch)}).json()
        for response_key, item in (payload.get("data") or {}).items():
            instrument_key = str(item.get("instrument_token") or "")
            symbol = key_to_symbol.get(instrument_key)
            if not symbol:
                symbol = str(item.get("symbol") or response_key.replace("|", ":").rsplit(":", 1)[-1]).upper()
            if symbol not in mapping:
                continue
            provider_time = parse_timestamp(item.get("timestamp"))
            if provider_time is None:
                continue
            provider_ist = provider_time.astimezone(IST)
            if provider_ist.date() != now.date():
                continue
            if provider_ist > now + timedelta(minutes=5) or now - provider_ist > timedelta(minutes=20):
                continue
            output[symbol] = {**item, "_provider_time": provider_time}
    return output


def numeric(value: Any):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not (parsed == parsed and abs(parsed) != float("inf")):
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 4)


def stamp(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def update_row(row: list[Any], item: dict[str, Any], now: datetime) -> None:
    row.extend([""] * max(25 - len(row), 0))
    ohlc = item.get("ohlc") or {}
    previous_close = numeric(ohlc.get("close"))
    net_change = numeric(item.get("net_change"))
    change_percent = None
    if net_change is not None and previous_close not in (None, 0):
        change_percent = round(float(net_change) / float(previous_close) * 100, 4)
    values = (
        numeric(item.get("last_price")), numeric(ohlc.get("open")),
        numeric(ohlc.get("high")), numeric(ohlc.get("low")), previous_close,
        numeric(item.get("volume")), net_change, change_percent,
    )
    for column, value in zip(range(4, 12), values):
        if value is not None:
            row[column] = value
    row[22] = stamp(item["_provider_time"])
    last_trade = parse_timestamp(item.get("last_trade_time"))
    if last_trade is not None:
        row[23] = stamp(last_trade)
    row[24] = stamp(now)


def run(dry_run: bool = False) -> int:
    now = datetime.now(IST)
    if not session_is_open(now) and not dry_run:
        log("SKIPPED_OUTSIDE_NSE_SESSION", now=stamp(now))
        return 0
    config = load_config()
    live_sheet, status_sheet = open_sheets(config)
    rows, symbols = read_verified_rows(live_sheet)
    if not symbols:
        raise RuntimeError("LIVE_MARKET has no symbols")
    with requests.Session() as session:
        mapping = load_instruments(session, set(symbols))
        if len(mapping) / len(symbols) < 0.80:
            raise RuntimeError(f"Instrument mapping coverage too low: {len(mapping) / len(symbols):.1%}")
        if dry_run:
            sample_symbol, sample_key = next(iter(mapping.items()))
            headers = {"Accept": "application/json", "Authorization": f"Bearer {config['upstox_access_token']}"}
            payload = get(session, QUOTES_URL, headers=headers, params={"instrument_key": sample_key}).json()
            sample = next(iter((payload.get("data") or {}).values()), None)
            provider_time = parse_timestamp((sample or {}).get("timestamp"))
            if provider_time is None:
                raise RuntimeError("Sample quote has no provider timestamp")
            log("DRY_RUN_OK", sheet_rows=len(symbols), mapped=len(mapping), sample_symbol=sample_symbol, provider_timestamp=stamp(provider_time))
            return 0
        quotes = fetch_fresh_quotes(session, config["upstox_access_token"], mapping, now)
    if len(quotes) / len(symbols) < 0.80:
        raise RuntimeError(f"Fresh quote coverage too low: {len(quotes) / len(symbols):.1%}")
    symbol_rows = {row[1].strip().upper(): row for row in rows[1:] if len(row) > 1 and row[1].strip()}
    for symbol, quote in quotes.items():
        update_row(symbol_rows[symbol], quote, now)

    ordered = [symbol_rows[symbol] for symbol in symbols]
    live_sheet.batch_update([
        {"range": f"E2:L{len(ordered) + 1}", "values": [row[4:12] for row in ordered]},
        {"range": f"W2:Y{len(ordered) + 1}", "values": [row[22:25] for row in ordered]},
    ], value_input_option="USER_ENTERED")
    latest = max(item["_provider_time"] for item in quotes.values())
    status_sheet.update("A1:B7", [
        ["Key", "Value"], ["status", "HEALTHY"], ["worksheet", "LIVE_MARKET"],
        ["row_count", len(symbols)], ["last_successful_publish", stamp(now)],
        ["latest_market_timestamp", stamp(latest)], ["update_mode", "GITHUB_ACTIONS_FAST_QUOTES"],
    ], value_input_option="RAW")
    log("SYNC_SUCCESS", sheet_rows=len(symbols), mapped=len(mapping), fresh_quotes=len(quotes), latest_market_timestamp=stamp(latest))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return run(dry_run=args.dry_run)
    except Exception as exc:
        log("SYNC_FAILED", error_type=type(exc).__name__, error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())