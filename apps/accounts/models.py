import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Plan(models.TextChoices):
        FREE = "FREE", "Free"
        PRO = "PRO", "Pro"
        PREMIUM = "PREMIUM", "Premium"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)

    mobile = models.CharField(max_length=15, blank=True)

    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.FREE,
    )

    is_verified = models.BooleanField(default=False)

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    def __str__(self):
        return self.email
