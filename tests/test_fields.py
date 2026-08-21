from play_doh_catalog.fields import (
    HEADER_MAP,
    missing_expected_headers,
    normalize_row,
    unmapped_headers,
)

# Captured verbatim (including whitespace quirks) from the live intake
# Sheet on 2026-08-20 - see todo.md's "Sheet access" resolution. If this
# list stops matching HEADER_MAP, the form's questions changed and
# HEADER_MAP needs updating to match.
REAL_SHEET_HEADERS = [
    "location in ReD ",
    "location in cannon",
    "Timestamp",
    "Full Name",
    "PI's Full Name",
    "Institutional Affiliation",
    "Email",
    (
        "Is the dataset publicly shareable? (The data is not under a DUA, "
        "restricted use, etc)\n\nYour data may not be shareable if it is: "
        "\n\n1) Draft publication your data files are not ready for "
        "publication\n2) Restricted data your data files cannot be shared "
        "because of sensitive or restricted content."
    ),
    (
        "Provide the relative path (research_projects/) for your desired "
        "location on ReD for the data."
    ),
    "Is your data shareable with your, your PI's, or a third party's consent? ",
    "Please provide the contact information and terms for acquiring access to the data",
    (
        "Is the dataset in a public repository (Harvard Dataverse, "
        "Zenodo, etc)? This includes any repository that provides a DOI "
        "for a dataset. "
    ),
    "Dataset Title",
    "DOI (Enter N/A if your dataset is restricted)",
    "Spatial Coverage",
    "Temporal Coverage",
    "Domain",
    (
        "When relevant, answer each of the following questions about the "
        "motivation behind the dataset.\na. What is the motivation behind "
        "the creation of this dataset?\nb. Who funded the creation of "
        "this dataset?\nc. What groups/people were involved in the "
        "collection/generation/processing of this data?"
    ),
    (
        "Provide the import path in Globus for your staged datasets "
        "(e.g. /import/username)"
    ),
    "Anything else we should know about the data?",
    (
        "If you have any questions or feedback on this process, please "
        "feel free to share it here."
    ),
    "Link to Basecamp project card",
    (
        "If you generated or processed the data yourself, please provide "
        "a link to the GitHub repository and any other resources you "
        "used to create it"
    ),
    (
        "Key words describing the data focus (e.g. Heat, ADRD, Surface "
        "Temperature, etc.)"
    ),
    "Spatial Resolution",
    "Temporal Resolution",
    "Do you have sufficient information to create a Dataverse deposit? ",
    "Have you received permission from a member of the  Data Team to import your restricted data?",
    "Review Status",
    "Publish to Catalog",
]


def test_header_map_covers_every_real_sheet_header() -> None:
    assert unmapped_headers(REAL_SHEET_HEADERS) == []


def test_every_mapped_header_is_present_in_the_real_sheet() -> None:
    assert missing_expected_headers(REAL_SHEET_HEADERS) == []


def test_normalize_row_maps_known_headers_to_canonical_names() -> None:
    raw_row = {
        "Dataset Title": "My Dataset",
        "DOI (Enter N/A if your dataset is restricted)": "10.1234/abc",
        "Review Status": "Approved",
    }

    assert normalize_row(raw_row) == {
        "dataset_title": "My Dataset",
        "doi": "10.1234/abc",
        "review_status": "Approved",
    }


def test_normalize_row_strips_header_whitespace_before_matching() -> None:
    raw_row = {"location in ReD ": "research_projects/foo"}

    assert normalize_row(raw_row) == {"location_in_red": "research_projects/foo"}


def test_normalize_row_drops_unmapped_headers() -> None:
    raw_row = {"Dataset Title": "My Dataset", "Some New Question": "answer"}

    assert normalize_row(raw_row) == {"dataset_title": "My Dataset"}


def test_no_duplicate_canonical_names() -> None:
    canonical_names = list(HEADER_MAP.values())
    assert len(canonical_names) == len(set(canonical_names))
