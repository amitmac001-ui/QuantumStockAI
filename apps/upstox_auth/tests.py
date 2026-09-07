from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.upstox_auth.models import UpstoxToken
from apps.upstox_auth.repositories.token_repository import TokenRepository


class TokenSelectionTests(TestCase):
    def test_latest_active_token_is_selected_and_inactive_token_is_ignored(self):
        user = get_user_model().objects.create_user(
            username="token-user", email="token@example.test", password="safe-test-only"
        )
        active = UpstoxToken.objects.create(
            user=user, access_token="active-test-token", is_active=True
        )
        UpstoxToken.objects.create(
            user=user, access_token="inactive-test-token", is_active=False
        )
        self.assertEqual(TokenRepository().get().pk, active.pk)
