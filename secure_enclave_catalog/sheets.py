"""Read data intake Sheet via the Google Sheets API.

This module reads a Google Sheet range, treating the first row as column headers 
and returning each subsequent row as a dictionary keyed by those headers. 
It uses service account credentials for authentication.
"""

from __future__ import annotations

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _build_service(credentials_path: str):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials)


def read_sheet_rows(
    spreadsheet_id: str,
    sheet_range: str,
    credentials_path: str,
) -> list[dict[str, str]]:
    """Read a Sheet range, treating its first row as column headers.

    `sheet_range` must include the tab name, e.g. "Form Responses 1!A1:AZ".
    Each remaining row is returned as a dict keyed by the header row, so
    downstream code can look fields up by their actual Sheet column name
    rather than a hardcoded position.
    """
    service = _build_service(credentials_path)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_range)
        .execute()
    )
    values: list[list[str]] = result.get("values", [])
    if not values:
        return []

    header, *data_rows = values
    rows = []
    for raw_row in data_rows:
        padded_row = raw_row + [""] * (len(header) - len(raw_row))
        rows.append(dict(zip(header, padded_row)))
    return rows
