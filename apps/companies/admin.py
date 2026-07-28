from django.contrib import admin

from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "name",
        "exchange",
        "sector",
        "industry",
        "is_active",
    )

    list_filter = (
        "exchange",
        "sector",
        "industry",
        "is_active",
    )

    search_fields = (
        "symbol",
        "name",
        "isin",
    )

    ordering = (
        "symbol",
    )

    list_per_page = 100

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )
