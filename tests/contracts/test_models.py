"""Tests for AgentTrax contract models."""

import builtins
import io
import json
import os
import socket
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agenttrax.contracts.models import (
    ActionProposal,
    ApprovalEvidence,
    ContractViolation,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    NotExecutedReason,
    PolicyDecision,
    PolicyDecisionType,
    PolicyReasonCode,
    VerificationReasonCode,
    VerificationResult,
    VerificationStatus,
    check_lifecycle_consistency,
    compute_proposal_digest,
)
from agenttrax.contracts.serialization import (
    MAX_ARGUMENT_BYTES,
    MAX_ARGUMENT_DEPTH,
    FrozenJsonArray,
    FrozenJsonObject,
)


@pytest.fixture
def valid_proposal_data() -> dict[str, object]:
    return {
        "action_id": "action-001",
        "task_id": "task-001",
        "tool_name": "get_order",
        "arguments": {"order_id": "order-123", "include_items": True},
        "requested_by": "test-agent",
        "created_at": "2026-10-01T12:00:00Z",
    }


def test_action_proposal_accepts_valid_data(
    valid_proposal_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    assert proposal.action_id == "action-001"
    assert proposal.task_id == "task-001"
    assert proposal.tool_name == "get_order"
    assert proposal.arguments["order_id"] == "order-123"
    assert proposal.requested_by == "test-agent"
    assert proposal.created_at == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "field",
    ["action_id", "task_id", "tool_name", "requested_by"],
)
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_action_proposal_rejects_blank_required_strings(
    valid_proposal_data: dict[str, object],
    field: str,
    value: str,
) -> None:
    valid_proposal_data[field] = value

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)



def test_action_proposal_rejects_extra_fields(
    valid_proposal_data: dict[str, object],
) -> None:
    valid_proposal_data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        None,
        "not-an-object",
        {1: "non-string key"},
        {"unsupported": (1, 2)},
        {"unsupported": float("nan")},
        {"unsupported": float("inf")},
    ],
)
def test_action_proposal_rejects_invalid_arguments(
    valid_proposal_data: dict[str, object],
    arguments: object,
) -> None:
    valid_proposal_data["arguments"] = arguments

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-01T12:00:00",
        "2026-10-01",
        "not-a-timestamp",
    ],
)
def test_action_proposal_rejects_timestamp_without_valid_offset(
    valid_proposal_data: dict[str, object],
    timestamp: str,
) -> None:
    valid_proposal_data["created_at"] = timestamp

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)


def test_action_proposal_normalizes_datetime_to_utc(
    valid_proposal_data: dict[str, object],
) -> None:
    original = datetime(
        2026,
        10,
        1,
        14,
        0,
        tzinfo=timezone(timedelta(hours=2)),
    )
    valid_proposal_data["created_at"] = original

    proposal = ActionProposal.model_validate(valid_proposal_data)

    assert proposal.created_at == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert proposal.created_at.tzinfo is UTC


def test_action_proposal_copies_and_freezes_nested_arguments(
    valid_proposal_data: dict[str, object],
) -> None:
    original_arguments = {
        "order": {
            "items": [{"sku": "SKU-1"}],
        }
    }
    valid_proposal_data["arguments"] = original_arguments

    proposal = ActionProposal.model_validate(valid_proposal_data)

    original_arguments["order"]["items"][0]["sku"] = "CHANGED"  # type: ignore[index]
    original_arguments["new_key"] = "new value"

    assert isinstance(proposal.arguments, FrozenJsonObject)
    frozen_order = proposal.arguments["order"]
    assert isinstance(frozen_order, FrozenJsonObject)
    frozen_items = frozen_order["items"]
    assert isinstance(frozen_items, FrozenJsonArray)
    frozen_item = frozen_items[0]
    assert isinstance(frozen_item, FrozenJsonObject)
    assert frozen_item["sku"] == "SKU-1"
    assert "new_key" not in proposal.arguments

    with pytest.raises(TypeError):
        proposal.arguments["another"] = "value"  # type: ignore[index]

    with pytest.raises(ValidationError):
        proposal.action_id = "changed"  # type: ignore[misc]


def test_action_proposal_rejects_arguments_over_byte_limit(
    valid_proposal_data: dict[str, object],
) -> None:
    valid_proposal_data["arguments"] = {"payload": "x" * MAX_ARGUMENT_BYTES}

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)


def test_action_proposal_rejects_arguments_over_depth_limit(
    valid_proposal_data: dict[str, object],
) -> None:
    nested: object = "leaf"
    for _ in range(MAX_ARGUMENT_DEPTH):
        nested = {"level": nested}

    valid_proposal_data["arguments"] = {"nested": nested}

    with pytest.raises(ValidationError):
        ActionProposal.model_validate(valid_proposal_data)


def test_proposal_digest_is_lowercase_sha256_hex(
    valid_proposal_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    digest = compute_proposal_digest(proposal)

    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(character in "0123456789abcdef" for character in digest)


def test_proposal_digest_matches_canonicalization_vector(
    valid_proposal_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    assert compute_proposal_digest(proposal) == (
        "9e0171e6462840d11e8a85e26139bfdadc184a6a4b052f9e21c2c5d0d23cbd79"
    )


def test_proposal_digest_excludes_created_at(
    valid_proposal_data: dict[str, object],
) -> None:
    first = ActionProposal.model_validate(valid_proposal_data)

    valid_proposal_data["created_at"] = "2026-10-02T12:00:00Z"
    second = ActionProposal.model_validate(valid_proposal_data)

    assert compute_proposal_digest(first) == compute_proposal_digest(second)


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("action_id", "action-002"),
        ("task_id", "task-002"),
        ("tool_name", "cancel_order"),
        ("requested_by", "another-agent"),
        ("arguments", {"order_id": "different-order"}),
    ],
)
def test_proposal_digest_changes_when_covered_field_changes(
    valid_proposal_data: dict[str, object],
    field: str,
    changed_value: object,
) -> None:
    first = ActionProposal.model_validate(valid_proposal_data)

    valid_proposal_data[field] = changed_value
    second = ActionProposal.model_validate(valid_proposal_data)

    assert compute_proposal_digest(first) != compute_proposal_digest(second)


@pytest.fixture
def valid_policy_decision_data() -> dict[str, object]:
    return {
        "action_id": "action-001",
        "proposal_digest": "a" * 64,
        "decision": PolicyDecisionType.ALLOW,
        "reason_code": PolicyReasonCode.ALLOWED_BY_POLICY,
        "reason": "Tool call is permitted by policy.",
        "policy_version": "1.0.0",
    }


@pytest.fixture
def valid_verification_result_data() -> dict[str, object]:
    return {
        "action_id": "action-123",
        "status": VerificationStatus.VERIFIED_SUCCESS,
        "reason_code": VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
        "reason": "The observed outcome matches the expected outcome.",
        "evidence": {"order_status": "confirmed"},
        "verified_at": "2026-10-28T10:00:00Z",
    }


@pytest.fixture
def valid_execution_result_data() -> dict[str, object]:
    return {
        "action_id": "action-123",
        "status": ExecutionStatus.SUCCEEDED,
        "result": {"order_id": "order-456", "updated": True},
        "error_code": None,
        "not_executed_reason": None,
        "completed_at": "2026-10-28T10:00:00Z",
    }


@pytest.mark.parametrize(
    ("decision", "reason_code", "expected_valid"),
    [
        (decision, reason_code, reason_code in allowed_codes)
        for decision, allowed_codes in [
            (
                PolicyDecisionType.ALLOW,
                {PolicyReasonCode.ALLOWED_BY_POLICY},
            ),
            (
                PolicyDecisionType.BLOCK,
                {
                    PolicyReasonCode.BLOCKED_BY_POLICY,
                    PolicyReasonCode.UNKNOWN_TOOL,
                    PolicyReasonCode.INVALID_ARGUMENTS,
                    PolicyReasonCode.MALFORMED_DECISION,
                },
            ),
            (
                PolicyDecisionType.REQUIRE_APPROVAL,
                {PolicyReasonCode.APPROVAL_REQUIRED},
            ),
        ]
        for reason_code in PolicyReasonCode
    ],
)
def test_policy_decision_validates_decision_reason_pairs(
    valid_policy_decision_data: dict[str, object],
    decision: PolicyDecisionType,
    reason_code: PolicyReasonCode,
    expected_valid: bool,
) -> None:
    valid_policy_decision_data["decision"] = decision
    valid_policy_decision_data["reason_code"] = reason_code

    if expected_valid:
        model = PolicyDecision.model_validate(valid_policy_decision_data)
        assert model.decision == decision
        assert model.reason_code == reason_code
    else:
        with pytest.raises(ValidationError):
            PolicyDecision.model_validate(valid_policy_decision_data)


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        " " + "a" * 63,
    ],
)
def test_policy_decision_rejects_invalid_proposal_digest(
    valid_policy_decision_data: dict[str, object],
    digest: str,
) -> None:
    valid_policy_decision_data["proposal_digest"] = digest

    with pytest.raises(ValidationError):
        PolicyDecision.model_validate(valid_policy_decision_data)


def test_policy_decision_accepts_valid_proposal_digest(
    valid_policy_decision_data: dict[str, object],
) -> None:
    model = PolicyDecision.model_validate(valid_policy_decision_data)

    assert model.proposal_digest == "a" * 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("action_id", ""),
        ("action_id", "   "),
        ("reason", ""),
        ("reason", "   "),
        ("policy_version", ""),
        ("policy_version", "   "),
        ("decision", "ALLOW"),
        ("reason_code", "ALLOWED_BY_POLICY"),
    ],
)
def test_policy_decision_rejects_invalid_field_values(
    valid_policy_decision_data: dict[str, object],
    field: str,
    value: object,
) -> None:
    valid_policy_decision_data[field] = value

    with pytest.raises(ValidationError):
        PolicyDecision.model_validate(valid_policy_decision_data)

@pytest.mark.parametrize(
    "missing_field",
    [
        "action_id",
        "proposal_digest",
        "decision",
        "reason_code",
        "reason",
        "policy_version",
    ],
)

def test_policy_decision_rejects_missing_fields(
    valid_policy_decision_data: dict[str, object],
    missing_field: str,
) -> None:
    del valid_policy_decision_data[missing_field]

    with pytest.raises(ValidationError):
        PolicyDecision.model_validate(valid_policy_decision_data)


def test_policy_decision_rejects_extra_fields(
    valid_policy_decision_data: dict[str, object],
) -> None:
    valid_policy_decision_data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        PolicyDecision.model_validate(valid_policy_decision_data)


def test_policy_decision_is_immutable(
    valid_policy_decision_data: dict[str, object],
) -> None:
    model = PolicyDecision.model_validate(valid_policy_decision_data)

    with pytest.raises(ValidationError):
        model.action_id = "action-002"  # type: ignore[misc]


def test_execution_result_accepts_success(
    valid_execution_result_data: dict[str, object],
) -> None:
    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    assert execution_result.status == ExecutionStatus.SUCCEEDED
    assert execution_result.result is not None
    assert execution_result.result["order_id"] == "order-456"
    assert execution_result.error_code is None
    assert execution_result.not_executed_reason is None
    assert execution_result.completed_at.isoformat() == "2026-10-28T10:00:00+00:00"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (ExecutionStatus.NOT_EXECUTED, NotExecutedReason.POLICY_BLOCKED),
        (ExecutionStatus.NOT_EXECUTED, NotExecutedReason.APPROVAL_PENDING),
        (ExecutionStatus.NOT_EXECUTED, NotExecutedReason.APPROVAL_DENIED),
        (ExecutionStatus.NOT_EXECUTED, NotExecutedReason.APPROVAL_EXPIRED),
        (
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.INTEGRITY_CHECK_FAILED,
        ),
    ],
)
def test_execution_result_accepts_not_executed(
    valid_execution_result_data: dict[str, object],
    status: ExecutionStatus,
    reason: NotExecutedReason,
) -> None:
    valid_execution_result_data.update(
        status=status,
        result=None,
        error_code=None,
        not_executed_reason=reason,
    )

    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    assert execution_result.not_executed_reason == reason
    assert execution_result.result is None
    assert execution_result.error_code is None
    assert execution_result.not_executed_reason == NotExecutedReason(reason)


@pytest.mark.parametrize(
    "error_code",
    [
        ExecutionErrorCode.TOOL_ERROR,
        ExecutionErrorCode.TIMEOUT,
        ExecutionErrorCode.INVALID_RESULT,
        ExecutionErrorCode.INTERNAL_ERROR,
    ],
)
def test_execution_result_accepts_failed(
    valid_execution_result_data: dict[str, object],
    error_code: ExecutionErrorCode,
) -> None:

    valid_execution_result_data.update(
        status=ExecutionStatus.FAILED,
        result=None,
        error_code=error_code,
        not_executed_reason=None,
    )

    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    assert execution_result.status == ExecutionStatus.FAILED
    assert execution_result.result is None
    assert execution_result.error_code == error_code
    assert execution_result.not_executed_reason is None


def test_execution_result_allows_success_without_result(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["result"] = None

    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    assert execution_result.status == ExecutionStatus.SUCCEEDED
    assert execution_result.result is None


@pytest.mark.parametrize(
    ("status", "result", "error_code", "reason"),
    [
        ("NOT_EXECUTED", {"unexpected": True}, None, "POLICY_BLOCKED"),
        ("NOT_EXECUTED", None, "TIMEOUT", "POLICY_BLOCKED"),
        ("NOT_EXECUTED", None, None, None),
        ("SUCCEEDED", None, "TIMEOUT", None),
        ("SUCCEEDED", None, None, "POLICY_BLOCKED"),
        ("FAILED", {"unexpected": True}, "TOOL_ERROR", None),
        ("FAILED", None, None, None),
        ("FAILED", None, "TOOL_ERROR", "POLICY_BLOCKED"),
    ],
)
def test_execution_result_rejects_invalid_status_fields(
    valid_execution_result_data: dict[str, object],
    status: str,
    result: object,
    error_code: str | None,
    reason: str | None,
) -> None:
    valid_execution_result_data.update(
        status=status,
        result=result,
        error_code=error_code,
        not_executed_reason=reason,
    )

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


@pytest.mark.parametrize(
    "invalid_action_id",
    ["", "   ", "\t"],
)
def test_execution_result_rejects_blank_action_id(
    valid_execution_result_data: dict[str, object],
    invalid_action_id: str,
) -> None:
    valid_execution_result_data["action_id"] = invalid_action_id

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


@pytest.mark.parametrize(
    "invalid_status",
    ["SUCCESS", "FAILED_UNKNOWN", "", "succeeded"],
)
def test_execution_result_rejects_invalid_status(
    valid_execution_result_data: dict[str, object],
    invalid_status: str,
) -> None:
    valid_execution_result_data["status"] = invalid_status

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)

@pytest.mark.parametrize(
    "missing_field",
    ["action_id", "status", "completed_at"],
)
def test_execution_result_rejects_missing_fields(
    valid_execution_result_data: dict[str, object],
    missing_field: str,
) -> None:
    del valid_execution_result_data[missing_field]

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)

def test_execution_result_rejects_extra_fields(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-28T10:00:00",
        "not-a-timestamp",
    ],
)
def test_execution_result_rejects_invalid_timestamp(
    valid_execution_result_data: dict[str, object],
    timestamp: str,
) -> None:
    valid_execution_result_data["completed_at"] = timestamp

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


def test_execution_result_normalizes_timestamp_to_utc(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["completed_at"] = "2026-10-28T12:00:00+02:00"

    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    assert execution_result.completed_at.isoformat() == "2026-10-28T10:00:00+00:00"


def test_execution_result_copies_and_freezes_nested_result(
    valid_execution_result_data: dict[str, object],
) -> None:
    original_result = {
        "metadata": {"tags": ["original"]},
    }
    valid_execution_result_data["result"] = original_result

    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    original_result["metadata"]["tags"].append("mutated")

    assert execution_result.result is not None
    assert list(execution_result.result["metadata"]["tags"]) == ["original"]

    with pytest.raises((TypeError, AttributeError)):
        execution_result.result["new_key"] = "value"  # type: ignore[index]

    with pytest.raises((TypeError, AttributeError)):
        execution_result.result["metadata"]["tags"].append("mutated")  # type: ignore[union-attr]


def test_execution_result_rejects_non_object_result(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["result"] = ["not", "an", "object"]

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


def test_execution_result_rejects_oversized_result(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["result"] = {"payload": "x" * 66_000}

    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(valid_execution_result_data)


def test_execution_result_is_immutable(
    valid_execution_result_data: dict[str, object],
) -> None:
    execution_result = ExecutionResult.model_validate(valid_execution_result_data)

    with pytest.raises(ValidationError):
        execution_result.action_id = "another-action"  # type: ignore[misc]


def test_verification_result_accepts_valid_success(
    valid_verification_result_data: dict[str, object],
) -> None:
    result = VerificationResult.model_validate(valid_verification_result_data)

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED
    assert result.evidence is not None


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
        ),
        (
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.OUTCOME_MISMATCH,
        ),
        (
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
        ),
        (
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_MISSING,
        ),
        (
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_CONFLICTING,
        ),
        (
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.VERIFIER_ERROR,
        ),
    ],
)
def test_verification_result_accepts_valid_status_reason_pairs(
    valid_verification_result_data: dict[str, object],
    status: VerificationStatus,
    reason_code: VerificationReasonCode,
) -> None:
    valid_verification_result_data.update(
        status=status,
        reason_code=reason_code,
    )

    result = VerificationResult.model_validate(valid_verification_result_data)

    assert result.status == status
    assert result.reason_code == reason_code


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.OUTCOME_MISMATCH,
        ),
        (
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
        ),
        (
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
        ),
    ],
)
def test_verification_result_rejects_invalid_status_reason_pairs(
    valid_verification_result_data: dict[str, object],
    status: VerificationStatus,
    reason_code: VerificationReasonCode,
) -> None:
    valid_verification_result_data.update(
        status=status,
        reason_code=reason_code,
    )

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.VERIFIED_SUCCESS,
        VerificationStatus.VERIFIED_FAILURE,
    ],
)
def test_verification_result_requires_evidence_for_conclusive_status(
    valid_verification_result_data: dict[str, object],
    status: VerificationStatus,
) -> None:
    valid_verification_result_data.update(
        status=status,
        evidence=None,
    )

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


def test_verification_result_allows_missing_evidence_when_inconclusive(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data.update(
        status=VerificationStatus.INCONCLUSIVE,
        reason_code=VerificationReasonCode.EVIDENCE_MISSING,
        evidence=None,
    )

    result = VerificationResult.model_validate(valid_verification_result_data)

    assert result.evidence is None


def test_verification_result_normalizes_timestamp_to_utc(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["verified_at"] = "2026-10-28T11:00:00+01:00"

    result = VerificationResult.model_validate(valid_verification_result_data)

    assert result.verified_at.utcoffset() == datetime.now(UTC).utcoffset()
    assert result.verified_at.hour == 10


def test_verification_result_rejects_string_enum_values(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["status"] = "VERIFIED_SUCCESS"

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


def test_verification_result_rejects_unknown_fields(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


@pytest.mark.parametrize(
    "field",
    ["action_id", "reason"],
)
@pytest.mark.parametrize("value", ["", " ", "\t", "\n"])
def test_verification_result_rejects_blank_text_fields(
    valid_verification_result_data: dict[str, object],
    field: str,
    value: str,
) -> None:
    valid_verification_result_data[field] = value

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


def test_verification_result_rejects_non_object_evidence(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["evidence"] = ["not", "an", "object"]

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


def test_verification_result_copies_and_freezes_nested_evidence(
    valid_verification_result_data: dict[str, object],
) -> None:
    original_evidence = {"metadata": {"tags": ["original"]}}
    valid_verification_result_data["evidence"] = original_evidence

    result = VerificationResult.model_validate(valid_verification_result_data)

    original_evidence["metadata"]["tags"].append("mutated")

    assert result.evidence is not None
    assert list(result.evidence["metadata"]["tags"]) == ["original"]

    with pytest.raises(TypeError):
        result.evidence["metadata"]["new_key"] = "value"

    with pytest.raises(AttributeError):
        result.evidence["metadata"]["tags"].append("another")


def test_verification_result_rejects_oversized_evidence(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["evidence"] = {"payload": "x" * 70_000}

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-28T10:00:00",
        datetime(2026, 10, 28, 10, 0, 0),
    ],
)
def test_verification_result_rejects_naive_timestamps(
    valid_verification_result_data: dict[str, object],
    timestamp: str | datetime,
) -> None:
    valid_verification_result_data["verified_at"] = timestamp

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)


@pytest.mark.parametrize(
    "missing_field",
    [
        "action_id",
        "status",
        "reason_code",
        "reason",
        "verified_at",
    ],
)
def test_verification_result_rejects_missing_required_field(
    valid_verification_result_data: dict[str, object],
    missing_field: str,
) -> None:
    del valid_verification_result_data[missing_field]

    with pytest.raises(ValidationError):
        VerificationResult.model_validate(valid_verification_result_data)

def test_verification_result_is_immutable(
    valid_verification_result_data: dict[str, object],
) -> None:
    result = VerificationResult.model_validate(valid_verification_result_data)

    with pytest.raises(ValidationError):
        result.reason = "Changed reason"


def _build_lifecycle_models(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
):
    proposal = ActionProposal.model_validate(valid_proposal_data)

    decision_data = dict(valid_policy_decision_data)
    decision_data["action_id"] = proposal.action_id
    decision_data["proposal_digest"] = compute_proposal_digest(proposal)
    decision = PolicyDecision.model_validate(decision_data)

    execution_data = dict(valid_execution_result_data)
    execution_data["action_id"] = proposal.action_id
    execution = ExecutionResult.model_validate(execution_data)

    verification_data = dict(valid_verification_result_data)
    verification_data["action_id"] = proposal.action_id
    verification = VerificationResult.model_validate(verification_data)

    return proposal, decision, execution, verification


def test_lifecycle_consistency_does_not_mutate_inputs(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
) -> None:
    proposal, decision, result, verification = _build_lifecycle_models(
        valid_proposal_data,
        valid_policy_decision_data,
        valid_execution_result_data,
        valid_verification_result_data,
    )

    models = (proposal, decision, result, verification)
    before = tuple(model.model_dump(mode="python") for model in models)

    check_lifecycle_consistency(proposal, decision, result, verification)

    after = tuple(model.model_dump(mode="python") for model in models)

    assert after == before


def test_lifecycle_consistency_performs_no_filesystem_or_network_io(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, decision, result, verification = _build_lifecycle_models(
        valid_proposal_data,
        valid_policy_decision_data,
        valid_execution_result_data,
        valid_verification_result_data,
    )

    def reject_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("Lifecycle checker attempted external I/O.")

    monkeypatch.setattr(builtins, "open", reject_io)
    monkeypatch.setattr(io, "open", reject_io)
    monkeypatch.setattr(os, "open", reject_io)
    monkeypatch.setattr(socket, "socket", reject_io)
    monkeypatch.setattr(socket, "create_connection", reject_io)
    monkeypatch.setattr(socket, "getaddrinfo", reject_io)

    assert (
        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            verification,
        )
        is None
    )

def test_lifecycle_consistency_accepts_allow_with_success(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=PolicyDecisionType.ALLOW,
        reason_code=PolicyReasonCode.ALLOWED_BY_POLICY,
    )
    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        error_code=None,
        not_executed_reason=None,
    )

    decision = PolicyDecision.model_validate(decision_data)
    result = ExecutionResult.model_validate(result_data)

    assert check_lifecycle_consistency(proposal, decision, result) is None


def test_lifecycle_consistency_rejects_mismatched_decision_action_id(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    decision_data = dict(valid_policy_decision_data)
    decision_data["proposal_digest"] = compute_proposal_digest(proposal)
    decision_data["action_id"] = "different-action"
    decision = PolicyDecision.model_validate(decision_data)

    with pytest.raises(ContractViolation, match="H1"):
        check_lifecycle_consistency(proposal, decision)


def test_lifecycle_consistency_rejects_mismatched_proposal_digest(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    decision_data = dict(valid_policy_decision_data)
    decision_data["action_id"] = proposal.action_id
    decision_data["proposal_digest"] = "0" * 64
    decision = PolicyDecision.model_validate(decision_data)

    with pytest.raises(ContractViolation, match="H2"):
        check_lifecycle_consistency(proposal, decision)




def test_lifecycle_consistency_rejects_mismatched_result_action_id(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
) -> None:
    proposal, decision, result, _ = _build_lifecycle_models(
        valid_proposal_data,
        valid_policy_decision_data,
        valid_execution_result_data,
        {
            "action_id": "placeholder",
            "status": VerificationStatus.INCONCLUSIVE,
            "reason_code": VerificationReasonCode.EVIDENCE_MISSING,
            "reason": "Not relevant",
            "evidence": None,
            "verified_at": "2026-10-28T10:00:00Z",
        },
    )
    result_data = dict(valid_execution_result_data)
    result_data["action_id"] = "different-action"
    result = ExecutionResult.model_validate(result_data)

    with pytest.raises(ContractViolation, match="H3"):
        check_lifecycle_consistency(proposal, decision, result)


def test_lifecycle_consistency_rejects_mismatched_verification_action_id(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
) -> None:
    proposal, decision, result, _ = _build_lifecycle_models(
        valid_proposal_data,
        valid_policy_decision_data,
        valid_execution_result_data,
        valid_verification_result_data,
    )
    verification_data = dict(valid_verification_result_data)
    verification_data["action_id"] = "different-action"
    verification = VerificationResult.model_validate(verification_data)

    with pytest.raises(ContractViolation, match="H4"):
        check_lifecycle_consistency(proposal, decision, result, verification)


def test_lifecycle_consistency_requires_execution_result_for_verification(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
    )
    decision = PolicyDecision.model_validate(decision_data)

    verification_data = dict(valid_verification_result_data)
    verification_data["action_id"] = proposal.action_id
    verification = VerificationResult.model_validate(verification_data)

    with pytest.raises(ContractViolation, match="H7"):
        check_lifecycle_consistency(proposal, decision, verification=verification)



@pytest.mark.parametrize(
    (
        "decision_type",
        "status",
        "not_executed_reason",
        "valid",
    ),
    [
        # ALLOW
        (PolicyDecisionType.ALLOW, ExecutionStatus.SUCCEEDED, None, True),
        (PolicyDecisionType.ALLOW, ExecutionStatus.FAILED, None, True),
        (
            PolicyDecisionType.ALLOW,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.INTEGRITY_CHECK_FAILED,
            True,
        ),
        (
            PolicyDecisionType.ALLOW,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.POLICY_BLOCKED,
            False,
        ),
        (
            PolicyDecisionType.ALLOW,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_PENDING,
            False,
        ),
        (
            PolicyDecisionType.ALLOW,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_DENIED,
            False,
        ),
        (
            PolicyDecisionType.ALLOW,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_EXPIRED,
            False,
        ),

        # BLOCK
        (PolicyDecisionType.BLOCK, ExecutionStatus.SUCCEEDED, None, False),
        (PolicyDecisionType.BLOCK, ExecutionStatus.FAILED, None, False),
        (
            PolicyDecisionType.BLOCK,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.POLICY_BLOCKED,
            True,
        ),
        (
            PolicyDecisionType.BLOCK,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.INTEGRITY_CHECK_FAILED,
            True,
        ),
        (
            PolicyDecisionType.BLOCK,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_PENDING,
            False,
        ),
        (
            PolicyDecisionType.BLOCK,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_DENIED,
            False,
        ),
        (
            PolicyDecisionType.BLOCK,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_EXPIRED,
            False,
        ),

        # REQUIRE_APPROVAL
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.SUCCEEDED,
            None,
            False,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.FAILED,
            None,
            False,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_PENDING,
            True,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_DENIED,
            True,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.APPROVAL_EXPIRED,
            True,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.INTEGRITY_CHECK_FAILED,
            True,
        ),
        (
            PolicyDecisionType.REQUIRE_APPROVAL,
            ExecutionStatus.NOT_EXECUTED,
            NotExecutedReason.POLICY_BLOCKED,
            False,
        ),
    ],
)
def test_lifecycle_consistency_decision_execution_matrix(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    decision_type: PolicyDecisionType,
    status: ExecutionStatus,
    not_executed_reason: NotExecutedReason | None,
    valid: bool,
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    decision_reasons = {
        PolicyDecisionType.ALLOW: PolicyReasonCode.ALLOWED_BY_POLICY,
        PolicyDecisionType.BLOCK: PolicyReasonCode.BLOCKED_BY_POLICY,
        PolicyDecisionType.REQUIRE_APPROVAL: PolicyReasonCode.APPROVAL_REQUIRED,
    }

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=decision_type,
        reason_code=decision_reasons[decision_type],
    )
    decision = PolicyDecision.model_validate(decision_data)

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=status,
        result={"order_status": "confirmed"}
        if status == ExecutionStatus.SUCCEEDED
        else None,
        error_code=(
            ExecutionErrorCode.TOOL_ERROR
            if status == ExecutionStatus.FAILED
            else None
        ),
        not_executed_reason=not_executed_reason,
    )
    result = ExecutionResult.model_validate(result_data)

    if valid:
        assert check_lifecycle_consistency(proposal, decision, result) is None
    else:
        expected_rule = (
            "H5" if status != ExecutionStatus.NOT_EXECUTED else "H6"
        )
        with pytest.raises(ContractViolation, match=expected_rule):
            check_lifecycle_consistency(proposal, decision, result)


@pytest.mark.parametrize(
    (
        "execution_status",
        "verification_status",
        "reason_code",
        "valid",
    ),
    [
        # NOT_EXECUTED
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
            False,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
            True,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.OUTCOME_MISMATCH,
            False,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
            True,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_MISSING,
            True,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_CONFLICTING,
            True,
        ),
        (
            ExecutionStatus.NOT_EXECUTED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.VERIFIER_ERROR,
            True,
        ),

        # SUCCEEDED
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
            True,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
            False,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.OUTCOME_MISMATCH,
            True,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
            False,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_MISSING,
            True,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_CONFLICTING,
            True,
        ),
        (
            ExecutionStatus.SUCCEEDED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.VERIFIER_ERROR,
            True,
        ),

        # FAILED
        (
            ExecutionStatus.FAILED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
            True,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.VERIFIED_SUCCESS,
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
            False,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.OUTCOME_MISMATCH,
            True,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.VERIFIED_FAILURE,
            VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
            False,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_MISSING,
            True,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.EVIDENCE_CONFLICTING,
            True,
        ),
        (
            ExecutionStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
            VerificationReasonCode.VERIFIER_ERROR,
            True,
        ),
    ],
)
def test_lifecycle_consistency_verification_matrix(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    valid_verification_result_data: dict[str, object],
    execution_status: ExecutionStatus,
    verification_status: VerificationStatus,
    reason_code: VerificationReasonCode,
    valid: bool,
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=(
            PolicyDecisionType.BLOCK
            if execution_status == ExecutionStatus.NOT_EXECUTED
            else PolicyDecisionType.ALLOW
        ),
        reason_code=(
            PolicyReasonCode.BLOCKED_BY_POLICY
            if execution_status == ExecutionStatus.NOT_EXECUTED
            else PolicyReasonCode.ALLOWED_BY_POLICY
        ),
    )
    decision = PolicyDecision.model_validate(decision_data)

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=execution_status,
        result=(
            {"order_status": "confirmed"}
            if execution_status == ExecutionStatus.SUCCEEDED
            else None
        ),
        error_code=(
            ExecutionErrorCode.TOOL_ERROR
            if execution_status == ExecutionStatus.FAILED
            else None
        ),
        not_executed_reason=(
            NotExecutedReason.POLICY_BLOCKED
            if execution_status == ExecutionStatus.NOT_EXECUTED
            else None
        ),
    )
    result = ExecutionResult.model_validate(result_data)

    verification_data = dict(valid_verification_result_data)
    verification_data.update(
        action_id=proposal.action_id,
        status=verification_status,
        reason_code=reason_code,
        evidence={"observed": "test-evidence"},
    )
    verification = VerificationResult.model_validate(verification_data)

    if valid:
        assert (
            check_lifecycle_consistency(
                proposal,
                decision,
                result,
                verification,
            )
            is None
        )
    else:
        expected_rule = (
            "H8"
            if execution_status == ExecutionStatus.NOT_EXECUTED
            else "H9"
        )
        with pytest.raises(ContractViolation, match=expected_rule):
            check_lifecycle_consistency(
                proposal,
                decision,
                result,
                verification,
            )
def test_action_proposal_normalizes_json_timestamp_to_utc(
    valid_proposal_data: dict[str, object],
) -> None:
    valid_proposal_data["created_at"] = "2026-10-28T12:00:00+02:00"

    proposal = ActionProposal.model_validate_json(
        json.dumps(valid_proposal_data)
    )

    assert proposal.created_at.tzinfo is UTC
    assert proposal.created_at.hour == 10


def test_execution_result_normalizes_json_timestamp_to_utc(
    valid_execution_result_data: dict[str, object],
) -> None:
    valid_execution_result_data["completed_at"] = (
        "2026-10-28T12:00:00+02:00"
    )

    result = ExecutionResult.model_validate_json(
        json.dumps(valid_execution_result_data)
    )

    assert result.completed_at.tzinfo is UTC
    assert result.completed_at.hour == 10


def test_verification_result_normalizes_json_timestamp_to_utc(
    valid_verification_result_data: dict[str, object],
) -> None:
    valid_verification_result_data["verified_at"] = (
        "2026-10-28T12:00:00+02:00"
    )

    result = VerificationResult.model_validate_json(
        json.dumps(valid_verification_result_data)
    )

    assert result.verified_at.tzinfo is UTC
    assert result.verified_at.hour == 10

def test_lifecycle_accepts_matching_approval_evidence(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    digest = compute_proposal_digest(proposal)

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=digest,
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason_code=PolicyReasonCode.APPROVAL_REQUIRED,
    )
    decision = PolicyDecision.model_validate(decision_data)

    approved_at = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    expires_at = approved_at + timedelta(minutes=15)

    evidence = ApprovalEvidence(
        approval_id="approval-test-001",
        action_id=proposal.action_id,
        proposal_digest=digest,
        policy_version=decision.policy_version,
        approved_at=approved_at,
        expires_at=expires_at,
    )

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={"order_status": "confirmed"},
        error_code=None,
        not_executed_reason=None,
        completed_at=approved_at + timedelta(seconds=30),
    )
    result = ExecutionResult.model_validate(result_data)

    assert (
        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            approval_evidence=evidence,
        )
        is None
    )


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED],
)
def test_lifecycle_rejects_approval_execution_without_evidence(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    status: ExecutionStatus,
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason_code=PolicyReasonCode.APPROVAL_REQUIRED,
    )
    decision = PolicyDecision.model_validate(decision_data)

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=status,
        result={"order_status": "confirmed"}
        if status == ExecutionStatus.SUCCEEDED
        else None,
        error_code=(
            ExecutionErrorCode.TOOL_ERROR
            if status == ExecutionStatus.FAILED
            else None
        ),
        not_executed_reason=None,
    )
    result = ExecutionResult.model_validate(result_data)

    with pytest.raises(ContractViolation, match="H5"):
        check_lifecycle_consistency(proposal, decision, result)


def test_lifecycle_rejects_approval_evidence_for_another_policy_version(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    digest = compute_proposal_digest(proposal)

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=digest,
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason_code=PolicyReasonCode.APPROVAL_REQUIRED,
    )
    decision = PolicyDecision.model_validate(decision_data)

    evidence = ApprovalEvidence(
        approval_id="approval-test-002",
        action_id=proposal.action_id,
        proposal_digest=digest,
        policy_version="different-policy-version",
        approved_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        expires_at=datetime(2026, 10, 1, 12, 15, tzinfo=UTC),
    )

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={"order_status": "confirmed"},
        error_code=None,
        not_executed_reason=None,
        completed_at=datetime(2026, 10, 1, 12, 1, tzinfo=UTC),
    )
    result = ExecutionResult.model_validate(result_data)

    with pytest.raises(ContractViolation, match="H12"):
        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            approval_evidence=evidence,
        )


@pytest.mark.parametrize(
    "completed_at",
    [
        datetime(2026, 10, 1, 11, 59, 59, tzinfo=UTC),
        datetime(2026, 10, 1, 12, 15, tzinfo=UTC),
    ],
)
def test_lifecycle_rejects_execution_outside_approval_window(
    valid_proposal_data: dict[str, object],
    valid_policy_decision_data: dict[str, object],
    valid_execution_result_data: dict[str, object],
    completed_at: datetime,
) -> None:
    proposal = ActionProposal.model_validate(valid_proposal_data)
    digest = compute_proposal_digest(proposal)

    decision_data = dict(valid_policy_decision_data)
    decision_data.update(
        action_id=proposal.action_id,
        proposal_digest=digest,
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason_code=PolicyReasonCode.APPROVAL_REQUIRED,
    )
    decision = PolicyDecision.model_validate(decision_data)

    evidence = ApprovalEvidence(
        approval_id="approval-test-003",
        action_id=proposal.action_id,
        proposal_digest=digest,
        policy_version=decision.policy_version,
        approved_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        expires_at=datetime(2026, 10, 1, 12, 15, tzinfo=UTC),
    )

    result_data = dict(valid_execution_result_data)
    result_data.update(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={"order_status": "confirmed"},
        error_code=None,
        not_executed_reason=None,
        completed_at=completed_at,
    )
    result = ExecutionResult.model_validate(result_data)

    with pytest.raises(ContractViolation, match="H13"):
        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            approval_evidence=evidence,
        )