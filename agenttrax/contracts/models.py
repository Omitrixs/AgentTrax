"""Pydantic contract models for AgentTrax."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agenttrax.contracts.serialization import (
    PROPOSAL_DIGEST_HEX_LENGTH,
    FrozenJsonObject,
    canonical_json_bytes,
    enforce_json_limits,
    thaw_json_value,
)


class ContractViolation(Exception):
    """Raised when lifecycle contracts violate cross-contract invariants."""

class StrictContractModel(BaseModel):
    """Shared configuration for immutable, strictly validated contracts."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        arbitrary_types_allowed=True,
    )


NonBlankString = Annotated[str, Field(min_length=1)]


def _validate_nonblank_string(value: str) -> str:
    if not value.strip():
        raise ValueError("Value must contain at least one non-whitespace character.")
    return value


def _validate_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must be timezone-aware.")
    return value.astimezone(UTC)


class ActionProposal(StrictContractModel):
    """A proposed tool action, before policy evaluation or execution."""

    action_id: NonBlankString
    task_id: NonBlankString
    tool_name: NonBlankString
    arguments: FrozenJsonObject
    requested_by: NonBlankString
    created_at: datetime

    @field_validator("action_id", "task_id", "tool_name", "requested_by")
    @classmethod
    def validate_nonblank_fields(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_and_copy_arguments(cls, value: object) -> FrozenJsonObject:
        if type(value) is not dict:
            raise ValueError("Arguments must be a JSON object.")

        try:
            enforce_json_limits(value)
            return FrozenJsonObject(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid arguments: {exc}") from exc

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError("Timestamp string must include a timezone offset.")

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)


class PolicyDecisionType(StrEnum):
    """Possible outcomes of a policy evaluation."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyReasonCode(StrEnum):
    """Machine-readable reasons for a policy decision."""

    ALLOWED_BY_POLICY = "ALLOWED_BY_POLICY"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    MALFORMED_DECISION = "MALFORMED_DECISION"


class ExecutionStatus(StrEnum):
    """Possible outcomes at the execution boundary."""

    NOT_EXECUTED = "NOT_EXECUTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExecutionErrorCode(StrEnum):
    """Machine-readable reasons for execution failure."""

    TOOL_ERROR = "TOOL_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_RESULT = "INVALID_RESULT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class NotExecutedReason(StrEnum):
    """Why an action did not reach execution."""

    POLICY_BLOCKED = "POLICY_BLOCKED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    INTEGRITY_CHECK_FAILED = "INTEGRITY_CHECK_FAILED"


class PolicyDecision(StrictContractModel):
    """A policy decision bound to a specific proposal digest."""

    action_id: NonBlankString
    proposal_digest: str
    decision: PolicyDecisionType
    reason_code: PolicyReasonCode
    reason: NonBlankString
    policy_version: NonBlankString

    @field_validator("action_id", "reason", "policy_version")
    @classmethod
    def validate_nonblank_fields(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("proposal_digest")
    @classmethod
    def validate_proposal_digest(cls, value: str) -> str:
        if (
            re.fullmatch(
                rf"[0-9a-f]{{{PROPOSAL_DIGEST_HEX_LENGTH}}}",
                value,
            )
            is None
        ):
            raise ValueError(
                "Proposal digest must contain exactly "
                f"{PROPOSAL_DIGEST_HEX_LENGTH} lowercase hexadecimal characters."
            )
        return value

    @model_validator(mode="after")
    def validate_decision_reason_pair(self) -> PolicyDecision:
        allowed_reason_codes = {
            PolicyDecisionType.ALLOW: {PolicyReasonCode.ALLOWED_BY_POLICY},
            PolicyDecisionType.REQUIRE_APPROVAL: {PolicyReasonCode.APPROVAL_REQUIRED},
            PolicyDecisionType.BLOCK: {
                PolicyReasonCode.BLOCKED_BY_POLICY,
                PolicyReasonCode.UNKNOWN_TOOL,
                PolicyReasonCode.INVALID_ARGUMENTS,
                PolicyReasonCode.MALFORMED_DECISION,
            },
        }

        if self.reason_code not in allowed_reason_codes[self.decision]:
            raise ValueError(
                f"Reason code {self.reason_code.value} is not valid "
                f"for decision {self.decision.value}."
            )

        return self


class ExecutionResult(StrictContractModel):
    """A record of what happened at the execution boundary."""

    action_id: NonBlankString
    status: ExecutionStatus
    result: FrozenJsonObject | None = None
    error_code: ExecutionErrorCode | None = None
    not_executed_reason: NotExecutedReason | None = None
    completed_at: datetime

    @field_validator("action_id")
    @classmethod
    def validate_action_id(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("result", mode="before")
    @classmethod
    def validate_and_copy_result(cls, value: object) -> FrozenJsonObject | None:
        if value is None:
            return None
        if type(value) is not dict:
            raise ValueError("Execution result must be a JSON object or None.")

        try:
            enforce_json_limits(value)
            return FrozenJsonObject(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid execution result: {exc}") from exc

    @field_validator("completed_at", mode="before")
    @classmethod
    def validate_completed_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError("Timestamp string must include a timezone offset.")

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)

    @model_validator(mode="after")
    def validate_status_fields(self) -> ExecutionResult:
        if self.status == ExecutionStatus.NOT_EXECUTED:
            if self.result is not None:
                raise ValueError("NOT_EXECUTED requires result to be None.")
            if self.error_code is not None:
                raise ValueError("NOT_EXECUTED requires error_code to be None.")
            if self.not_executed_reason is None:
                raise ValueError("NOT_EXECUTED requires a not_executed_reason.")

        elif self.status == ExecutionStatus.SUCCEEDED:
            if self.error_code is not None:
                raise ValueError("SUCCEEDED requires error_code to be None.")
            if self.not_executed_reason is not None:
                raise ValueError("SUCCEEDED requires not_executed_reason to be None.")

        elif self.status == ExecutionStatus.FAILED:
            if self.result is not None:
                raise ValueError("FAILED requires result to be None.")
            if self.error_code is None:
                raise ValueError("FAILED requires an error_code.")
            if self.not_executed_reason is not None:
                raise ValueError("FAILED requires not_executed_reason to be None.")

        return self


class VerificationStatus(StrEnum):
    """Possible outcomes of independent verification."""

    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationReasonCode(StrEnum):
    """Machine-readable reasons for a verification outcome."""

    OUTCOME_MATCHES_EXPECTED = "OUTCOME_MATCHES_EXPECTED"
    NO_CHANGE_CONFIRMED = "NO_CHANGE_CONFIRMED"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    UNEXPECTED_STATE_CHANGE = "UNEXPECTED_STATE_CHANGE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_CONFLICTING = "EVIDENCE_CONFLICTING"
    VERIFIER_ERROR = "VERIFIER_ERROR"


class VerificationResult(StrictContractModel):
    """An independent assessment of an action's observed outcome."""

    action_id: NonBlankString
    status: VerificationStatus
    reason_code: VerificationReasonCode
    reason: NonBlankString
    evidence: FrozenJsonObject | None = None
    verified_at: datetime

    @field_validator("action_id", "reason")
    @classmethod
    def validate_nonblank_fields(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_and_copy_evidence(cls, value: object) -> FrozenJsonObject | None:
        if value is None:
            return None
        if type(value) is not dict:
            raise ValueError("Verification evidence must be a JSON object or None.")

        try:
            enforce_json_limits(value)
            return FrozenJsonObject(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid verification evidence: {exc}") from exc

    @field_validator("verified_at", mode="before")
    @classmethod
    def validate_verified_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError("Timestamp string must include a timezone offset.")

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)

    @model_validator(mode="after")
    def validate_status_reason_pair(self) -> VerificationResult:
        allowed_reason_codes = {
            VerificationStatus.VERIFIED_SUCCESS: {
                VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
                VerificationReasonCode.NO_CHANGE_CONFIRMED,
            },
            VerificationStatus.VERIFIED_FAILURE: {
                VerificationReasonCode.OUTCOME_MISMATCH,
                VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
            },
            VerificationStatus.INCONCLUSIVE: {
                VerificationReasonCode.EVIDENCE_MISSING,
                VerificationReasonCode.EVIDENCE_CONFLICTING,
                VerificationReasonCode.VERIFIER_ERROR,
            },
        }

        if self.reason_code not in allowed_reason_codes[self.status]:
            raise ValueError(
                f"Reason code {self.reason_code.value} is not valid "
                f"for verification status {self.status.value}."
            )

        if (
            self.status
            in {
                VerificationStatus.VERIFIED_SUCCESS,
                VerificationStatus.VERIFIED_FAILURE,
            }
            and self.evidence is None
        ):
            raise ValueError(f"{self.status.value} requires verification evidence.")

        return self


class TaskVerificationResult(StrictContractModel):
    """An independent assessment of whether the overall task objective was met."""

    status: VerificationStatus
    reason_code: VerificationReasonCode
    reason: NonBlankString
    evidence: FrozenJsonObject | None = None
    verified_at: datetime

    @field_validator("reason")
    @classmethod
    def validate_nonblank_reason(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_and_copy_evidence(cls, value: object) -> FrozenJsonObject | None:
        if value is None:
            return None
        if type(value) is not dict:
            raise ValueError(
    "Task verification evidence must be a JSON object or None."
)

        try:
            enforce_json_limits(value)
            return FrozenJsonObject(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid task verification evidence: {exc}") from exc

    @field_validator("verified_at", mode="before")
    @classmethod
    def validate_verified_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError("Timestamp string must include a timezone offset.")

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)

    @model_validator(mode="after")
    def validate_status_reason_pair(self) -> TaskVerificationResult:
        allowed_reason_codes = {
            VerificationStatus.VERIFIED_SUCCESS: {
                VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
            },
            VerificationStatus.VERIFIED_FAILURE: {
                VerificationReasonCode.OUTCOME_MISMATCH,
                VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
            },
            VerificationStatus.INCONCLUSIVE: {
                VerificationReasonCode.EVIDENCE_MISSING,
                VerificationReasonCode.EVIDENCE_CONFLICTING,
                VerificationReasonCode.VERIFIER_ERROR,
            },
        }

        if self.reason_code not in allowed_reason_codes[self.status]:
            raise ValueError(
                f"Reason code {self.reason_code.value} is not valid "
                f"for task verification status {self.status.value}."
            )

        if (
            self.status
            in {
                VerificationStatus.VERIFIED_SUCCESS,
                VerificationStatus.VERIFIED_FAILURE,
            }
            and self.evidence is None
        ):
            raise ValueError(
                f"{self.status.value} requires task verification evidence."
            )

        return self



def compute_proposal_digest(proposal: ActionProposal) -> str:
    """Compute the version-1 SHA-256 digest, excluding created_at."""
    payload = {
        "action_id": proposal.action_id,
        "task_id": proposal.task_id,
        "tool_name": proposal.tool_name,
        "arguments": thaw_json_value(proposal.arguments),
        "requested_by": proposal.requested_by,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def check_lifecycle_consistency(
    proposal: ActionProposal,
    decision: PolicyDecision,
    result: ExecutionResult | None = None,
    verification: VerificationResult | None = None,
    approval_evidence: ApprovalEvidence | None = None,
) -> None:
    """Raise ContractViolation when lifecycle invariants are violated."""

    if decision.action_id != proposal.action_id:
        raise ContractViolation(
            "H1: Decision action_id does not match proposal."
        )

    if decision.proposal_digest != compute_proposal_digest(proposal):
        raise ContractViolation(
            "H2: Decision digest does not match proposal."
        )

    if result is not None and result.action_id != proposal.action_id:
        raise ContractViolation(
            "H3: Execution result action_id does not match proposal."
        )

    if verification is not None and verification.action_id != proposal.action_id:
        raise ContractViolation(
            "H4: Verification action_id does not match proposal."
        )

    if verification is not None and result is None:
        raise ContractViolation(
            "H7: Verification requires an execution result."
        )

    if result is not None:
        status = result.status
        reason = result.not_executed_reason

        if decision.decision == PolicyDecisionType.ALLOW:
            allowed_statuses = {
                ExecutionStatus.SUCCEEDED,
                ExecutionStatus.FAILED,
                ExecutionStatus.NOT_EXECUTED,
            }
            allowed_reasons = {
                NotExecutedReason.INTEGRITY_CHECK_FAILED,
            }

        elif decision.decision == PolicyDecisionType.BLOCK:
            allowed_statuses = {
                ExecutionStatus.NOT_EXECUTED,
            }
            allowed_reasons = {
                NotExecutedReason.POLICY_BLOCKED,
                NotExecutedReason.INTEGRITY_CHECK_FAILED,
            }

        else:
            allowed_statuses = {
                ExecutionStatus.NOT_EXECUTED,
            }

            if approval_evidence is not None:
                allowed_statuses.update(
                    {
                        ExecutionStatus.SUCCEEDED,
                        ExecutionStatus.FAILED,
                    }
                )

            allowed_reasons = {
                NotExecutedReason.APPROVAL_PENDING,
                NotExecutedReason.APPROVAL_DENIED,
                NotExecutedReason.APPROVAL_EXPIRED,
                NotExecutedReason.INTEGRITY_CHECK_FAILED,
            }

        if status not in allowed_statuses:
            raise ContractViolation(
                "H5: Execution status is not allowed for the policy decision."
            )

        if (
            status == ExecutionStatus.NOT_EXECUTED
            and reason not in allowed_reasons
        ):
            raise ContractViolation(
                "H6: Not-executed reason is not allowed for the policy decision."
            )

    # H11-H13: Approval evidence is valid only for an approved execution.
    if approval_evidence is not None:
        if not isinstance(approval_evidence, ApprovalEvidence):
            raise ContractViolation(
                "H11: Approval evidence must be an ApprovalEvidence contract."
            )

        if decision.decision != PolicyDecisionType.REQUIRE_APPROVAL:
            raise ContractViolation(
                "H11: Approval evidence requires REQUIRE_APPROVAL."
            )

        if result is None or result.status not in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
        }:
            raise ContractViolation(
                "H11: Approval evidence requires a SUCCEEDED or FAILED result."
            )

        if approval_evidence.action_id != proposal.action_id:
            raise ContractViolation(
                "H12: Approval evidence action_id does not match proposal."
            )

        if approval_evidence.proposal_digest != compute_proposal_digest(proposal):
            raise ContractViolation(
                "H12: Approval evidence digest does not match proposal."
            )

        if approval_evidence.policy_version != decision.policy_version:
            raise ContractViolation(
                "H12: Approval evidence policy version does not match decision."
            )

        if not (
            approval_evidence.approved_at
            <= result.completed_at
            < approval_evidence.expires_at
        ):
            raise ContractViolation(
                "H13: Execution completion must occur after approval "
                "and before approval expiry."
            )

    if verification is not None:
        if result.status == ExecutionStatus.NOT_EXECUTED:
            if (
                verification.status == VerificationStatus.VERIFIED_SUCCESS
                and verification.reason_code
                != VerificationReasonCode.NO_CHANGE_CONFIRMED
            ):
                raise ContractViolation(
                    "H8: NOT_EXECUTED requires NO_CHANGE_CONFIRMED "
                    "for VERIFIED_SUCCESS."
                )

            if (
                verification.status == VerificationStatus.VERIFIED_FAILURE
                and verification.reason_code
                != VerificationReasonCode.UNEXPECTED_STATE_CHANGE
            ):
                raise ContractViolation(
                    "H8: NOT_EXECUTED requires UNEXPECTED_STATE_CHANGE "
                    "for VERIFIED_FAILURE."
                )

        elif verification.reason_code in {
            VerificationReasonCode.NO_CHANGE_CONFIRMED,
            VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
        }:
            raise ContractViolation(
                "H9: NO_CHANGE_CONFIRMED and UNEXPECTED_STATE_CHANGE "
                "require NOT_EXECUTED."
            )

    # H10: INCONCLUSIVE is permitted with any execution status.


class ApprovalEvidence(StrictContractModel):
    """Immutable evidence that a specific pending action was approved."""

    approval_id: NonBlankString
    action_id: NonBlankString
    proposal_digest: str
    policy_version: NonBlankString
    approved_at: datetime
    expires_at: datetime

    @field_validator(
        "approval_id",
        "action_id",
        "policy_version",
    )
    @classmethod
    def validate_nonblank_fields(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("proposal_digest")
    @classmethod
    def validate_proposal_digest(cls, value: str) -> str:
        if (
            re.fullmatch(
                rf"[0-9a-f]{{{PROPOSAL_DIGEST_HEX_LENGTH}}}",
                value,
            )
            is None
        ):
            raise ValueError(
                "Proposal digest must contain exactly "
                f"{PROPOSAL_DIGEST_HEX_LENGTH} lowercase hexadecimal characters."
            )
        return value

    @field_validator("approved_at", "expires_at", mode="before")
    @classmethod
    def validate_timestamps(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError(
                    "Timestamp string must include a timezone offset."
                )

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> ApprovalEvidence:
        if self.expires_at <= self.approved_at:
            raise ValueError("Approval expiry must be later than approval time.")
        return self
