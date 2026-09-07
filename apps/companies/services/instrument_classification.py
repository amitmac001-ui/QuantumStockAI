from __future__ import annotations

from apps.companies.models import Company


class InstrumentClassificationService:
    """Classify securities only from authoritative provider identity fields."""

    EQUITY_SERIES = frozenset({"EQ", "BE", "BZ", "SM", "ST"})
    DEBT_TYPES = frozenset({"SG", "GS", "TB", "GB", "RR"})

    @classmethod
    def classify(
        cls,
        *,
        segment: str,
        instrument_type: str,
        security_type: str,
        isin: str,
    ) -> str:
        segment = str(segment or "").strip().upper()
        instrument_type = str(instrument_type or "").strip().upper()
        security_type = str(security_type or "").strip().upper()
        isin = str(isin or "").strip().upper()

        if segment != "NSE_EQ":
            return Company.SecurityCategory.OTHER
        if instrument_type in cls.EQUITY_SERIES and isin.startswith("INE"):
            return Company.SecurityCategory.OPERATING_EQUITY
        if instrument_type in cls.EQUITY_SERIES and isin.startswith("INF"):
            return Company.SecurityCategory.ETF
        if (
            instrument_type in cls.DEBT_TYPES
            or instrument_type.startswith("N")
            or security_type == "DEBT"
        ):
            return Company.SecurityCategory.DEBT
        return Company.SecurityCategory.OTHER
