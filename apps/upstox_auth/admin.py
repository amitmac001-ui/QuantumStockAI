from django.contrib import admin

from .models import UpstoxToken


@admin.register(UpstoxToken)
class UpstoxTokenAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "is_active",
        "expires_at",
        "expires_in_display",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )

    def expires_in_display(self, obj):
        return obj.expires_in

    expires_in_display.short_description = "Expires In (sec)"
