"""Rebuild the datalad-catalog static site from the current eligible Sheet rows.

Datasets are nested one level under a synthetic "domain" record derived
from the Sheet's `Domain` answer, so the catalog reads as domain folders
(Health, Climate, ...) each containing their datasets, rather than every
dataset sitting flat under the root.

`catalog_state.json` is a small snapshot of
the currently-published dataset set - not read by the site itself, just
bookkeeping so the *next* run can report what changed (added/removed/
modified datasets) without needing to reach into datalad-catalog's own
storage format.
"""

from __future__ import annotations

import hashlib
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


def _domain_dataset_id(domain: str) -> str:
    return f"{ROOT_DATASET_ID}.domain.{_slugify(domain)}"


def _build_domain_record(domain: str, records: list[dict]) -> dict:
    return {
        "type": "dataset",
        "dataset_id": _domain_dataset_id(domain),
        "dataset_version": ROOT_DATASET_VERSION,
        "name": domain,
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


def _build_root_record(domains: list[str]) -> dict:
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
                "dataset_id": _domain_dataset_id(domain),
                "dataset_version": ROOT_DATASET_VERSION,
                "dataset_path": _slugify(domain),
            }
            for domain in domains
        ],
    }


def _group_by_domain(entries: list[tuple[str, dict]]) -> dict[str, list[dict]]:
    """Group dataset records by domain, preserving first-seen domain order."""
    grouped: dict[str, list[dict]] = {}
    for domain, record in entries:
        grouped.setdefault(domain, []).append(record)
    return grouped


def build_eligible_records(
    spreadsheet_id: str, sheet_range: str, credentials_path: str
) -> list[tuple[str, dict]]:
    """Read the Sheet and build one (domain, catalog record) pair per eligible dataset."""
    raw_rows = read_sheet_rows(spreadsheet_id, sheet_range, credentials_path)
    entries = []
    for raw_row in raw_rows:
        normalized = normalize_row(raw_row)
        result = evaluate_eligibility(normalized)
        if result.eligible:
            record = build_catalog_record(normalized, result.tier)
            entries.append((normalized.get("domain", "").strip(), record))
    return entries


def rebuild_site(entries: list[tuple[str, dict]], catalog_dir: Path, config_path: Path) -> None:
    """Rebuild the catalog site at `catalog_dir` from scratch using `entries`."""
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

    shutil.copyfile(REPO_ROOT / "index.html", catalog_dir / "index.html")

    grouped = _group_by_domain(entries)
    domain_records = [_build_domain_record(domain, records) for domain, records in grouped.items()]
    root_record = _build_root_record(list(grouped.keys()))
    all_records = [record for records in grouped.values() for record in records]

    with tempfile.TemporaryDirectory() as tmp_dir:
        metadata_path = Path(tmp_dir) / "metadata.jsonl"
        with open(metadata_path, "w", encoding="utf-8") as f:
            for record in [root_record, *domain_records, *all_records]:
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


def _content_hash(record: dict) -> str:
    canonical = json.dumps(record, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_catalog_state(entries: list[tuple[str, dict]]) -> dict:
    """A snapshot of the currently-published eligible dataset set.

    Used only to diff against on the next run (`_diff_catalog_state`) - not
    read by the site itself.
    """
    datasets = sorted(
        (
            {
                "dataset_id": record["dataset_id"],
                "domain": domain,
                "name": record["name"],
                "content_hash": _content_hash(record),
            }
            for domain, record in entries
        ),
        key=lambda dataset: dataset["dataset_id"],
    )
    return {"datasets": datasets}


def _diff_catalog_state(old_state: dict, new_state: dict) -> dict:
    """Added/removed/modified (domain, name) pairs between two catalog states."""
    old_by_id = {dataset["dataset_id"]: dataset for dataset in old_state.get("datasets", [])}
    new_by_id = {dataset["dataset_id"]: dataset for dataset in new_state.get("datasets", [])}

    added = [
        (dataset["domain"], dataset["name"])
        for dataset_id, dataset in new_by_id.items()
        if dataset_id not in old_by_id
    ]
    removed = [
        (dataset["domain"], dataset["name"])
        for dataset_id, dataset in old_by_id.items()
        if dataset_id not in new_by_id
    ]
    modified = [
        (dataset["domain"], dataset["name"])
        for dataset_id, dataset in new_by_id.items()
        if dataset_id in old_by_id
        and old_by_id[dataset_id]["content_hash"] != dataset["content_hash"]
    ]
    return {"added": added, "removed": removed, "modified": modified}


def _format_diff_summary(diff: dict) -> str:
    """A markdown summary of `_diff_catalog_state`'s output, for the rebuild Issue body."""
    sections = []
    for label, key in (("Added", "added"), ("Removed", "removed"), ("Modified", "modified")):
        pairs = diff.get(key, [])
        if not pairs:
            continue
        lines = [f"### {label}"] + [f"- {name} ({domain})" for domain, name in pairs]
        sections.append("\n".join(lines))

    if not sections:
        return (
            "No dataset-level changes - the catalog output changed for another "
            "reason (e.g. branding/config)."
        )
    return "\n\n".join(sections)


def main() -> None:
    credentials_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    sheet_config_path = REPO_ROOT / os.environ.get("SHEET_CONFIG_PATH", "sheet_config.yaml")
    catalog_dir = REPO_ROOT / os.environ.get("CATALOG_OUTPUT_DIR", "site")
    config_path = REPO_ROOT / os.environ.get("CATALOG_CONFIG_PATH", "config.json")
    state_path = REPO_ROOT / os.environ.get("CATALOG_STATE_PATH", "catalog_state.json")

    spreadsheet_id, sheet_range = _load_sheet_config(sheet_config_path)
    entries = build_eligible_records(spreadsheet_id, sheet_range, credentials_path)
    rebuild_site(entries, catalog_dir, config_path)

    old_state = (
        json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"datasets": []}
    )
    new_state = _build_catalog_state(entries)
    state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")

    diff_summary_path = os.environ.get("CATALOG_DIFF_SUMMARY_PATH")
    if diff_summary_path:
        diff = _diff_catalog_state(old_state, new_state)
        Path(diff_summary_path).write_text(_format_diff_summary(diff) + "\n", encoding="utf-8")

    print(f"Published {len(entries)} dataset(s) to {catalog_dir}")


if __name__ == "__main__":
    main()
