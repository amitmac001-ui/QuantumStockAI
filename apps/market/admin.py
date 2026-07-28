from django.contrib import admin

from .models import (
    MarketQuote,
    MarketOHLC,
)


@admin.register(MarketQuote)
class MarketQuoteAdmin(admin.ModelAdmin):

    list_display = (
        "symbol",
        "exchange",
        "last_price",
        "change",
        "change_percent",
        "volume",
        "market_status",
        "updated_at",
    )

    list_filter = (
        "exchange",
        "market_status",
    )

    search_fields = (
        "symbol",
        "company_name",
    )

    ordering = (
        "symbol",
    )


@admin.register(MarketOHLC)
class MarketOHLCAdmin(admin.ModelAdmin):

    list_display = (
        "symbol",
        "interval",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "candle_time",
    )

    list_filter = (
        "exchange",
        "interval",
    )

    search_fields = (
        "symbol",
    )

    ordering = (
        "-candle_time",
    )
