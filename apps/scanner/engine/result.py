from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ScanContext:

    symbol: str

    candles: list

    quote: Any = None


@dataclass(slots=True)
class ScanResult:

    strategy: str

    signal: str

    score: float

    confidence: float

    reason: str

    metadata: dict = field(default_factory=dict)
