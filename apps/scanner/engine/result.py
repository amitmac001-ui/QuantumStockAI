from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class ScanContext:

    symbol: str

    candles: list

    dataframe: pd.DataFrame | None = None

    quote: Any = None


@dataclass(slots=True)
class ScanResult:

    strategy: str

    signal: str

    score: float

    confidence: float

    reason: str

    metadata: dict = field(default_factory=dict)