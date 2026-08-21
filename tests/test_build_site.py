import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from play_doh_catalog.build_site import (
    ROOT_DATASET_ID,
    ROOT_DATASET_VERSION,
    _build_catalog_state,
    _build_domain_record,
    _build_root_record,
    _diff_catalog_state,
    _domain_dataset_id,
    _format_diff_summary,
    _group_by_domain,
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


def test_build_root_record_lists_every_domain_as_a_subdataset() -> None:
    root = _build_root_record(["Health", "Climate"])

    assert root["dataset_id"] == ROOT_DATASET_ID
    assert root["dataset_version"] == ROOT_DATASET_VERSION
    assert root["subdatasets"] == [
        {
            "dataset_id": "play_doh_catalog.domain.health",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "health",
        },
        {
            "dataset_id": "play_doh_catalog.domain.climate",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "climate",
        },
    ]


def test_build_root_record_with_no_domains() -> None:
    root = _build_root_record([])
    assert root["subdatasets"] == []


def test_domain_dataset_id_is_namespaced_and_slugified() -> None:
    assert _domain_dataset_id("Health") == "play_doh_catalog.domain.health"


def test_build_domain_record_lists_its_datasets_as_subdatasets() -> None:
    records = [
        {"dataset_id": "play_doh_catalog.dataset_one-aaaa1111", "name": "Dataset One"},
        {"dataset_id": "play_doh_catalog.dataset_two-bbbb2222", "name": "Dataset Two"},
    ]

    domain_record = _build_domain_record("Health", records)

    assert domain_record["dataset_id"] == "play_doh_catalog.domain.health"
    assert domain_record["dataset_version"] == ROOT_DATASET_VERSION
    assert domain_record["name"] == "Health"
    assert domain_record["subdatasets"] == [
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


def test_group_by_domain_preserves_first_seen_domain_order() -> None:
    health_one = {"dataset_id": "play_doh_catalog.h1", "name": "H1"}
    climate_one = {"dataset_id": "play_doh_catalog.c1", "name": "C1"}
    health_two = {"dataset_id": "play_doh_catalog.h2", "name": "H2"}

    grouped = _group_by_domain(
        [("Health", health_one), ("Climate", climate_one), ("Health", health_two)]
    )

    assert list(grouped.keys()) == ["Health", "Climate"]
    assert grouped["Health"] == [health_one, health_two]
    assert grouped["Climate"] == [climate_one]


def test_build_catalog_state_is_sorted_by_dataset_id_with_stable_hash() -> None:
    entries = [
        ("Health", {"dataset_id": "play_doh_catalog.b-2222", "name": "B"}),
        ("Climate", {"dataset_id": "play_doh_catalog.a-1111", "name": "A"}),
    ]

    state = _build_catalog_state(entries)

    assert [d["dataset_id"] for d in state["datasets"]] == [
        "play_doh_catalog.a-1111",
        "play_doh_catalog.b-2222",
    ]
    assert state["datasets"][0]["domain"] == "Climate"
    assert state["datasets"][0]["name"] == "A"
    assert isinstance(state["datasets"][0]["content_hash"], str)
    # Same record content -> same hash, independent of dict key order.
    same_record_different_order = {"name": "A", "dataset_id": "play_doh_catalog.a-1111"}
    restated = _build_catalog_state([("Climate", same_record_different_order)])
    assert restated["datasets"][0]["content_hash"] == state["datasets"][0]["content_hash"]


def test_diff_catalog_state_detects_added_removed_and_modified() -> None:
    old_state = _build_catalog_state(
        [
            ("Health", {"dataset_id": "play_doh_catalog.stays-1", "name": "Stays"}),
            ("Health", {"dataset_id": "play_doh_catalog.removed-1", "name": "Removed"}),
            ("Health", {"dataset_id": "play_doh_catalog.changed-1", "name": "Changed", "doi": "old"}),
        ]
    )
    new_state = _build_catalog_state(
        [
            ("Health", {"dataset_id": "play_doh_catalog.stays-1", "name": "Stays"}),
            ("Climate", {"dataset_id": "play_doh_catalog.added-1", "name": "Added"}),
            ("Health", {"dataset_id": "play_doh_catalog.changed-1", "name": "Changed", "doi": "new"}),
        ]
    )

    diff = _diff_catalog_state(old_state, new_state)

    assert diff["added"] == [("Climate", "Added")]
    assert diff["removed"] == [("Health", "Removed")]
    assert diff["modified"] == [("Health", "Changed")]


def test_diff_catalog_state_empty_when_states_match() -> None:
    state = _build_catalog_state([("Health", {"dataset_id": "play_doh_catalog.x-1", "name": "X"})])
    diff = _diff_catalog_state(state, state)
    assert diff == {"added": [], "removed": [], "modified": []}


def test_format_diff_summary_lists_each_section() -> None:
    diff = {
        "added": [("Climate", "Added Dataset")],
        "removed": [("Health", "Removed Dataset")],
        "modified": [("Health", "Changed Dataset")],
    }

    summary = _format_diff_summary(diff)

    assert "### Added" in summary
    assert "- Added Dataset (Climate)" in summary
    assert "### Removed" in summary
    assert "- Removed Dataset (Health)" in summary
    assert "### Modified" in summary
    assert "- Changed Dataset (Health)" in summary


def test_format_diff_summary_omits_empty_sections() -> None:
    diff = {"added": [("Climate", "Added Dataset")], "removed": [], "modified": []}
    summary = _format_diff_summary(diff)
    assert "### Added" in summary
    assert "### Removed" not in summary
    assert "### Modified" not in summary


def test_format_diff_summary_falls_back_when_nothing_dataset_level_changed() -> None:
    summary = _format_diff_summary({"added": [], "removed": [], "modified": []})
    assert "No dataset-level changes" in summary


@patch("play_doh_catalog.build_site.read_sheet_rows")
def test_build_eligible_records_filters_and_builds(mock_read_sheet_rows: MagicMock) -> None:
    eligible_public = _raw_row(
        review_status="Approved",
        publish_to_catalog="TRUE",
        dataset_title="Eligible Public Dataset",
        timestamp="2026/08/20 10:00:00",
        publicly_shareable="Yes, my data is fully shareable",
        shareable_with_consent="No, the data is not shareable under any circumstances",
        domain="Health",
    )
    not_eligible = _raw_row(
        review_status="Pending",
        publish_to_catalog="FALSE",
        dataset_title="Not Yet Approved Dataset",
        timestamp="2026/08/20 11:00:00",
        publicly_shareable="No, my data is sensitive/restricted",
        shareable_with_consent="No, the data is not shareable under any circumstances",
        domain="Health",
    )
    mock_read_sheet_rows.return_value = [eligible_public, not_eligible]

    entries = build_eligible_records("sheet-id", "Sheet1!A1:Z", "fake-creds.json")

    assert len(entries) == 1
    domain, record = entries[0]
    assert domain == "Health"
    assert record["name"] == "Eligible Public Dataset"
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
    entries = [("Health", {"dataset_id": "play_doh_catalog.d-aaaa1111", "name": "D", "type": "dataset"})]

    rebuild_site(entries, catalog_dir, config_path)

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


def test_rebuild_site_metadata_file_includes_root_domain_and_dataset_records(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "site"
    config_path = tmp_path / "config.json"
    dataset_record = {"dataset_id": "play_doh_catalog.d-aaaa1111", "name": "D", "type": "dataset"}
    entries = [("Health", dataset_record)]
    captured_metadata_lines: list[str] = []

    def _capture_metadata_file(*args: str, cwd: Path) -> None:
        _fake_run_datalad(*args, cwd=cwd)
        if args[0] == "catalog-validate":
            metadata_path = Path(args[args.index("--metadata") + 1])
            captured_metadata_lines.extend(metadata_path.read_text().splitlines())

    with patch("play_doh_catalog.build_site._run_datalad", side_effect=_capture_metadata_file):
        rebuild_site(entries, catalog_dir, config_path)

    parsed = [json.loads(line) for line in captured_metadata_lines]
    assert len(parsed) == 3  # root record + the domain record + the one dataset record
    assert parsed[0]["dataset_id"] == ROOT_DATASET_ID
    assert parsed[0]["subdatasets"] == [
        {
            "dataset_id": "play_doh_catalog.domain.health",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "health",
        }
    ]
    assert parsed[1]["dataset_id"] == "play_doh_catalog.domain.health"
    assert parsed[1]["subdatasets"] == [
        {
            "dataset_id": "play_doh_catalog.d-aaaa1111",
            "dataset_version": ROOT_DATASET_VERSION,
            "dataset_path": "d",
        }
    ]
    assert parsed[2] == dataset_record
