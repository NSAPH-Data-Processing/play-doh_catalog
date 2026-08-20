"""Map the intake Sheet's raw column headers to stable internal field names.

Sheet headers are the literal form question text - long, sometimes
multi-line, occasionally with stray whitespace (e.g. `"location in ReD "`
has a trailing space, and the restricted-import-permission question has a
double space before "Data Team") - rather than short, stable names.
Downstream eligibility/whitelist logic should go through `normalize_row`
and refer to the canonical names below, never raw header text directly, so
a question's wording can change without every consumer needing to change
too.

`HEADER_MAP` is intentionally a whitelist: a Sheet column with no entry
here is dropped by `normalize_row` rather than passed through, matching
the fail-closed philosophy in decisions.md. Use `unmapped_headers` /
`missing_expected_headers` to catch drift (a form question was reworded,
or a new column was added) instead of assuming the map stays correct
forever - see tests/test_fields.py, which checks it against the real
Sheet's headers as captured on 2026-08-20.
"""

from __future__ import annotations

HEADER_MAP: dict[str, str] = {
    "Timestamp": "timestamp",
    "Full Name": "full_name",
    "PI's Full Name": "pi_full_name",
    "Institutional Affiliation": "institutional_affiliation",
    "Email": "submitter_email",
    (
        "Is the dataset publicly shareable? (The data is not under a DUA, "
        "restricted use, etc)\n\nYour data may not be shareable if it is: "
        "\n\n1) Draft publication your data files are not ready for "
        "publication\n2) Restricted data your data files cannot be shared "
        "because of sensitive or restricted content."
    ): "publicly_shareable",
    (
        "Provide the relative path (research_projects/) for your desired "
        "location on ReD for the data."
    ): "desired_red_path",
    "Is your data shareable with your, your PI's, or a third party's consent?": "shareable_with_consent",
    "Please provide the contact information and terms for acquiring access to the data": "access_contact_terms",
    (
        "Is the dataset in a public repository (Harvard Dataverse, "
        "Zenodo, etc)? This includes any repository that provides a DOI "
        "for a dataset."
    ): "in_public_repository",
    "Dataset Title": "dataset_title",
    "DOI (Enter N/A if your dataset is restricted)": "doi",
    "Spatial Coverage": "spatial_coverage",
    "Temporal Coverage": "temporal_coverage",
    "Domain": "domain",
    (
        "When relevant, answer each of the following questions about the "
        "motivation behind the dataset.\na. What is the motivation behind "
        "the creation of this dataset?\nb. Who funded the creation of "
        "this dataset?\nc. What groups/people were involved in the "
        "collection/generation/processing of this data?"
    ): "motivation_provenance",
    (
        "Provide the import path in Globus for your staged datasets "
        "(e.g. /import/username)"
    ): "globus_import_path",
    "Anything else we should know about the data?": "additional_notes",
    (
        "If you have any questions or feedback on this process, please "
        "feel free to share it here."
    ): "process_feedback",
    "Link to Basecamp project card": "basecamp_project_card",
    (
        "If you generated or processed the data yourself, please provide "
        "a link to the GitHub repository and any other resources you "
        "used to create it"
    ): "github_repo_and_resources",
    (
        "Key words describing the data focus (e.g. Heat, ADRD, Surface "
        "Temperature, etc.)"
    ): "keywords",
    "Spatial Resolution": "spatial_resolution",
    "Temporal Resolution": "temporal_resolution",
    "Do you have sufficient information to create a Dataverse deposit?": "dataverse_ready",
    # Note the double space before "Data Team" - that's in the real header,
    # not a typo here.
    (
        "Have you received permission from a member of the  Data Team to "
        "import your restricted data?"
    ): "restricted_import_permission",
    "Review Status": "review_status",
    "Publish to Catalog": "publish_to_catalog",
    "location in ReD": "location_in_red",
    "location in cannon": "location_in_cannon",
}


def normalize_row(raw_row: dict[str, str]) -> dict[str, str]:
    """Re-key a raw Sheet row (from `sheets.read_sheet_rows`) by canonical field name.

    Headers are matched after stripping surrounding whitespace. Any raw
    header with no entry in `HEADER_MAP` is dropped, not passed through.
    """
    normalized: dict[str, str] = {}
    for raw_header, value in raw_row.items():
        canonical_name = HEADER_MAP.get(raw_header.strip())
        if canonical_name is not None:
            normalized[canonical_name] = value
    return normalized


def unmapped_headers(header_row: list[str]) -> list[str]:
    """Sheet headers with no entry in HEADER_MAP - a sign the form changed."""
    return [h for h in header_row if h.strip() not in HEADER_MAP]


def missing_expected_headers(header_row: list[str]) -> list[str]:
    """HEADER_MAP entries whose header text isn't present in the Sheet."""
    present = {h.strip() for h in header_row}
    return [raw for raw in HEADER_MAP if raw not in present]
