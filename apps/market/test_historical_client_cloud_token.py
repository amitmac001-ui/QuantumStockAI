from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.market.providers.historical_client import HistoricalClient
from apps.upstox_auth.exceptions import TokenNotFoundError


class HistoricalClientCloudTokenTests(SimpleTestCase):
    @override_settings(UPSTOX_ACCESS_TOKEN="cloud-token")
    @patch("apps.market.providers.historical_client.HistoryV3Api")
    @patch("apps.market.providers.historical_client.ApiClient")
    @patch("apps.market.providers.historical_client.Configuration")
    @patch("apps.upstox_auth.services.read_only_credential_service.token_refresh_service.refresh_if_required")
    def test_environment_token_is_used_when_cloud_database_has_no_oauth_row(
        self, refresh, configuration, api_client, history_api
    ):
        refresh.side_effect = TokenNotFoundError("no DB token")
        configured = SimpleNamespace(access_token=None)
        configuration.return_value = configured

        HistoricalClient()

        self.assertEqual(configured.access_token, "cloud-token")
        api_client.assert_called_once_with(configured)
        history_api.assert_called_once()
