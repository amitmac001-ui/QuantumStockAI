import uuid

from django.db import connection, models


class Company(models.Model):
    class InstrumentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"
        INVALID = "invalid", "Invalid instrument"

    class SecurityCategory(models.TextChoices):
        OPERATING_EQUITY = "operating_equity", "Operating-company equity"
        ETF = "etf", "Exchange-traded fund"
        DEBT = "debt", "Debt or government security"
        OTHER = "other", "Other security"
        UNKNOWN = "unknown", "Unclassified"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    symbol = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
    )

    exchange = models.CharField(
        max_length=20,
        default="NSE",
        db_index=True,
    )

    isin = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
    )

    # Upstox Instrument Key
    # Example:
    # NSE_EQ|INE002A01018
    upstox_instrument_key = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
    )

    name = models.CharField(
        max_length=255,
        db_index=True,
    )

    series = models.CharField(
        max_length=20,
        blank=True,
    )

    provider_segment = models.CharField(max_length=30, blank=True, db_index=True)

    provider_instrument_type = models.CharField(
        max_length=30, blank=True, db_index=True
    )

    provider_security_type = models.CharField(
        max_length=30, blank=True, db_index=True
    )

    security_category = models.CharField(
        max_length=30,
        choices=SecurityCategory.choices,
        default=SecurityCategory.UNKNOWN,
        db_index=True,
    )

    history_sync_last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)

    history_sync_last_success_session = models.DateField(null=True, blank=True, db_index=True)

    sector = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )

    industry = models.CharField(
        max_length=150,
        blank=True,
        db_index=True,
    )

    listing_date = models.DateField(
        null=True,
        blank=True,
    )
    # Compact prior-session three-year high summary. The scanner needs the
    # breakout reference, not three years of cloud candle rows per company.
    three_year_high = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    three_year_high_session = models.DateField(null=True, blank=True)
    three_year_window_start = models.DateField(null=True, blank=True)
    three_year_observations = models.PositiveIntegerField(default=0)


    face_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    market_cap = models.BigIntegerField(
        default=0,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    instrument_status = models.CharField(
        max_length=20,
        choices=InstrumentStatus.choices,
        default=InstrumentStatus.ACTIVE,
        db_index=True,
    )

    instrument_status_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["symbol"]

        indexes = [
            models.Index(fields=["symbol"]),
            models.Index(fields=["name"]),
            models.Index(fields=["exchange"]),
            models.Index(fields=["isin"]),
            models.Index(fields=["upstox_instrument_key"]),
            models.Index(fields=["sector"]),
            models.Index(fields=["industry"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["instrument_status"]),
            models.Index(fields=["exchange", "symbol"]),
            models.Index(fields=["exchange", "upstox_instrument_key"]),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.name}"

    @property
    def is_scan_eligible(self) -> bool:
        return bool(
            self.is_active
            and self.instrument_status == self.InstrumentStatus.ACTIVE
            and str(self.upstox_instrument_key or "").strip()
            and self.provider_segment == "NSE_EQ"
            and self.security_category == self.SecurityCategory.OPERATING_EQUITY
            and self.provider_security_type in {"", "NORMAL"}
        )

    @classmethod
    def persisted_database_columns(cls) -> frozenset[str]:
        """Return the columns currently available without assuming migrations ran."""
        try:
            with connection.cursor() as cursor:
                description = connection.introspection.get_table_description(
                    cursor, cls._meta.db_table
                )
        except Exception:
            return frozenset()
        return frozenset(column.name for column in description)

    @classmethod
    def scanner_eligible(cls):
        base = cls.objects.filter(
            exchange="NSE",
            is_active=True,
            instrument_status=cls.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="")
        classification_columns = {
            "provider_segment",
            "provider_security_type",
            "security_category",
        }
        if not classification_columns.issubset(cls.persisted_database_columns()):
            # Pull-request diagnostics deliberately use the shared database in a
            # read-only mode. Until its migration is applied, retain the prior,
            # narrow NSE EQ rule instead of querying columns that do not exist.
            return base.filter(series="EQ")
        return base.filter(
            provider_segment="NSE_EQ",
            security_category=cls.SecurityCategory.OPERATING_EQUITY,
            provider_security_type__in=("", "NORMAL"),
        )
