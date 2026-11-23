
"""Thread-safe, in-memory recorder for correlated AgentTrax lifecycle events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from agenttrax.contracts.models import (
    ActionProposal,
    ApprovalEvidence,
    ContractViolation,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    PolicyDecisionType,
    TaskVerificationResult,
    VerificationResult,
    check_lifecycle_consistency,
    compute_proposal_digest,
)
from agenttrax.contracts.tracing import (
    TraceEvent,
    TraceEventType,
    sanitize_details,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_event_id() -> str:
    return f"trace_{uuid4().hex}"


class TraceRecorder:
    """Record immutable, correlated lifecycle events in deterministic order."""

    def __init__(
        self,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = _new_event_id,
    ) -> None:
        if not callable(clock):
            raise ValueError("Clock must be callable.")

        if not callable(id_factory):
            raise ValueError("ID factory must be callable.")

        self._clock = clock
        self._id_factory = id_factory
        self._lock = RLock()
        self._events: list[TraceEvent] = []
        self._sequence = 0

    def record_proposal(self, proposal: ActionProposal) -> TraceEvent:
        """Record a validated action proposal without its raw arguments."""
        self._validate_proposal(proposal)

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.PROPOSAL_CREATED,
            details={
                "tool_name": proposal.tool_name,
                "proposal_digest": compute_proposal_digest(proposal),
            },
        )

    def record_policy_decision(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
    ) -> TraceEvent:
        """Record a policy decision linked to the exact proposal."""
        self._validate_linkage(proposal, decision)

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.POLICY_DECIDED,
            details={
                "decision": decision.decision.value,
                "reason_code": decision.reason_code.value,
                "policy_version": decision.policy_version,
                "proposal_digest": decision.proposal_digest,
            },
        )

    def record_approval_requested(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        approval_id: str,
    ) -> TraceEvent:
        """Record an approval request after the service creates it."""
        self._validate_linkage(proposal, decision)
        self._validate_approval_decision(decision)
        self._validate_identifier(approval_id, "approval_id")

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.APPROVAL_REQUESTED,
            details={
                "approval_id": approval_id,
                "proposal_digest": decision.proposal_digest,
                "policy_version": decision.policy_version,
            },
        )

    def record_approval_granted(
        self,
        proposal: ActionProposal,
        evidence: ApprovalEvidence,
    ) -> TraceEvent:
        """Record service-generated approval evidence."""
        self._validate_proposal(proposal)

        if not isinstance(evidence, ApprovalEvidence):
            raise ContractViolation(
                "Approval grant requires ApprovalEvidence."
            )

        self._validate_identifier(evidence.approval_id, "approval_id")

        if evidence.action_id != proposal.action_id:
            raise ContractViolation(
                "Approval evidence action_id does not match proposal."
            )

        if evidence.proposal_digest != compute_proposal_digest(proposal):
            raise ContractViolation(
                "Approval evidence digest does not match proposal."
            )

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.APPROVAL_GRANTED,
            details={
                "approval_id": evidence.approval_id,
                "proposal_digest": evidence.proposal_digest,
                "policy_version": evidence.policy_version,
                "approved_at": evidence.approved_at.isoformat(),
                "expires_at": evidence.expires_at.isoformat(),
            },
        )

    def record_approval_denied(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        approval_id: str,
    ) -> TraceEvent:
        """Record a denial after the approval service confirms it."""
        self._validate_approval_context(proposal, decision, approval_id)

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.APPROVAL_DENIED,
            details={
                "approval_id": approval_id,
                "proposal_digest": decision.proposal_digest,
                "policy_version": decision.policy_version,
            },
        )

    def record_approval_expired(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        approval_id: str,
    ) -> TraceEvent:
        """Record expiry after the approval service confirms expiration."""
        self._validate_approval_context(proposal, decision, approval_id)

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.APPROVAL_EXPIRED,
            details={
                "approval_id": approval_id,
                "proposal_digest": decision.proposal_digest,
                "policy_version": decision.policy_version,
            },
        )

    def record_execution_started(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> TraceEvent:
        """Record an explicitly reported start of actual tool execution."""
        self._validate_linkage(proposal, decision)
        self._validate_execution_authorization(decision, approval_evidence)

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.EXECUTION_STARTED,
            details={
                "tool_name": proposal.tool_name,
                "proposal_digest": decision.proposal_digest,
                "policy_version": decision.policy_version,
                "approval_id": (
                    approval_evidence.approval_id
                    if approval_evidence is not None
                    else None
                ),
            },
        )

    def record_execution_result(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        result: ExecutionResult,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> TraceEvent:
        """Record the actual executor result after lifecycle validation."""
        self._validate_linkage(proposal, decision)

        if not isinstance(result, ExecutionResult):
            raise ContractViolation(
                "Execution result must be an ExecutionResult."
            )

        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            approval_evidence=approval_evidence,
        )

        if result.status == ExecutionStatus.SUCCEEDED:
            event_type = TraceEventType.EXECUTION_SUCCEEDED
        elif result.status == ExecutionStatus.FAILED:
            event_type = TraceEventType.EXECUTION_FAILED
        else:
            event_type = TraceEventType.EXECUTION_SKIPPED

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=event_type,
            details={
                "execution_status": result.status.value,
                "error_code": (
                    result.error_code.value
                    if result.error_code is not None
                    else None
                ),
                "not_executed_reason": (
                    result.not_executed_reason.value
                    if result.not_executed_reason is not None
                    else None
                ),
                "completed_at": result.completed_at.isoformat(),
            },
        )

    def record_action_verification(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        result: ExecutionResult,
        verification: VerificationResult,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> TraceEvent:
        """Record verification of one action, not overall task completion."""
        self._validate_linkage(proposal, decision)

        if not isinstance(verification, VerificationResult):
            raise ContractViolation(
                "Action verification requires VerificationResult."
            )

        check_lifecycle_consistency(
            proposal,
            decision,
            result,
            verification=verification,
            approval_evidence=approval_evidence,
        )

        return self._record(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            event_type=TraceEventType.VERIFICATION_COMPLETED,
            details={
                "verification_scope": "ACTION",
                "verification_status": verification.status.value,
                "reason_code": verification.reason_code.value,
                "verified_at": verification.verified_at.isoformat(),
            },
        )

    def record_task_verification(
        self,
        task_id: str,
        verification: TaskVerificationResult,
    ) -> TraceEvent:
        """Record explicit task-level verification with no action linkage."""
        self._validate_identifier(task_id, "task_id")

        if not isinstance(verification, TaskVerificationResult):
            raise ContractViolation(
                "Task verification requires TaskVerificationResult."
            )

        return self._record(
            task_id=task_id,
            action_id=None,
            event_type=TraceEventType.VERIFICATION_COMPLETED,
            details={
                "verification_scope": "TASK",
                "verification_status": verification.status.value,
                "reason_code": verification.reason_code.value,
                "verified_at": verification.verified_at.isoformat(),
            },
        )

    def get_events(self) -> tuple[TraceEvent, ...]:
        """Return an immutable snapshot of all recorded events."""
        with self._lock:
            return tuple(self._events)

    def get_task_events(self, task_id: str) -> tuple[TraceEvent, ...]:
        """Return an immutable snapshot of events for one task."""
        self._validate_identifier(task_id, "task_id")

        with self._lock:
            return tuple(
                event for event in self._events
                if event.task_id == task_id
            )

    def reset(self) -> None:
        """Clear recorded events and restart sequence numbering."""
        with self._lock:
            self._events.clear()
            self._sequence = 0

    def _record(
        self,
        task_id: str,
        action_id: str | None,
        event_type: TraceEventType,
        details: dict[str, object],
    ) -> TraceEvent:
        """Append atomically; failed records never consume a sequence."""
        with self._lock:
            next_sequence = self._sequence + 1

            sanitized = sanitize_details(details)

            event = TraceEvent(
                event_id=self._read_event_id(),
                task_id=task_id,
                action_id=action_id,
                event_type=event_type,
                sequence=next_sequence,
                timestamp=self._read_clock(),
                details=sanitized,
            )

            self._events.append(event)
            self._sequence = next_sequence

            return event

    def _read_clock(self) -> datetime:
        now = self._clock()

        if not isinstance(now, datetime):
            raise ContractViolation(
                "Trace clock must return a datetime."
            )

        if now.tzinfo is None or now.utcoffset() is None:
            raise ContractViolation(
                "Trace clock must return an aware datetime."
            )

        return now.astimezone(UTC)

    def _read_event_id(self) -> str:
        event_id = self._id_factory()
        self._validate_identifier(event_id, "event_id")
        return event_id

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ContractViolation(
                f"{field_name} must be a nonblank string."
            )

    @staticmethod
    def _validate_proposal(proposal: ActionProposal) -> None:
        if not isinstance(proposal, ActionProposal):
            raise ContractViolation(
                "Expected an ActionProposal."
            )

    @classmethod
    def _validate_linkage(
        cls,
        proposal: ActionProposal,
        decision: PolicyDecision,
    ) -> None:
        cls._validate_proposal(proposal)

        if not isinstance(decision, PolicyDecision):
            raise ContractViolation(
                "Expected a PolicyDecision."
            )

        if decision.action_id != proposal.action_id:
            raise ContractViolation(
                "Decision action_id does not match proposal."
            )

        if decision.proposal_digest != compute_proposal_digest(proposal):
            raise ContractViolation(
                "Decision digest does not match proposal."
            )

    @staticmethod
    def _validate_approval_decision(
        decision: PolicyDecision,
    ) -> None:
        if decision.decision != PolicyDecisionType.REQUIRE_APPROVAL:
            raise ContractViolation(
                "Approval events require a REQUIRE_APPROVAL decision."
            )

    @classmethod
    def _validate_approval_context(
        cls,
        proposal: ActionProposal,
        decision: PolicyDecision,
        approval_id: str,
    ) -> None:
        cls._validate_linkage(proposal, decision)
        cls._validate_approval_decision(decision)
        cls._validate_identifier(approval_id, "approval_id")

    @classmethod
    def _validate_execution_authorization(
        cls,
        decision: PolicyDecision,
        approval_evidence: ApprovalEvidence | None,
    ) -> None:
        if decision.decision == PolicyDecisionType.ALLOW:
            if approval_evidence is not None:
                raise ContractViolation(
                    "ALLOW execution must not include approval evidence."
                )
            return

        if decision.decision != PolicyDecisionType.REQUIRE_APPROVAL:
            raise ContractViolation(
                "Execution cannot start for a BLOCK decision."
            )

        if not isinstance(approval_evidence, ApprovalEvidence):
            raise ContractViolation(
                "Approved execution requires ApprovalEvidence."
            )

        if approval_evidence.action_id != decision.action_id:
            raise ContractViolation(
                "Approval evidence action_id does not match decision."
            )

        if approval_evidence.proposal_digest != decision.proposal_digest:
            raise ContractViolation(
                "Approval evidence digest does not match decision."
            )

        if approval_evidence.policy_version != decision.policy_version:
            raise ContractViolation(
                "Approval evidence policy version does not match decision."
            )
