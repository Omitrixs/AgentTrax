"""Tests for the AT-06 approval evidence contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agenttrax.contracts.models import ApprovalEvidence


@pytest.fixture
def valid_approval_evidence_data() -> dict[str, object]:
    return {
        "approval_id": "approval-001",
        "action_id": "action-001",
        "proposal_digest": "a" * 64,
        "policy_version": "order_support_policy_v1",
        "approved_at": datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        "expires_at": datetime(2026, 11, 5, 12, 15, tzinfo=UTC),
    }


def test_approval_evidence_accepts_valid_data(
    valid_approval_evidence_data: dict[str, object],
) -> None:
    evidence = ApprovalEvidence.model_validate(valid_approval_evidence_data)

    assert evidence.approval_id == "approval-001"
    assert evidence.action_id == "action-001"
    assert evidence.proposal_digest == "a" * 64
    assert evidence.policy_version == "order_support_policy_v1"
    assert evidence.approved_at == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    assert evidence.expires_at == datetime(2026, 11, 5, 12, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    "field",
    ["approval_id", "action_id", "policy_version"],
)
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_approval_evidence_rejects_blank_identifiers(
    valid_approval_evidence_data: dict[str, object],
    field: str,
    value: str,
) -> None:
    valid_approval_evidence_data[field] = value

    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(valid_approval_evidence_data)


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "A" * 64,
        "g" * 64,
        "a" * 63,
        "a" * 65,
    ],
)
def test_approval_evidence_rejects_invalid_digest(
    valid_approval_evidence_data: dict[str, object],
    digest: str,
) -> None:
    valid_approval_evidence_data["proposal_digest"] = digest

    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(valid_approval_evidence_data)


@pytest.mark.parametrize(
    "field",
    ["approved_at", "expires_at"],
)
@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-11-05T12:00:00",
        "2026-11-05",
        "not-a-timestamp",
    ],
)
def test_approval_evidence_rejects_timestamps_without_valid_offset(
    valid_approval_evidence_data: dict[str, object],
    field: str,
    timestamp: str,
) -> None:
    valid_approval_evidence_data[field] = timestamp

    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(valid_approval_evidence_data)


@pytest.mark.parametrize(
    "expiry",
    [
        datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 5, 11, 59, tzinfo=UTC),
    ],
)
def test_approval_evidence_rejects_expiry_not_after_approval(
    valid_approval_evidence_data: dict[str, object],
    expiry: datetime,
) -> None:
    valid_approval_evidence_data["expires_at"] = expiry

    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(valid_approval_evidence_data)


def test_approval_evidence_normalizes_timestamps_to_utc(
    valid_approval_evidence_data: dict[str, object],
) -> None:
    valid_approval_evidence_data["approved_at"] = "2026-11-05T13:00:00+01:00"
    valid_approval_evidence_data["expires_at"] = "2026-11-05T13:15:00+01:00"

    evidence = ApprovalEvidence.model_validate(valid_approval_evidence_data)

    assert evidence.approved_at == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    assert evidence.expires_at == datetime(2026, 11, 5, 12, 15, tzinfo=UTC)
    assert evidence.approved_at.tzinfo is UTC
    assert evidence.expires_at.tzinfo is UTC


def test_approval_evidence_is_immutable(
    valid_approval_evidence_data: dict[str, object],
) -> None:
    evidence = ApprovalEvidence.model_validate(valid_approval_evidence_data)

    with pytest.raises(ValidationError):
        evidence.approval_id = "changed"  # type: ignore[misc]


def test_approval_evidence_rejects_unknown_fields(
    valid_approval_evidence_data: dict[str, object],
) -> None:
    valid_approval_evidence_data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(valid_approval_evidence_data)
