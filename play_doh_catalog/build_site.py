"""Rebuild the datalad-catalog static site from the current eligible Sheet rows.

Mirrors the reference catalog's `create_catalog.sh`, but the metadata comes
from live Sheet data via the eligibility/whitelist pipeline (sheets ->
fields -> eligibility -> catalog_record) instead of pre-authored `.jsonl`
files. Every run does a full rebuild - removes any existing catalog output
first, same as the reference script's `rm -r lego` - rather than
incrementally patching one, so a dataset that becomes ineligible (e.g.
`publish_to_catalog` flips to FALSE) simply isn't re-added. Diffing and
removing stale `catalog-add` entries would be far more error-prone.

Datasets here are a flat, unrelated collection - no natural filesystem
hierarchy - but `datalad-catalog` has no browsable view without a `home`
dataset set (confirmed empirically: the site 404s at `/` with no home
set). So every run also builds one synthetic root record whose
`subdatasets` list is every eligible dataset, and sets that as home -
matching the reference catalog's own top-level "lego" dataset pattern.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from play_doh_catalog.catalog_record import _slugify, build_catalog_record
from play_doh_catalog.eligibility import evaluate_eligibility
from play_doh_catalog.fields import normalize_row
from play_doh_catalog.sheets import read_sheet_rows

REPO_ROOT = Path(__file__).resolve().parent.parent

ROOT_DATASET_ID = "play_doh_catalog"
ROOT_DATASET_VERSION = "v0"
ROOT_NAME = "Play-Doh Catalog"
ROOT_DESCRIPTION = "Catalog of datasets imported into the secure enclave."


def _run_datalad(*args: str, cwd: Path) -> None:
    subprocess.run(["datalad", *args], cwd=cwd, check=True)


def _build_root_record(records: list[dict]) -> dict:
    return {
        "type": "dataset",
        "dataset_id": ROOT_DATASET_ID,
        "dataset_version": ROOT_DATASET_VERSION,
        "name": ROOT_NAME,
        "description": ROOT_DESCRIPTION,
        "metadata_sources": {
            "key_source_map": {},
            "sources": [{"source_name": "play_doh_catalog_root", "source_version": "manual"}],
        },
        "subdatasets": [
            {
                "dataset_id": record["dataset_id"],
                "dataset_version": ROOT_DATASET_VERSION,
                # A nominal label, not a real filesystem path - these are
                # metadata-only records, not real DataLad datasets.
                "dataset_path": _slugify(record["name"]),
            }
            for record in records
        ],
    }


def build_eligible_records(
    spreadsheet_id: str, sheet_range: str, credentials_path: str
) -> list[dict]:
    """Read the Sheet and build one catalog record per eligible dataset."""
    raw_rows = read_sheet_rows(spreadsheet_id, sheet_range, credentials_path)
    records = []
    for raw_row in raw_rows:
        normalized = normalize_row(raw_row)
        result = evaluate_eligibility(normalized)
        if result.eligible:
            records.append(build_catalog_record(normalized, result.tier))
    return records


def rebuild_site(records: list[dict], catalog_dir: Path, config_path: Path) -> None:
    """Rebuild the catalog site at `catalog_dir` from scratch using `records`."""
    if catalog_dir.exists():
        shutil.rmtree(catalog_dir)

    _run_datalad(
        "catalog-create",
        "--catalog",
        str(catalog_dir),
        "--config-file",
        str(config_path),
        cwd=REPO_ROOT,
    )

    root_record = _build_root_record(records)

    with tempfile.TemporaryDirectory() as tmp_dir:
        metadata_path = Path(tmp_dir) / "metadata.jsonl"
        with open(metadata_path, "w", encoding="utf-8") as f:
            for record in [root_record, *records]:
                f.write(json.dumps(record) + "\n")

        _run_datalad("catalog-validate", "--metadata", str(metadata_path), cwd=REPO_ROOT)
        _run_datalad(
            "catalog-add",
            "--catalog",
            str(catalog_dir),
            "--metadata",
            str(metadata_path),
            cwd=REPO_ROOT,
        )

    _run_datalad(
        "catalog-set",
        "--catalog",
        str(catalog_dir),
        "--dataset-id",
        ROOT_DATASET_ID,
        "--dataset-version",
        ROOT_DATASET_VERSION,
        "home",
        cwd=REPO_ROOT,
    )


def _load_sheet_config(sheet_config_path: Path) -> tuple[str, str]:
    """Read (spreadsheet_id, range) from sheet_config.yaml.

    Not secret - a spreadsheet ID and tab name don't grant access on their
    own, so this is a committed config file rather than a GitHub Actions
    secret/variable (see decisions.md).
    """
    with open(sheet_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["spreadsheet_id"], config["range"]


def main() -> None:
    credentials_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    sheet_config_path = REPO_ROOT / os.environ.get("SHEET_CONFIG_PATH", "sheet_config.yaml")
    catalog_dir = REPO_ROOT / os.environ.get("CATALOG_OUTPUT_DIR", "site")
    config_path = REPO_ROOT / os.environ.get("CATALOG_CONFIG_PATH", "config.json")

    spreadsheet_id, sheet_range = _load_sheet_config(sheet_config_path)
    records = build_eligible_records(spreadsheet_id, sheet_range, credentials_path)
    rebuild_site(records, catalog_dir, config_path)
    print(f"Published {len(records)} dataset(s) to {catalog_dir}")


if __name__ == "__main__":
    main()
