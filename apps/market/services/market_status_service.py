from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.core.services.scanner_data_readiness import ScannerDataReadinessService


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class DataFreshness:
    status: str
    reason: str
    provider_timestamp: str | None
    age_seconds: int | None
    session: str | None
    expected_latest_completed_session: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class MarketStatusService:
    """Conservative, provider-timestamp-based market freshness decisions."""

    LIVE = "LIVE"
    STALE = "STALE"
    MARKET_CLOSED = "MARKET_CLOSED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    ALLOWED_STATES = frozenset({LIVE, STALE, MARKET_CLOSED, DATA_UNAVAILABLE})

    MARKET_OPEN = time(9, 15)
    MARKET_CLOSE = time(15, 30)
    CLOCK_SKEW_TOLERANCE_SECONDS = 300

    def __init__(self, *, now: datetime | None = None):
        current = now or timezone.now()
        if timezone.is_naive(current):
            current = timezone.make_aware(current, IST)
        self.now = current.astimezone(IST)
        self.stale_after_seconds = int(
            getattr(settings, "MARKET_DATA_STALE_AFTER_SECONDS", 300)
        )

    @property
    def is_trading_weekday(self) -> bool:
        return self.now.weekday() < 5

    @property
    def is_trading_window(self) -> bool:
        return (
            self.is_trading_weekday
            and self.MARKET_OPEN <= self.now.time() <= self.MARKET_CLOSE
        )

    @property
    def expected_latest_completed_session(self) -> date:
        # The project has no authoritative exchange-holiday calendar. The existing
        # readiness service deliberately supplies a conservative weekday estimate.
        return ScannerDataReadinessService.expected_latest_completed_session(self.now)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if timezone.is_naive(value):
            return timezone.make_aware(value, IST)
        return value

    def for_provider_timestamp(
        self,
        provider_timestamp: datetime | None,
        *,
        session: date | None = None,
    ) -> DataFreshness:
        expected = self.expected_latest_completed_session
        timestamp = self._aware(provider_timestamp)
        if timestamp is None:
            return DataFreshness(
                status=self.DATA_UNAVAILABLE,
                reason="Provider timestamp unavailable; live freshness cannot be verified.",
                provider_timestamp=None,
                age_seconds=None,
                session=session.isoformat() if session else None,
                expected_latest_completed_session=expected.isoformat(),
            )

        local_timestamp = timestamp.astimezone(IST)
        age_seconds = int((self.now - local_timestamp).total_seconds())
        if age_seconds < -self.CLOCK_SKEW_TOLERANCE_SECONDS:
            status = self.STALE
            reason = "Provider timestamp is ahead of the application clock."
        elif self.is_trading_window:
            status = (
                self.LIVE
                if age_seconds <= self.stale_after_seconds
                else self.STALE
            )
            reason = (
                "Provider timestamp is within the live freshness threshold."
                if status == self.LIVE
                else "Provider timestamp is older than the live freshness threshold."
            )
        elif (
            session == expected
            or local_timestamp.date() == expected
            or (
                not self.is_trading_window
                and local_timestamp.date() == self.now.date()
            )
            or (
                self.is_trading_weekday
                and self.now.time() > self.MARKET_CLOSE
                and local_timestamp.date() == self.now.date()
            )
        ):
            status = self.MARKET_CLOSED
            reason = "Latest completed weekday session is stored; market is outside trading hours."
        else:
            status = self.STALE
            reason = "Provider timestamp does not match the expected latest completed weekday session."

        return DataFreshness(
            status=status,
            reason=reason,
            provider_timestamp=local_timestamp.isoformat(),
            age_seconds=max(age_seconds, 0),
            session=session.isoformat() if session else None,
            expected_latest_completed_session=expected.isoformat(),
        )

    def for_scanner_session(self, session: date | None) -> DataFreshness:
        expected = self.expected_latest_completed_session
        if session is None:
            status = self.DATA_UNAVAILABLE
            reason = "Scanner session is unavailable."
        elif session != expected:
            status = self.STALE
            reason = "Scanner cache session is not the expected latest completed weekday session."
        elif self.is_trading_window:
            status = self.LIVE
            reason = "Scanner cache matches the latest completed session; scanner data is session-based."
        else:
            status = self.MARKET_CLOSED
            reason = "Scanner cache matches the latest completed session; market is closed."
        return DataFreshness(
            status=status,
            reason=reason,
            provider_timestamp=None,
            age_seconds=None,
            session=session.isoformat() if session else None,
            expected_latest_completed_session=expected.isoformat(),
        )

    def market_meta(
        self,
        *,
        provider_timestamp: datetime | None,
        provider_session: date | None = None,
        scanner_session: date | None,
    ) -> dict[str, object]:
        quote_freshness = self.for_provider_timestamp(
            provider_timestamp, session=provider_session
        )
        scanner_freshness = self.for_scanner_session(scanner_session)
        return {
            "generated_at": self.now.isoformat(),
            "timezone": "Asia/Kolkata",
            "status": quote_freshness.status,
            "reason": quote_freshness.reason,
            "is_trading_weekday": self.is_trading_weekday,
            "is_trading_window": self.is_trading_window,
            "holiday_calendar": "DATA_UNAVAILABLE",
            "latest_provider_timestamp": quote_freshness.provider_timestamp,
            "data_age_seconds": quote_freshness.age_seconds,
            "latest_scanner_session": (
                scanner_session.isoformat() if scanner_session else None
            ),
            "expected_latest_completed_session": (
                self.expected_latest_completed_session.isoformat()
            ),
            "scanner_status": scanner_freshness.status,
        }
