"""Decide whether a normalized Sheet row may be published, and to which tier.

Operates on the output of `fields.normalize_row` - never raw Sheet headers.
Implements plan.md's "Recommended Publication Logic": a dataset must be
Approved and explicitly marked `publish_to_catalog`, then falls into one of
three publicity tiers (see plan.md's "Catalog Publicity Conditions" and
decisions.md's three-tier rationale). Anything that doesn't clear every
check is RESTRICTED and not published - this fails closed, consistent with
the whitelist philosophy in decisions.md.

The exact answer text for the two publicity questions was confirmed
against the live form (2026-08-20), not guessed - getting this wrong would
misclassify a restricted dataset as public.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

REVIEW_STATUS_APPROVED = "Approved"
PUBLISH_TO_CATALOG_TRUE = "TRUE"

PUBLICLY_SHAREABLE_YES = "Yes, my data is fully shareable"
SHAREABLE_WITH_CONSENT_YES = "Yes, the data is shareable if permission is granted"


class PublicityTier(Enum):
    PUBLIC = "public"
    CONSENT = "consent"
    RESTRICTED = "restricted"


# Fields required for a catalog entry to be useful, beyond the eligibility
# gate itself. Intentionally minimal for now - dataset_title always, plus
# access_contact_terms for the consent tier (an entry that tells someone a
# dataset exists but gives no way to request it isn't useful). Expand this
# if a thin catalog entry turns out to be a problem in practice.
_REQUIRED_FIELDS_ALWAYS = ("dataset_title",)
_REQUIRED_FIELDS_BY_TIER = {
    PublicityTier.CONSENT: ("access_contact_terms",),
}


@dataclass
class EligibilityResult:
    eligible: bool
    tier: PublicityTier
    reasons: list[str] = field(default_factory=list)


def classify_publicity_tier(normalized_row: dict[str, str]) -> PublicityTier:
    """Classify a row into a publicity tier, independent of review/publish gating."""
    if normalized_row.get("publicly_shareable") == PUBLICLY_SHAREABLE_YES:
        return PublicityTier.PUBLIC
    if normalized_row.get("shareable_with_consent") == SHAREABLE_WITH_CONSENT_YES:
        return PublicityTier.CONSENT
    return PublicityTier.RESTRICTED


def _missing_required_fields(normalized_row: dict[str, str], tier: PublicityTier) -> list[str]:
    required = _REQUIRED_FIELDS_ALWAYS + _REQUIRED_FIELDS_BY_TIER.get(tier, ())
    return [name for name in required if not normalized_row.get(name, "").strip()]


def evaluate_eligibility(normalized_row: dict[str, str]) -> EligibilityResult:
    """Decide eligibility and tier for one normalized dataset row.

    `tier` is always the classified tier, even when `eligible` is False -
    callers must check `eligible` before using `tier` to select catalog
    fields; a RESTRICTED tier is never eligible regardless of the other
    gates.
    """
    reasons = []

    if normalized_row.get("review_status") != REVIEW_STATUS_APPROVED:
        reasons.append("review_status is not Approved")

    if normalized_row.get("publish_to_catalog") != PUBLISH_TO_CATALOG_TRUE:
        reasons.append("publish_to_catalog is not TRUE")

    tier = classify_publicity_tier(normalized_row)
    if tier == PublicityTier.RESTRICTED:
        reasons.append("not publicly shareable and not shareable with consent")

    missing = _missing_required_fields(normalized_row, tier)
    if missing:
        reasons.append(f"missing required fields: {', '.join(missing)}")

    return EligibilityResult(eligible=not reasons, tier=tier, reasons=reasons)
