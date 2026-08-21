from unittest.mock import MagicMock, patch

from play_doh_catalog.sheets import read_sheet_rows


def _mock_service(values: list[list[str]]) -> MagicMock:
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": values}
    return service


@patch("play_doh_catalog.sheets._build_service")
def test_read_sheet_rows_maps_header_to_dict(mock_build_service: MagicMock) -> None:
    mock_build_service.return_value = _mock_service(
        [
            ["Dataset Title", "DOI", "review_status"],
            ["My Dataset", "10.1234/abc", "Approved"],
        ]
    )

    rows = read_sheet_rows("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    assert rows == [
        {"Dataset Title": "My Dataset", "DOI": "10.1234/abc", "review_status": "Approved"}
    ]


@patch("play_doh_catalog.sheets._build_service")
def test_read_sheet_rows_pads_short_rows(mock_build_service: MagicMock) -> None:
    # Sheets API omits trailing empty cells, so a row can be shorter than the header.
    mock_build_service.return_value = _mock_service(
        [
            ["Dataset Title", "DOI"],
            ["My Dataset"],
        ]
    )

    rows = read_sheet_rows("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    assert rows == [{"Dataset Title": "My Dataset", "DOI": ""}]


@patch("play_doh_catalog.sheets._build_service")
def test_read_sheet_rows_empty_sheet_returns_empty_list(mock_build_service: MagicMock) -> None:
    mock_build_service.return_value = _mock_service([])

    rows = read_sheet_rows("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    assert rows == []


@patch("play_doh_catalog.sheets._build_service")
def test_read_sheet_rows_calls_get_with_spreadsheet_id_and_range(
    mock_build_service: MagicMock,
) -> None:
    service = _mock_service([["Dataset Title"], ["My Dataset"]])
    mock_build_service.return_value = service

    read_sheet_rows("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    service.spreadsheets.return_value.values.return_value.get.assert_called_once_with(
        spreadsheetId="sheet-id", range="Sheet1!A1:Z"
    )
