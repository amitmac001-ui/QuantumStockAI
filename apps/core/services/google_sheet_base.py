from __future__ import annotations

import json
import os
from pathlib import Path

import gspread
from django.conf import settings
from google.oauth2.service_account import Credentials


class GoogleSheetBase:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, spreadsheet_id: str | None = None):
        cloud_config = {}
        raw_cloud_config = str(os.environ.get("CLOUD_SYNC_CONFIG", "") or "").strip()
        if raw_cloud_config:
            cloud_config = json.loads(raw_cloud_config)
        credentials_json = str(settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
        if credentials_json:
            credentials = Credentials.from_service_account_info(
                json.loads(credentials_json), scopes=self.SCOPES
            )
        elif cloud_config.get("google_service_account"):
            credentials = Credentials.from_service_account_info(
                cloud_config["google_service_account"], scopes=self.SCOPES
            )
        else:
            credentials_file = Path(settings.GOOGLE_CREDENTIALS_FILE)
            if not credentials_file.is_absolute():
                credentials_file = Path(settings.BASE_DIR) / credentials_file
            credentials = Credentials.from_service_account_file(
                str(credentials_file), scopes=self.SCOPES
            )
        self.client = gspread.authorize(credentials)
        target = str(
            spreadsheet_id
            or settings.GOOGLE_SHEET_ID
            or cloud_config.get("google_sheet_id")
            or ""
        ).strip()
        if not target:
            raise ValueError("Google Sheets spreadsheet ID is not configured.")
        self.spreadsheet = self.client.open_by_key(target)

    def worksheet(self, name: str, rows: int = 5_000, cols: int = 120):
        try:
            return self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=name, rows=rows, cols=cols)
