from django.conf import settings
from django.db import models
from django.utils import timezone


class UpstoxToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upstox_tokens",
        null=True,
        blank=True,
    )

    access_token = models.TextField()

    refresh_token = models.TextField(
        blank=True,
        default="",
    )

    token_type = models.CharField(
        max_length=50,
        default="Bearer",
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        if self.user:
            return f"{self.user} - Upstox Token"
        return "System Upstox Token"

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at

    @property
    def expires_in(self):
        if not self.expires_at:
            return None

        seconds = int(
            (self.expires_at - timezone.now()).total_seconds()
        )

        return max(seconds, 0)

    @property
    def needs_refresh(self):
        if not self.expires_at:
            return False

        return self.expires_in <= 300
