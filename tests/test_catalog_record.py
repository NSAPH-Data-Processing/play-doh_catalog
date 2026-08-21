import json

import pytest

from play_doh_catalog.catalog_record import (
    build_catalog_record,
    derive_dataset_id,
)
from play_doh_catalog.eligibility import PublicityTier


def _public_row(**overrides: str) -> dict[str, str]:
    base = {
        "dataset_title": "MBSF CCW Dataset",
        "timestamp": "2026/08/15 10:23:00",
        "motivation_provenance": "Built to support chronic conditions research.",
        "doi": "https://doi.org/10.7910/DVN/BFCWDK",
        "github_repo_and_resources": "https://github.com/example/mbsf_ccw",
        "keywords": "chronic conditions, medicare, health",
        "spatial_coverage": "US",
        "temporal_coverage": "2003-2022",
        "domain": "Health",
        "spatial_resolution": "County",
        "temporal_resolution": "Yearly",
        "institutional_affiliation": "Harvard T.H. Chan School of Public Health",
        "pi_full_name": "Jane Doe",
        "location_in_red": "research_projects/mbsf_ccw",
        "location_in_cannon": "nsaph_ci3/mbsf_ccw",
        # Fields that must never appear in a catalog record:
        "full_name": "Submitter Name",
        "submitter_email": "submitter@example.edu",
        "desired_red_path": "research_projects/requested_path",
        "globus_import_path": "/import/submitter",
        "basecamp_project_card": "https://basecamp.com/some/card",
        "additional_notes": "internal note",
        "process_feedback": "internal feedback",
        "review_status": "Approved",
        "publish_to_catalog": "TRUE",
    }
    base.update(overrides)
    return base


def test_derive_dataset_id_is_stable_for_same_title_and_timestamp() -> None:
    row = _public_row()
    assert derive_dataset_id(row) == derive_dataset_id(dict(row))


def test_derive_dataset_id_differs_for_same_title_different_timestamp() -> None:
    row_a = _public_row(timestamp="2026/08/15 10:23:00")
    row_b = _public_row(timestamp="2026/08/16 09:00:00")
    assert derive_dataset_id(row_a) != derive_dataset_id(row_b)


def test_derive_dataset_id_survives_title_edit() -> None:
    # Same submission (same Timestamp), title edited after the fact -
    # the ID should not change, so the catalog entry isn't duplicated.
    row_a = _public_row(dataset_title="MBSF CCW Dataset")
    row_b = _public_row(dataset_title="MBSF CCW Dataset (renamed)")
    assert derive_dataset_id(row_a) != derive_dataset_id(row_b)  # title is part of the slug
    # ...but the hash suffix (the actual uniqueness/stability anchor) is unchanged:
    suffix_a = derive_dataset_id(row_a).rsplit("-", 1)[1]
    suffix_b = derive_dataset_id(row_b).rsplit("-", 1)[1]
    assert suffix_a == suffix_b


def test_build_catalog_record_raises_for_restricted_tier() -> None:
    with pytest.raises(ValueError):
        build_catalog_record(_public_row(), PublicityTier.RESTRICTED)


def test_public_record_has_required_datalad_catalog_fields() -> None:
    record = build_catalog_record(_public_row(), PublicityTier.PUBLIC)
    assert record["type"] == "dataset"
    assert record["dataset_id"]
    assert record["dataset_version"]
    assert record["metadata_sources"]["sources"]


def test_public_record_is_json_serializable() -> None:
    record = build_catalog_record(_public_row(), PublicityTier.PUBLIC)
    json.dumps(record)  # must not raise


def test_public_record_includes_locations() -> None:
    record = build_catalog_record(_public_row(), PublicityTier.PUBLIC)
    datapath_tabs = [d for d in record["additional_display"] if d["name"] == "Datapath"]
    assert datapath_tabs == [
        {
            "name": "Datapath",
            "content": {
                "ReD path": "research_projects/mbsf_ccw",
                "Cannon path": "nsaph_ci3/mbsf_ccw",
            },
        }
    ]


def test_consent_record_omits_locations() -> None:
    record = build_catalog_record(_public_row(), PublicityTier.CONSENT)
    tab_names = [d["name"] for d in record.get("additional_display", [])]
    assert "Datapath" not in tab_names


def test_consent_record_includes_access_instructions() -> None:
    row = _public_row(access_contact_terms="Email the PI at pi@example.edu for access.")
    record = build_catalog_record(row, PublicityTier.CONSENT)
    access_tabs = [d for d in record["additional_display"] if d["name"] == "Access Instructions"]
    assert access_tabs == [
        {
            "name": "Access Instructions",
            "content": {"How to request access": "Email the PI at pi@example.edu for access."},
        }
    ]


def test_public_record_omits_access_instructions_tab() -> None:
    row = _public_row(access_contact_terms="Email the PI at pi@example.edu for access.")
    record = build_catalog_record(row, PublicityTier.PUBLIC)
    tab_names = [d["name"] for d in record.get("additional_display", [])]
    assert "Access Instructions" not in tab_names


def test_na_doi_is_omitted() -> None:
    record = build_catalog_record(_public_row(doi="N/A"), PublicityTier.PUBLIC)
    assert "doi" not in record


def test_blank_doi_is_omitted() -> None:
    record = build_catalog_record(_public_row(doi=""), PublicityTier.PUBLIC)
    assert "doi" not in record


def test_keywords_are_split_and_stripped() -> None:
    record = build_catalog_record(
        _public_row(keywords="Heat,  ADRD ,Surface Temperature"), PublicityTier.PUBLIC
    )
    assert record["keywords"] == ["Heat", "ADRD", "Surface Temperature"]


@pytest.mark.parametrize("tier", [PublicityTier.PUBLIC, PublicityTier.CONSENT])
def test_never_leaked_fields_are_absent_from_either_tier(tier: PublicityTier) -> None:
    row = _public_row(
        full_name="Should Not Appear",
        submitter_email="should-not-appear@example.edu",
        desired_red_path="should_not_appear/path",
        globus_import_path="/should/not/appear",
        basecamp_project_card="https://should-not-appear.example.com",
        additional_notes="should not appear",
        process_feedback="should not appear",
        review_status="Approved",
        publish_to_catalog="TRUE",
    )
    record = build_catalog_record(row, tier)
    dumped = json.dumps(record)
    for forbidden in (
        "Should Not Appear",
        "should-not-appear@example.edu",
        "should_not_appear/path",
        "/should/not/appear",
        "should-not-appear.example.com",
        "should not appear",
        "Approved",
        "TRUE",
    ):
        assert forbidden not in dumped, f"{forbidden!r} leaked into the catalog record"
