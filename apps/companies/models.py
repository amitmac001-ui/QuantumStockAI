import uuid

from django.db import models


class Company(models.Model):
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
            models.Index(fields=["exchange", "symbol"]),
            models.Index(fields=["exchange", "upstox_instrument_key"]),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.name}"
