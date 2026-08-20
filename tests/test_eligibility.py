from play_doh_catalog.eligibility import (
    PublicityTier,
    classify_publicity_tier,
    evaluate_eligibility,
)


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "review_status": "Approved",
        "publish_to_catalog": "TRUE",
        "dataset_title": "My Dataset",
        "publicly_shareable": "Yes, my data is fully shareable",
        "shareable_with_consent": "No, the data is not shareable under any circumstances",
        "access_contact_terms": "",
    }
    base.update(overrides)
    return base


def test_classify_publicity_tier_public() -> None:
    assert classify_publicity_tier(_row()) == PublicityTier.PUBLIC


def test_classify_publicity_tier_consent() -> None:
    row = _row(
        publicly_shareable="No, my data is not ready for publication",
        shareable_with_consent="Yes, the data is shareable if permission is granted",
    )
    assert classify_publicity_tier(row) == PublicityTier.CONSENT


def test_classify_publicity_tier_restricted_when_both_no() -> None:
    row = _row(
        publicly_shareable="No, my data is sensitive/restricted",
        shareable_with_consent="No, the data is not shareable under any circumstances",
    )
    assert classify_publicity_tier(row) == PublicityTier.RESTRICTED


def test_classify_publicity_tier_restricted_when_fields_blank() -> None:
    row = _row(publicly_shareable="", shareable_with_consent="")
    assert classify_publicity_tier(row) == PublicityTier.RESTRICTED


def test_eligible_public_dataset() -> None:
    result = evaluate_eligibility(_row())
    assert result.eligible is True
    assert result.tier == PublicityTier.PUBLIC
    assert result.reasons == []


def test_eligible_consent_dataset_with_access_terms() -> None:
    row = _row(
        publicly_shareable="No, my data is not ready for publication",
        shareable_with_consent="Yes, the data is shareable if permission is granted",
        access_contact_terms="Email the PI at pi@example.edu",
    )
    result = evaluate_eligibility(row)
    assert result.eligible is True
    assert result.tier == PublicityTier.CONSENT


def test_not_eligible_consent_dataset_missing_access_terms() -> None:
    row = _row(
        publicly_shareable="No, my data is not ready for publication",
        shareable_with_consent="Yes, the data is shareable if permission is granted",
        access_contact_terms="",
    )
    result = evaluate_eligibility(row)
    assert result.eligible is False
    assert "missing required fields: access_contact_terms" in result.reasons


def test_not_eligible_when_review_status_not_approved() -> None:
    result = evaluate_eligibility(_row(review_status="Pending"))
    assert result.eligible is False
    assert "review_status is not Approved" in result.reasons


def test_not_eligible_when_publish_to_catalog_false() -> None:
    result = evaluate_eligibility(_row(publish_to_catalog="FALSE"))
    assert result.eligible is False
    assert "publish_to_catalog is not TRUE" in result.reasons


def test_not_eligible_when_restricted_even_if_approved_and_publish_true() -> None:
    row = _row(
        publicly_shareable="No, my data is sensitive/restricted",
        shareable_with_consent="No, the data is not shareable under any circumstances",
    )
    result = evaluate_eligibility(row)
    assert result.eligible is False
    assert result.tier == PublicityTier.RESTRICTED
    assert "not publicly shareable and not shareable with consent" in result.reasons


def test_not_eligible_when_dataset_title_missing() -> None:
    result = evaluate_eligibility(_row(dataset_title=""))
    assert result.eligible is False
    assert "missing required fields: dataset_title" in result.reasons


def test_import_permission_for_restricted_data_does_not_grant_publish_eligibility() -> None:
    # decisions.md: import permission != publish permission. Even if a
    # restricted dataset was cleared for enclave import, that must not
    # affect catalog-publish eligibility.
    row = _row(
        publicly_shareable="No, my data is sensitive/restricted",
        shareable_with_consent="No, the data is not shareable under any circumstances",
        restricted_import_permission="Yes",
    )
    result = evaluate_eligibility(row)
    assert result.eligible is False
    assert result.tier == PublicityTier.RESTRICTED
