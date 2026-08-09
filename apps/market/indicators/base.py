from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class Indicator(ABC):
    """
    Base class for all indicators.
    """

    name: str = ""

    @abstractmethod
    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Calculate indicator.
        """
        raise NotImplementedError

    def validate(
        self,
        df: pd.DataFrame,
    ) -> None:
        required = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        missing = [
            col
            for col in required
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing columns: {missing}"
            )

    def __call__(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        self.validate(df)

        return self.calculate(df)