"""Thread-safe, in-memory approval lifecycle service for AgentTrax."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import uuid4

from agenttrax.contracts.models import (
    ActionProposal,
    ApprovalEvidence,
    ContractViolation,
    PolicyDecision,
    PolicyDecisionType,
    compute_proposal_digest,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalStatus(StrEnum):
    """Lifecycle states for an in-memory approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True)
class _ApprovalRecord:
    """Private immutable record; transitions replace the stored instance."""

    proposal: ActionProposal
    decision: PolicyDecision
    proposal_digest: str
    policy_version: str
    requested_at: datetime
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: str | None = None
    approved_at: datetime | None = None
    evidence: ApprovalEvidence | None = None


class ApprovalService:
    """Manage exact-action approvals without executing simulator tools."""

    def __init__(
        self,
        clock: Callable[[], datetime] = _utc_now,
        ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        if not callable(clock):
            raise ValueError("Clock must be callable.")

        if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
            raise ValueError("Approval TTL must be a positive timedelta.")

        self._clock = clock
        self._ttl = ttl
        self._lock = Lock()
        self._records: dict[str, _ApprovalRecord] = {}

    def request_approval(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
    ) -> str:
        """Store an immutable proposal and its matching approval-required decision."""

        if not isinstance(proposal, ActionProposal):
            raise ContractViolation("Approval request requires an ActionProposal.")

        if not isinstance(decision, PolicyDecision):
            raise ContractViolation("Approval request requires a PolicyDecision.")

        if decision.decision != PolicyDecisionType.REQUIRE_APPROVAL:
            raise ContractViolation(
                "Only REQUIRE_APPROVAL decisions may create approval requests."
            )

        if decision.action_id != proposal.action_id:
            raise ContractViolation(
                "Approval decision action_id does not match proposal."
            )

        proposal_digest = compute_proposal_digest(proposal)

        if decision.proposal_digest != proposal_digest:
            raise ContractViolation(
                "Approval decision digest does not match proposal."
            )

        requested_at = self._read_clock()
        expires_at = requested_at + self._ttl

        approval_id = f"approval_{uuid4().hex}"
        record = _ApprovalRecord(
            proposal=proposal,
            decision=decision,
            proposal_digest=proposal_digest,
            policy_version=decision.policy_version,
            requested_at=requested_at,
            expires_at=expires_at,
        )

        with self._lock:
            if approval_id in self._records:
                raise ContractViolation("Duplicate approval identifier generated.")

            self._records[approval_id] = record

        return approval_id

    def approve(
        self,
        approval_id: str,
        approver_id: str,
    ) -> ApprovalEvidence:
        """Approve a pending request and return service-generated evidence."""

        self._validate_identifier(approval_id, "approval_id")
        self._validate_identifier(approver_id, "approver_id")

        with self._lock:
            record = self._get_record(approval_id)
            now = self._read_clock()
            record = self._expire_if_needed(approval_id, record, now)

            if record.status != ApprovalStatus.PENDING:
                raise ContractViolation(
                    f"Approval cannot be approved from state {record.status}."
                )

            evidence = ApprovalEvidence(
                approval_id=approval_id,
                action_id=record.proposal.action_id,
                proposal_digest=record.proposal_digest,
                policy_version=record.policy_version,
                approved_at=now,
                expires_at=record.expires_at,
            )

            self._records[approval_id] = replace(
                record,
                status=ApprovalStatus.APPROVED,
                approver_id=approver_id,
                approved_at=now,
                evidence=evidence,
            )

            return evidence

    def deny(
        self,
        approval_id: str,
        approver_id: str,
    ) -> None:
        """Deny a pending request; denied requests cannot be revived."""

        self._validate_identifier(approval_id, "approval_id")
        self._validate_identifier(approver_id, "approver_id")

        with self._lock:
            record = self._get_record(approval_id)
            now = self._read_clock()
            record = self._expire_if_needed(approval_id, record, now)

            if record.status != ApprovalStatus.PENDING:
                raise ContractViolation(
                    f"Approval cannot be denied from state {record.status}."
                )

            self._records[approval_id] = replace(
                record,
                status=ApprovalStatus.DENIED,
                approver_id=approver_id,
                approved_at=None,
                evidence=None,
            )

    def get_status(self, approval_id: str) -> ApprovalStatus:
        """Return the current state, applying expiry at the exact boundary."""

        self._validate_identifier(approval_id, "approval_id")

        with self._lock:
            record = self._get_record(approval_id)
            now = self._read_clock()
            record = self._expire_if_needed(approval_id, record, now)
            return record.status
    def _get_execution_record(
        self,
        approval_id: str,
    ) -> tuple[
        ActionProposal,
        PolicyDecision,
        ApprovalStatus,
        ApprovalEvidence | None,
    ]:
        """Return the stored execution context without consuming approval."""

        self._validate_identifier(approval_id, "approval_id")

        with self._lock:
            record = self._get_record(approval_id)
            now = self._read_clock()
            record = self._expire_if_needed(approval_id, record, now)

            return (
                record.proposal,
                record.decision,
                record.status,
                record.evidence,
            )

    def _consume_approved(
        self,
        approval_id: str,
    ) -> tuple[ActionProposal, PolicyDecision, ApprovalEvidence]:
        """Atomically consume an approved record for one executor invocation."""

        self._validate_identifier(approval_id, "approval_id")

        with self._lock:
            record = self._get_record(approval_id)
            now = self._read_clock()
            record = self._expire_if_needed(approval_id, record, now)

            if record.status != ApprovalStatus.APPROVED:
                raise ContractViolation(
                    f"Approval cannot be consumed from state {record.status}."
                )

            if record.evidence is None:
                raise ContractViolation(
                    "Approved record is missing service-generated evidence."
                )

            self._records[approval_id] = replace(
                record,
                status=ApprovalStatus.CONSUMED,
            )

            return record.proposal, record.decision, record.evidence

    def _get_record(self, approval_id: str) -> _ApprovalRecord:
        record = self._records.get(approval_id)

        if record is None:
            raise ContractViolation("Unknown approval identifier.")

        return record

    def _expire_if_needed(
        self,
        approval_id: str,
        record: _ApprovalRecord,
        now: datetime,
    ) -> _ApprovalRecord:
        if (
            record.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}
            and now >= record.expires_at
        ):
            record = replace(record, status=ApprovalStatus.EXPIRED)
            self._records[approval_id] = record

        return record

    def _read_clock(self) -> datetime:
        now = self._clock()

        if not isinstance(now, datetime):
            raise ContractViolation("Approval clock must return a datetime.")

        if now.tzinfo is None or now.utcoffset() is None:
            raise ContractViolation("Approval clock must return an aware datetime.")

        return now.astimezone(UTC)

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ContractViolation(f"{field_name} must be a nonblank string.")
