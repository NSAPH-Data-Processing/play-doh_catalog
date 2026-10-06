"""Build a datalad-catalog dataset JSON record from an eligible Sheet row.

Only call this after `eligibility.evaluate_eligibility` has confirmed a row
is eligible - it trusts its caller on that and does not re-check
review_status/publish_to_catalog. It does still branch on `tier`, though:
this is where plan.md's Metadata Publication Matrix whitelist actually
gets enforced. Only fields explicitly copied below are ever included in
the output - submitter email, internal staging paths, workflow
columns, etc. are never referenced here, so they never reach the catalog,
by construction (decisions.md's whitelist-not-blacklist rationale).

Field placement not spelled out in plan.md was resolved here rather than
left pending (see decisions.md):
- The submitter's "Full Name" is published as the dataset's author, via
  the datalad-catalog `authors` field's free-text `name` (the form answer
  is one string that doesn't split cleanly into given/family names). PI
  Name and Institutional Affiliation are not published.
- Consent-tier access instructions go in an "Access Instructions"
  additional_display tab, not `access_request_url`/`access_request_contact`
  - the Sheet's answer is one free-text blob mixing contact info and
    terms, which doesn't fit either structured field.
"""

from __future__ import annotations

import hashlib
import re

from play_doh_catalog.eligibility import PublicityTier

DATASET_ID_NAMESPACE = "play_doh_catalog"
DATASET_VERSION = "v0"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "dataset"


def derive_dataset_id(normalized_row: dict[str, str]) -> str:
    """A stable, unique dataset_id derived from the title + submission timestamp.

    The Sheet has no dedicated ID column. Hashing the (immutable)
    Timestamp keeps the ID stable even if the title is edited later, and
    makes same-titled submissions collision-safe; the title slug keeps IDs
    human-readable.
    """
    title_slug = _slugify(normalized_row.get("dataset_title", ""))
    timestamp = normalized_row.get("timestamp", "")
    short_hash = hashlib.sha256(timestamp.encode("utf-8")).hexdigest()[:8]
    return f"{DATASET_ID_NAMESPACE}.{title_slug}-{short_hash}"


def _split_keywords(raw: str) -> list[str]:
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


def _drop_empty(fields: dict[str, str]) -> dict[str, str]:
    return {k: v.strip() for k, v in fields.items() if v and v.strip()}


def _is_present_doi(doi: str) -> bool:
    return bool(doi) and doi.strip().lower() != "n/a"


def build_catalog_record(normalized_row: dict[str, str], tier: PublicityTier) -> dict:
    """Build one datalad-catalog dataset JSON record for an eligible row."""
    if tier == PublicityTier.RESTRICTED:
        raise ValueError("RESTRICTED datasets must never be published to the catalog")

    record: dict = {
        "type": "dataset",
        "dataset_id": derive_dataset_id(normalized_row),
        "dataset_version": DATASET_VERSION,
        "name": normalized_row.get("dataset_title", ""),
        "metadata_sources": {
            "key_source_map": {},
            "sources": [
                {"source_name": "play_doh_intake_sheet", "source_version": "manual"}
            ],
        },
    }

    author = normalized_row.get("full_name", "").strip()
    if author:
        record["authors"] = [{"name": author}]

    description = normalized_row.get("motivation_provenance", "").strip()
    if description:
        record["description"] = description

    doi = normalized_row.get("doi", "")
    if _is_present_doi(doi):
        record["doi"] = doi.strip()

    url = normalized_row.get("github_repo_and_resources", "").strip()
    if url:
        record["url"] = url

    # The domain leads the keyword tags - the catalog is flat, so tags are
    # how visitors find all datasets in a domain.
    keywords = _split_keywords(normalized_row.get("keywords", ""))
    domain = normalized_row.get("domain", "").strip()
    if domain:
        keywords = [domain] + [kw for kw in keywords if kw.lower() != domain.lower()]
    if keywords:
        record["keywords"] = keywords

    top_display = []
    for name, field_name in (
        ("Spatial Coverage", "spatial_coverage"),
        ("Temporal Coverage", "temporal_coverage"),
        ("Spatial Resolution", "spatial_resolution"),
        ("Temporal Resolution", "temporal_resolution"),
    ):
        value = normalized_row.get(field_name, "").strip()
        if value:
            top_display.append({"name": name, "value": value})
    if top_display:
        record["top_display"] = top_display

    additional_display = []

    if tier == PublicityTier.PUBLIC:
        datapath = _drop_empty(
            {
                "ReD path": normalized_row.get("location_in_red", ""),
                "Cannon path": normalized_row.get("location_in_cannon", ""),
            }
        )
        if datapath:
            additional_display.append({"name": "Datapath", "content": datapath})

    if tier == PublicityTier.CONSENT:
        access_terms = normalized_row.get("access_contact_terms", "").strip()
        if access_terms:
            additional_display.append(
                {
                    "name": "Access Instructions",
                    "content": {"How to request access": access_terms},
                }
            )

    if additional_display:
        record["additional_display"] = additional_display

    return record
