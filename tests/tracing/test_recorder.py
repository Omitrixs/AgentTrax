
"""Acceptance tests for the AgentTrax lifecycle trace recorder."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest

from agenttrax.contracts.models import (
    ActionProposal,
    ContractViolation,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    NotExecutedReason,
    PolicyDecision,
    PolicyDecisionType,
    PolicyReasonCode,
    TaskVerificationResult,
    VerificationReasonCode,
    VerificationResult,
    VerificationStatus,
    compute_proposal_digest,
)
from agenttrax.contracts.tracing import TraceEventType
from agenttrax.execution.approval import ApprovalService, ApprovalStatus
from agenttrax.tracing import TraceRecorder

FIXED_TIME = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    """Return a deterministic UTC timestamp."""
    return FIXED_TIME


def make_proposal(
    action_id: str = "action-001",
    task_id: str = "task-001",
    tool_name: str = "get_order",
    arguments: dict[str, Any] | None = None,
) -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        task_id=task_id,
        tool_name=tool_name,
        arguments=arguments or {"order_id": "ord_demo_001"},
        requested_by="test-agent",
        created_at=FIXED_TIME,
    )


def make_decision(
    proposal: ActionProposal,
    decision_type: PolicyDecisionType = PolicyDecisionType.ALLOW,
) -> PolicyDecision:
    reason_codes = {
        PolicyDecisionType.ALLOW: PolicyReasonCode.ALLOWED_BY_POLICY,
        PolicyDecisionType.BLOCK: PolicyReasonCode.BLOCKED_BY_POLICY,
        PolicyDecisionType.REQUIRE_APPROVAL: PolicyReasonCode.APPROVAL_REQUIRED,
    }

    return PolicyDecision(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=decision_type,
        reason_code=reason_codes[decision_type],
        reason="Test policy decision.",
        policy_version="test-policy-v1",
    )


def make_successful_execution(
    proposal: ActionProposal,
) -> ExecutionResult:
    return ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={"order_id": "ord_demo_001"},
        completed_at=FIXED_TIME,
    )


def make_failed_execution(
    proposal: ActionProposal,
) -> ExecutionResult:
    return ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.FAILED,
        error_code=ExecutionErrorCode.TOOL_ERROR,
        completed_at=FIXED_TIME,
    )


def make_skipped_execution(
    proposal: ActionProposal,
) -> ExecutionResult:
    return ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.NOT_EXECUTED,
        not_executed_reason=NotExecutedReason.POLICY_BLOCKED,
        completed_at=FIXED_TIME,
    )


def make_action_verification(
    proposal: ActionProposal,
) -> VerificationResult:
    return VerificationResult(
        action_id=proposal.action_id,
        status=VerificationStatus.VERIFIED_SUCCESS,
        reason_code=VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
        reason="The observed outcome matches the expected result.",
        evidence={"observed": "expected"},
        verified_at=FIXED_TIME,
    )


def make_task_verification() -> TaskVerificationResult:
    return TaskVerificationResult(
        status=VerificationStatus.VERIFIED_SUCCESS,
        reason_code=VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
        reason="The task objective was independently verified.",
        evidence={"objective_satisfied": True},
        verified_at=FIXED_TIME,
    )


@pytest.fixture
def recorder() -> TraceRecorder:
    ids = count(1)

    return TraceRecorder(
        clock=fixed_clock,
        id_factory=lambda: f"event-{next(ids):03d}",
    )


# ---------------------------------------------------------------------------
# Initialization, event identity, and timestamps
# ---------------------------------------------------------------------------


def test_recorder_starts_empty(
    recorder: TraceRecorder,
) -> None:
    assert recorder.get_events() == ()


def test_record_proposal_creates_correlated_event(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()

    event = recorder.record_proposal(proposal)

    assert event.event_type == TraceEventType.PROPOSAL_CREATED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.sequence == 1
    assert event.event_id == "event-001"
    assert event.timestamp == FIXED_TIME
    assert event.details["tool_name"] == proposal.tool_name
    assert event.details["proposal_digest"] == compute_proposal_digest(
        proposal
    )


def test_record_proposal_does_not_store_raw_arguments(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal(
        arguments={
            "order_id": "ord_demo_001",
            "password": "must-not-be-recorded",
            "api_key": "must-not-be-recorded-either",
        }
    )

    event = recorder.record_proposal(proposal)

    assert "password" not in event.details
    assert "api_key" not in event.details
    assert "must-not-be-recorded" not in str(event.details)


def test_recorder_normalizes_timestamps_to_utc() -> None:
    offset_time = datetime.fromisoformat("2026-11-23T14:00:00+02:00")

    recorder = TraceRecorder(
        clock=lambda: offset_time,
        id_factory=lambda: "event-offset",
    )

    event = recorder.record_proposal(make_proposal())

    assert event.timestamp == FIXED_TIME
    assert event.timestamp.utcoffset() == timedelta(0)


def test_recorder_rejects_naive_clock() -> None:
    recorder = TraceRecorder(
        clock=lambda: datetime(2026, 11, 23, 12, 0),
        id_factory=lambda: "event-001",
    )

    with pytest.raises(ContractViolation, match="aware datetime"):
        recorder.record_proposal(make_proposal())

    assert recorder.get_events() == ()


def test_recorder_rejects_non_datetime_clock() -> None:
    recorder = TraceRecorder(
        clock=lambda: "not-a-datetime",  # type: ignore[arg-type]
        id_factory=lambda: "event-001",
    )

    with pytest.raises(ContractViolation, match="must return a datetime"):
        recorder.record_proposal(make_proposal())

    assert recorder.get_events() == ()


def test_recorder_rejects_blank_event_id() -> None:
    recorder = TraceRecorder(
        clock=fixed_clock,
        id_factory=lambda: " ",
    )

    with pytest.raises(ContractViolation, match="event_id"):
        recorder.record_proposal(make_proposal())

    assert recorder.get_events() == ()


# ---------------------------------------------------------------------------
# Policy decisions and proposal correlation
# ---------------------------------------------------------------------------


def test_record_policy_decision_creates_correlated_event(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    event = recorder.record_policy_decision(proposal, decision)

    assert event.event_type == TraceEventType.POLICY_DECIDED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.details["decision"] == "ALLOW"
    assert event.details["reason_code"] == "ALLOWED_BY_POLICY"
    assert event.details["policy_version"] == "test-policy-v1"
    assert event.details["proposal_digest"] == decision.proposal_digest


def test_policy_decision_rejects_mismatched_action_id(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    mismatched_proposal = make_proposal(action_id="different-action")

    with pytest.raises(ContractViolation, match="action_id"):
        recorder.record_policy_decision(mismatched_proposal, decision)

    assert recorder.get_events() == ()


def test_policy_decision_rejects_mismatched_proposal_digest(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    changed_proposal = make_proposal(
        arguments={"order_id": "different-order"}
    )

    with pytest.raises(ContractViolation, match="digest"):
        recorder.record_policy_decision(changed_proposal, decision)

    assert recorder.get_events() == ()


def test_recorder_rejects_non_proposal_input(
    recorder: TraceRecorder,
) -> None:
    with pytest.raises(ContractViolation, match="ActionProposal"):
        recorder.record_proposal("not-a-proposal")  # type: ignore[arg-type]

    assert recorder.get_events() == ()


# ---------------------------------------------------------------------------
# Approval lifecycle
# ---------------------------------------------------------------------------


def test_record_approval_requested_requires_approval_decision(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    with pytest.raises(ContractViolation, match="REQUIRE_APPROVAL"):
        recorder.record_approval_requested(
            proposal,
            decision,
            "approval-001",
        )

    assert recorder.get_events() == ()


def test_record_approval_requested_records_service_request(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )
    service = ApprovalService(clock=fixed_clock)

    approval_id = service.request_approval(proposal, decision)

    event = recorder.record_approval_requested(
        proposal,
        decision,
        approval_id,
    )

    assert service.get_status(approval_id) == ApprovalStatus.PENDING
    assert event.event_type == TraceEventType.APPROVAL_REQUESTED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.details["approval_id"] == approval_id
    assert event.details["proposal_digest"] == decision.proposal_digest


def test_record_approval_granted_uses_service_evidence(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )
    service = ApprovalService(clock=fixed_clock)

    approval_id = service.request_approval(proposal, decision)
    evidence = service.approve(approval_id, "test-approver")

    event = recorder.record_approval_granted(proposal, evidence)

    assert event.event_type == TraceEventType.APPROVAL_GRANTED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.details["approval_id"] == evidence.approval_id
    assert event.details["proposal_digest"] == evidence.proposal_digest
    assert event.details["policy_version"] == evidence.policy_version
    assert event.details["approved_at"] == evidence.approved_at.isoformat()
    assert event.details["expires_at"] == evidence.expires_at.isoformat()


def test_record_approval_denied_after_service_denial(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )
    service = ApprovalService(clock=fixed_clock)

    approval_id = service.request_approval(proposal, decision)
    service.deny(approval_id, "test-approver")

    assert service.get_status(approval_id) == ApprovalStatus.DENIED

    event = recorder.record_approval_denied(
        proposal,
        decision,
        approval_id,
    )

    assert event.event_type == TraceEventType.APPROVAL_DENIED
    assert event.details["approval_id"] == approval_id


def test_record_approval_expired_after_service_expiry(
    recorder: TraceRecorder,
) -> None:
    current_time = [FIXED_TIME]

    def advancing_clock() -> datetime:
        return current_time[0]

    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )
    service = ApprovalService(
        clock=advancing_clock,
        ttl=timedelta(minutes=1),
    )

    approval_id = service.request_approval(proposal, decision)

    current_time[0] = FIXED_TIME + timedelta(minutes=2)

    assert service.get_status(approval_id) == ApprovalStatus.EXPIRED

    event = recorder.record_approval_expired(
        proposal,
        decision,
        approval_id,
    )

    assert event.event_type == TraceEventType.APPROVAL_EXPIRED
    assert event.details["approval_id"] == approval_id


# ---------------------------------------------------------------------------
# Execution lifecycle
# ---------------------------------------------------------------------------


def test_execution_started_records_explicit_start(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    event = recorder.record_execution_started(proposal, decision)

    assert event.event_type == TraceEventType.EXECUTION_STARTED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.details["tool_name"] == proposal.tool_name
    assert event.details["approval_id"] is None


def test_blocked_decision_cannot_record_execution_started(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal, PolicyDecisionType.BLOCK)

    with pytest.raises(ContractViolation, match="BLOCK"):
        recorder.record_execution_started(proposal, decision)

    assert recorder.get_events() == ()


def test_approval_required_execution_start_requires_evidence(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )

    with pytest.raises(ContractViolation, match="ApprovalEvidence"):
        recorder.record_execution_started(proposal, decision)

    assert recorder.get_events() == ()


def test_record_approved_execution_start(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        PolicyDecisionType.REQUIRE_APPROVAL,
    )
    service = ApprovalService(clock=fixed_clock)

    approval_id = service.request_approval(proposal, decision)
    evidence = service.approve(approval_id, "test-approver")

    event = recorder.record_execution_started(
        proposal,
        decision,
        approval_evidence=evidence,
    )

    assert event.event_type == TraceEventType.EXECUTION_STARTED
    assert event.details["approval_id"] == approval_id


@pytest.mark.parametrize(
    ("execution_factory", "expected_event"),
    [
        (make_successful_execution, TraceEventType.EXECUTION_SUCCEEDED),
        (make_failed_execution, TraceEventType.EXECUTION_FAILED),
    ],
)
def test_execution_result_maps_actual_execution_status(
    recorder: TraceRecorder,
    execution_factory: Any,
    expected_event: TraceEventType,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)
    result = execution_factory(proposal)

    event = recorder.record_execution_result(
        proposal,
        decision,
        result,
    )

    assert event.event_type == expected_event
    assert event.details["execution_status"] == result.status.value
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id


def test_blocked_execution_result_maps_to_execution_skipped(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal, PolicyDecisionType.BLOCK)
    result = make_skipped_execution(proposal)

    event = recorder.record_execution_result(
        proposal,
        decision,
        result,
    )

    assert event.event_type == TraceEventType.EXECUTION_SKIPPED
    assert event.details["execution_status"] == "NOT_EXECUTED"
    assert event.details["not_executed_reason"] == "POLICY_BLOCKED"


def test_execution_result_rejects_invalid_lifecycle_combination(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    blocked_decision = make_decision(
        proposal,
        PolicyDecisionType.BLOCK,
    )
    successful_result = make_successful_execution(proposal)

    with pytest.raises(ContractViolation):
        recorder.record_execution_result(
            proposal,
            blocked_decision,
            successful_result,
        )

    assert recorder.get_events() == ()


# ---------------------------------------------------------------------------
# Action-level and task-level verification
# ---------------------------------------------------------------------------


def test_record_action_verification_uses_action_scope(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)
    execution = make_successful_execution(proposal)
    verification = make_action_verification(proposal)

    event = recorder.record_action_verification(
        proposal,
        decision,
        execution,
        verification,
    )

    assert event.event_type == TraceEventType.VERIFICATION_COMPLETED
    assert event.task_id == proposal.task_id
    assert event.action_id == proposal.action_id
    assert event.details["verification_scope"] == "ACTION"
    assert event.details["verification_status"] == "VERIFIED_SUCCESS"


def test_record_task_verification_has_no_action_linkage(
    recorder: TraceRecorder,
) -> None:
    verification = make_task_verification()

    event = recorder.record_task_verification(
        "task-001",
        verification,
    )

    assert event.event_type == TraceEventType.VERIFICATION_COMPLETED
    assert event.task_id == "task-001"
    assert event.action_id is None
    assert event.details["verification_scope"] == "TASK"
    assert event.details["verification_status"] == "VERIFIED_SUCCESS"


def test_task_verification_does_not_require_action_event(
    recorder: TraceRecorder,
) -> None:
    event = recorder.record_task_verification(
        "task-without-action",
        make_task_verification(),
    )

    assert event.task_id == "task-without-action"
    assert event.action_id is None
    assert event.sequence == 1


def test_task_verification_rejects_blank_task_id(
    recorder: TraceRecorder,
) -> None:
    with pytest.raises(ContractViolation, match="task_id"):
        recorder.record_task_verification(
            " ",
            make_task_verification(),
        )

    assert recorder.get_events() == ()


# ---------------------------------------------------------------------------
# Redaction and immutable event snapshots
# ---------------------------------------------------------------------------


def test_recording_sanitizes_sensitive_detail_keys(
    recorder: TraceRecorder,
) -> None:
    # Exercise the recorder's shared append boundary directly so that
    # arbitrary nested detail structures are covered by this test.
    from agenttrax.contracts.tracing import TraceEventType

    details = {
        "nested": {
            "api_key": "secret-value",
            "ordinary": "visible-value",
        },
        "items": [
            {"password": "another-secret"},
        ],
    }

    original = {
        "nested": {
            "api_key": "secret-value",
            "ordinary": "visible-value",
        },
        "items": [
            {"password": "another-secret"},
        ],
    }

    event = recorder._record(
        task_id="task-001",
        action_id="action-001",
        event_type=TraceEventType.PROPOSAL_CREATED,
        details=details,
    )

    assert event.details["nested"]["api_key"] == "[REDACTED]"
    assert event.details["nested"]["ordinary"] == "visible-value"
    assert event.details["items"][0]["password"] == "[REDACTED]"
    assert details == original


def test_get_events_returns_immutable_tuple_snapshot(
    recorder: TraceRecorder,
) -> None:
    recorder.record_proposal(make_proposal())

    snapshot = recorder.get_events()

    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1

    with pytest.raises(AttributeError):
        snapshot.append(snapshot[0])  # type: ignore[attr-defined]


def test_event_details_are_immutable(
    recorder: TraceRecorder,
) -> None:
    event = recorder.record_proposal(make_proposal())

    with pytest.raises(TypeError):
        event.details["new_key"] = "not-allowed"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Ordering, filtering, reset, and concurrency
# ---------------------------------------------------------------------------


def test_event_sequence_is_monotonically_increasing(
    recorder: TraceRecorder,
) -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)

    recorder.record_proposal(proposal)
    recorder.record_policy_decision(proposal, decision)
    recorder.record_execution_started(proposal, decision)

    events = recorder.get_events()

    assert [event.sequence for event in events] == [1, 2, 3]


def test_sequence_follows_record_order_not_event_timestamp() -> None:
    times = iter(
        [
            FIXED_TIME + timedelta(minutes=5),
            FIXED_TIME,
        ]
    )

    recorder = TraceRecorder(
        clock=lambda: next(times),
        id_factory=iter(["event-001", "event-002"]).__next__,
    )

    first = recorder.record_proposal(make_proposal())
    second = recorder.record_proposal(
        make_proposal(action_id="action-002")
    )

    assert first.timestamp > second.timestamp
    assert first.sequence == 1
    assert second.sequence == 2


def test_get_task_events_filters_without_changing_global_sequence(
    recorder: TraceRecorder,
) -> None:
    recorder.record_proposal(make_proposal(task_id="task-001"))
    recorder.record_proposal(
        make_proposal(
            action_id="action-002",
            task_id="task-002",
        )
    )
    recorder.record_proposal(
        make_proposal(
            action_id="action-003",
            task_id="task-001",
        )
    )

    task_events = recorder.get_task_events("task-001")

    assert len(task_events) == 2
    assert all(event.task_id == "task-001" for event in task_events)
    assert [event.sequence for event in task_events] == [1, 3]
    assert len(recorder.get_events()) == 3


def test_reset_clears_events_and_restarts_sequence(
    recorder: TraceRecorder,
) -> None:
    first = recorder.record_proposal(make_proposal())

    recorder.reset()

    assert recorder.get_events() == ()

    second = recorder.record_proposal(make_proposal())

    assert second.sequence == 1
    assert second.event_id != first.event_id


def test_failed_append_does_not_consume_sequence() -> None:
    ids = iter(["", "event-valid"])

    recorder = TraceRecorder(
        clock=fixed_clock,
        id_factory=lambda: next(ids),
    )

    with pytest.raises(ContractViolation, match="event_id"):
        recorder.record_proposal(make_proposal())

    event = recorder.record_proposal(make_proposal())

    assert event.sequence == 1
    assert len(recorder.get_events()) == 1


def test_concurrent_recording_preserves_unique_ordered_sequences() -> None:
    recorder = TraceRecorder(clock=fixed_clock)

    def record_one(index: int) -> None:
        recorder.record_proposal(
            make_proposal(
                action_id=f"action-{index:03d}",
                task_id="concurrent-task",
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(record_one, range(40)))

    events = recorder.get_events()

    assert len(events) == 40
    assert [event.sequence for event in events] == list(range(1, 41))
    assert len({event.event_id for event in events}) == 40
