import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from play_doh_catalog.build_site import (
    ROOT_DATASET_ID,
    ROOT_DATASET_VERSION,
    _build_root_record,
    _load_sheet_config,
    build_eligible_records,
    rebuild_site,
)
from play_doh_catalog.fields import HEADER_MAP

RAW_HEADER_OF = {canonical: raw for raw, canonical in HEADER_MAP.items()}


def _raw_row(**canonical_fields: str) -> dict[str, str]:
    return {RAW_HEADER_OF[name]: value for name, value in canonical_fields.items()}


def _fake_run_datalad(*args: str, cwd: Path) -> None:
    """_run_datalad side_effect that creates catalog_dir on catalog-create,
    matching what the real datalad command does - needed since rebuild_site
    now copies index.html into catalog_dir right after that call."""
    if args[0] == "catalog-create":
        catalog_dir = Path(args[args.index("--catalog") + 1])
        catalog_dir.mkdir(parents=True, exist_ok=True)


def test_load_sheet_config_reads_spreadsheet_id_and_range(tmp_path: Path) -> None:
    config_path = tmp_path / "sheet_config.yaml"
    config_path.write_text('spreadsheet_id: "abc123"\nrange: "Sheet1!A1:Z"\n')

    spreadsheet_id, sheet_range = _load_sheet_config(config_path)

    assert spreadsheet_id == "abc123"
    assert sheet_range == "Sheet1!A1:Z"


def test_build_root_record_lists_every_child_as_a_subdataset() -> None:
    records = [
        {"dataset_id": "play_doh_catalog.dataset_one-aaaa1111", "name": "Dataset One"},
        {"dataset_id": "play_doh_catalog.dataset_two-bbbb2222", "name": "Dataset Two"},
    ]

    root = _build_root_record(records)

    assert root["dataset_id"] == ROOT_DATASET_ID
    assert root["dataset_version"] == ROOT_DATASET_VERSION
    assert root["subdatasets"] == [
        {
            "dataset_id": "play_doh_catalog.dataset_one-aaaa1111",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "dataset_one",
        },
        {
            "dataset_id": "play_doh_catalog.dataset_two-bbbb2222",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "dataset_two",
        },
    ]


def test_build_root_record_with_no_eligible_datasets() -> None:
    root = _build_root_record([])
    assert root["subdatasets"] == []


@patch("play_doh_catalog.build_site.read_sheet_rows")
def test_build_eligible_records_filters_and_builds(mock_read_sheet_rows: MagicMock) -> None:
    eligible_public = _raw_row(
        review_status="Approved",
        publish_to_catalog="TRUE",
        dataset_title="Eligible Public Dataset",
        timestamp="2026/08/20 10:00:00",
        publicly_shareable="Yes, my data is fully shareable",
        shareable_with_consent="No, the data is not shareable under any circumstances",
    )
    not_eligible = _raw_row(
        review_status="Pending",
        publish_to_catalog="FALSE",
        dataset_title="Not Yet Approved Dataset",
        timestamp="2026/08/20 11:00:00",
        publicly_shareable="No, my data is sensitive/restricted",
        shareable_with_consent="No, the data is not shareable under any circumstances",
    )
    mock_read_sheet_rows.return_value = [eligible_public, not_eligible]

    records = build_eligible_records("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    assert len(records) == 1
    assert records[0]["name"] == "Eligible Public Dataset"
    mock_read_sheet_rows.assert_called_once_with("sheet-id", "Sheet1!A1:Z", "fake-creds.json")


@patch("play_doh_catalog.build_site.read_sheet_rows")
def test_build_eligible_records_empty_sheet(mock_read_sheet_rows: MagicMock) -> None:
    mock_read_sheet_rows.return_value = []
    assert build_eligible_records("sheet-id", "Sheet1!A1:Z", "fake-creds.json") == []


@patch("play_doh_catalog.build_site.shutil.rmtree")
@patch("play_doh_catalog.build_site._run_datalad")
def test_rebuild_site_removes_existing_catalog_dir_first(
    mock_run_datalad: MagicMock, mock_rmtree: MagicMock, tmp_path: Path
) -> None:
    catalog_dir = tmp_path / "site"
    catalog_dir.mkdir()
    config_path = tmp_path / "config.json"

    rebuild_site([], catalog_dir, config_path)

    # shutil.rmtree is also used internally by tempfile.TemporaryDirectory's
    # own cleanup, so assert our specific call happened rather than that it
    # was the only call.
    mock_rmtree.assert_any_call(catalog_dir)


@patch("play_doh_catalog.build_site._run_datalad", side_effect=_fake_run_datalad)
def test_rebuild_site_runs_create_validate_add_set_in_order(
    mock_run_datalad: MagicMock, tmp_path: Path
) -> None:
    catalog_dir = tmp_path / "does_not_exist_yet"
    config_path = tmp_path / "config.json"
    records = [{"dataset_id": "play_doh_catalog.d-aaaa1111", "name": "D", "type": "dataset"}]

    rebuild_site(records, catalog_dir, config_path)

    subcommands = [c.args[0] for c in mock_run_datalad.call_args_list]
    assert subcommands == ["catalog-create", "catalog-validate", "catalog-add", "catalog-set"]

    create_call = mock_run_datalad.call_args_list[0]
    assert create_call == call(
        "catalog-create",
        "--catalog",
        str(catalog_dir),
        "--config-file",
        str(config_path),
        cwd=create_call.kwargs["cwd"],
    )

    set_call = mock_run_datalad.call_args_list[3]
    assert set_call.args == (
        "catalog-set",
        "--catalog",
        str(catalog_dir),
        "--dataset-id",
        ROOT_DATASET_ID,
        "--dataset-version",
        ROOT_DATASET_VERSION,
        "home",
    )


@patch("play_doh_catalog.build_site._run_datalad", side_effect=_fake_run_datalad)
def test_rebuild_site_copies_index_html_override(mock_run_datalad: MagicMock, tmp_path: Path) -> None:
    # Stock datalad-catalog's generated index.html renders the logo at
    # width:100% of a wide column - huge regardless of the source image's
    # own pixel dimensions (confirmed empirically). REPO_ROOT/index.html is
    # a checked-in override (width:20%, matching the reference catalog)
    # that must get copied into every rebuilt catalog_dir.
    catalog_dir = tmp_path / "site"
    config_path = tmp_path / "config.json"

    rebuild_site([], catalog_dir, config_path)

    assert (catalog_dir / "index.html").read_text(encoding="utf-8") == (
        (Path(__file__).resolve().parent.parent / "index.html").read_text(encoding="utf-8")
    )


def test_rebuild_site_metadata_file_includes_root_and_all_records(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "site"
    config_path = tmp_path / "config.json"
    records = [
        {"dataset_id": "play_doh_catalog.d-aaaa1111", "name": "D", "type": "dataset"},
    ]
    captured_metadata_lines: list[str] = []

    def _capture_metadata_file(*args: str, cwd: Path) -> None:
        _fake_run_datalad(*args, cwd=cwd)
        if args[0] == "catalog-validate":
            metadata_path = Path(args[args.index("--metadata") + 1])
            captured_metadata_lines.extend(metadata_path.read_text().splitlines())

    with patch("play_doh_catalog.build_site._run_datalad", side_effect=_capture_metadata_file):
        rebuild_site(records, catalog_dir, config_path)

    parsed = [json.loads(line) for line in captured_metadata_lines]
    assert len(parsed) == 2  # root record + the one dataset record
    assert parsed[0]["dataset_id"] == ROOT_DATASET_ID
    assert parsed[0]["subdatasets"] == [
        {
            "dataset_id": "play_doh_catalog.d-aaaa1111",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "d",
        }
    ]
    assert parsed[1] == records[0]
