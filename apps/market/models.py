from django.db import models
from django.utils import timezone
import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from apps.companies.models import Company


class Exchange(models.TextChoices):
    NSE = "NSE", "NSE"
    BSE = "BSE", "BSE"


class MarketStatus(models.TextChoices):
    PREOPEN = "PREOPEN", "Pre Open"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    POST = "POST", "Post Market"


class MarketQuote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    symbol = models.CharField(max_length=30, db_index=True)

    exchange = models.CharField(
        max_length=10,
        choices=Exchange.choices,
        default=Exchange.NSE,
        db_index=True,
    )

    company_name = models.CharField(max_length=255)

    last_price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    open_price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    high_price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    low_price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    previous_close = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    change = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    change_percent = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    volume = models.BigIntegerField(default=0)

    traded_value = models.DecimalField(
        max_digits=30,
        decimal_places=2,
        default=0,
    )

    market_status = models.CharField(
        max_length=20,
        choices=MarketStatus.choices,
        default=MarketStatus.CLOSED,
        db_index=True,
    )

    last_trade_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Provider-supplied quote snapshot timestamp. This is not the exchange trade time;
    # use last_trade_time for that. Both are distinct from the DB updated_at time.
    provider_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

        indexes = [
            models.Index(fields=["symbol"]),
            models.Index(fields=["exchange"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["market_status"]),
            models.Index(fields=["symbol", "exchange"]),
            models.Index(fields=["exchange", "updated_at"]),
            models.Index(fields=["change_percent"]),
            models.Index(fields=["volume"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange"],
                name="uq_market_symbol_exchange",
            ),
        ]

    def __str__(self):
        return f"{self.symbol} ({self.exchange})"


class MarketOHLC(models.Model):
    class Interval(models.TextChoices):
        M1 = "1m", "1 Minute"
        M5 = "5m", "5 Minute"
        M15 = "15m", "15 Minute"
        M30 = "30m", "30 Minute"
        H1 = "1h", "1 Hour"
        D1 = "1d", "Daily"
        W1 = "1w", "Weekly"
        MN = "1mo", "Monthly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    symbol = models.CharField(max_length=30, db_index=True)

    exchange = models.CharField(
        max_length=10,
        choices=Exchange.choices,
        default=Exchange.NSE,
    )

    interval = models.CharField(
        max_length=10,
        choices=Interval.choices,
        db_index=True,
    )

    open = models.DecimalField(max_digits=20, decimal_places=4)
    high = models.DecimalField(max_digits=20, decimal_places=4)
    low = models.DecimalField(max_digits=20, decimal_places=4)
    close = models.DecimalField(max_digits=20, decimal_places=4)

    volume = models.BigIntegerField(default=0)

    candle_time = models.DateTimeField(db_index=True)

    # Exact timestamp supplied by the provider. candle_time remains the canonical
    # exchange-session key used for idempotent daily upserts.
    provider_timestamp = models.DateTimeField(null=True, blank=True, db_index=True)

    # Provider/pipeline quality metadata is retained verbatim when available.
    data_quality_flags = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-candle_time"]

        indexes = [
            models.Index(fields=["symbol", "interval"]),
            models.Index(fields=["symbol", "candle_time"]),
            models.Index(fields=["interval", "candle_time"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "symbol",
                    "exchange",
                    "interval",
                    "candle_time",
                ],
                name="uq_market_candle",
            ),
        ]

    def __str__(self):
        return f"{self.symbol} {self.interval}"


class CloudDailyCandle(models.Model):
    """Compact rolling EOD history for cloud scanner execution."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="cloud_daily_candles"
    )
    session_date = models.DateField()
    open = models.DecimalField(max_digits=20, decimal_places=4)
    high = models.DecimalField(max_digits=20, decimal_places=4)
    low = models.DecimalField(max_digits=20, decimal_places=4)
    close = models.DecimalField(max_digits=20, decimal_places=4)
    volume = models.BigIntegerField(default=0)
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    data_quality_flags = models.JSONField(default=list, blank=True)
    ingested_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-session_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "session_date"],
                name="uq_cloud_daily_company_session",
            )
        ]

    @property
    def symbol(self):
        return self.company.symbol

    @property
    def exchange(self):
        return self.company.exchange

    @property
    def candle_time(self):
        return datetime.combine(
            self.session_date, time.min, tzinfo=ZoneInfo("Asia/Kolkata")
        )


class CloudBenchmarkCandle(models.Model):
    """Compact rolling NIFTY 50 EOD history."""

    session_date = models.DateField(unique=True)
    open = models.DecimalField(max_digits=20, decimal_places=4)
    high = models.DecimalField(max_digits=20, decimal_places=4)
    low = models.DecimalField(max_digits=20, decimal_places=4)
    close = models.DecimalField(max_digits=20, decimal_places=4)
    volume = models.BigIntegerField(default=0)
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    data_quality_flags = models.JSONField(default=list, blank=True)
    ingested_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-session_date"]

    @property
    def candle_time(self):
        return datetime.combine(
            self.session_date, time.min, tzinfo=ZoneInfo("Asia/Kolkata")
        )


class CloudQuoteSnapshot(models.Model):
    """One genuine latest quote per active cloud instrument."""

    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, primary_key=True,
        related_name="cloud_quote_snapshot",
    )
    last_price = models.DecimalField(max_digits=20, decimal_places=4)
    open_price = models.DecimalField(max_digits=20, decimal_places=4)
    high_price = models.DecimalField(max_digits=20, decimal_places=4)
    low_price = models.DecimalField(max_digits=20, decimal_places=4)
    previous_close = models.DecimalField(max_digits=20, decimal_places=4)
    change = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    change_percent = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    volume = models.BigIntegerField(default=0)
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    last_trade_time = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def symbol(self):
        return self.company.symbol

    @property
    def exchange(self):
        return self.company.exchange

    @property
    def company_name(self):
        return self.company.name