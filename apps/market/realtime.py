import hashlib


def quote_group(instrument: str) -> str:
    """Return a Channels-safe, non-sensitive group for one market instrument."""
    normalized = str(instrument or "").strip().upper()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"market.quote.{digest}"
