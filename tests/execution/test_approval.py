"""Tests for the AT-06 in-memory approval service."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from agenttrax.contracts.models import (
    ActionProposal,
    ContractViolation,
    PolicyDecision,
    PolicyDecisionType,
    PolicyReasonCode,
    compute_proposal_digest,
)
from agenttrax.execution.approval import ApprovalService, ApprovalStatus


class MutableClock:
    """A deterministic clock that tests can advance."""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 11, 5, 12, 0, tzinfo=UTC))


@pytest.fixture
def proposal() -> ActionProposal:
    return ActionProposal(
        action_id="action-001",
        task_id="task-001",
        tool_name="issue_refund",
        arguments={"order_id": "ord_demo_001", "amount_minor_units": 2500},
        requested_by="test-agent",
        created_at=datetime(2026, 11, 5, 11, 0, tzinfo=UTC),
    )


@pytest.fixture
def approval_decision(proposal: ActionProposal) -> PolicyDecision:
    return PolicyDecision(
        action_id=proposal.action_id,
        proposal_digest=compute_proposal_digest(proposal),
        decision=PolicyDecisionType.REQUIRE_APPROVAL,
        reason_code=PolicyReasonCode.APPROVAL_REQUIRED,
        reason="Refund requires explicit approval.",
        policy_version="order_support_policy_v1",
    )


@pytest.fixture
def service(clock: MutableClock) -> ApprovalService:
    return ApprovalService(clock=clock)


def test_request_stores_pending_approval(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)

    assert approval_id.startswith("approval_")
    assert service.get_status(approval_id) == ApprovalStatus.PENDING


def test_request_rejects_allow_decision(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    allow_decision = approval_decision.model_copy(
        update={"decision": PolicyDecisionType.ALLOW}
    )

    with pytest.raises(ContractViolation, match="Only REQUIRE_APPROVAL"):
        service.request_approval(proposal, allow_decision)


def test_request_rejects_block_decision(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    block_decision = approval_decision.model_copy(
        update={
            "decision": PolicyDecisionType.BLOCK,
            "reason_code": PolicyReasonCode.BLOCKED_BY_POLICY,
        }
    )

    with pytest.raises(ContractViolation, match="Only REQUIRE_APPROVAL"):
        service.request_approval(proposal, block_decision)


def test_request_rejects_action_id_mismatch(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    mismatched = approval_decision.model_copy(
        update={"action_id": "different-action"}
    )

    with pytest.raises(ContractViolation, match="action_id"):
        service.request_approval(proposal, mismatched)


def test_request_rejects_digest_mismatch(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    mismatched = approval_decision.model_copy(
        update={"proposal_digest": "b" * 64}
    )

    with pytest.raises(ContractViolation, match="digest"):
        service.request_approval(proposal, mismatched)


def test_approve_returns_service_generated_evidence(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
    clock: MutableClock,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)

    evidence = service.approve(approval_id, "reviewer-001")

    assert evidence.approval_id == approval_id
    assert evidence.action_id == proposal.action_id
    assert evidence.proposal_digest == compute_proposal_digest(proposal)
    assert evidence.policy_version == approval_decision.policy_version
    assert evidence.approved_at == clock.current
    assert evidence.expires_at == clock.current + timedelta(minutes=15)
    assert service.get_status(approval_id) == ApprovalStatus.APPROVED


def test_approval_normalizes_clock_to_utc(
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    local_clock = MutableClock(
        datetime.fromisoformat("2026-11-05T13:00:00+01:00")
    )
    service = ApprovalService(clock=local_clock)

    approval_id = service.request_approval(proposal, approval_decision)
    evidence = service.approve(approval_id, "reviewer-001")

    assert evidence.approved_at == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    assert evidence.expires_at == datetime(2026, 11, 5, 12, 15, tzinfo=UTC)


def test_deny_transitions_pending_request_to_denied(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)

    service.deny(approval_id, "reviewer-002")

    assert service.get_status(approval_id) == ApprovalStatus.DENIED


def test_denied_request_cannot_be_approved(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    service.deny(approval_id, "reviewer-002")

    with pytest.raises(ContractViolation, match="DENIED"):
        service.approve(approval_id, "reviewer-003")


def test_approved_request_cannot_be_denied_again(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    service.approve(approval_id, "reviewer-001")

    with pytest.raises(ContractViolation, match="APPROVED"):
        service.deny(approval_id, "reviewer-002")


def test_request_expires_at_exact_boundary(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
    clock: MutableClock,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    clock.current += timedelta(minutes=15)

    assert service.get_status(approval_id) == ApprovalStatus.EXPIRED

    with pytest.raises(ContractViolation, match="EXPIRED"):
        service.approve(approval_id, "reviewer-001")


def test_approved_request_expires_before_consumption(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
    clock: MutableClock,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    service.approve(approval_id, "reviewer-001")
    clock.current += timedelta(minutes=15)

    assert service.get_status(approval_id) == ApprovalStatus.EXPIRED

    with pytest.raises(ContractViolation, match="EXPIRED"):
        service._consume_approved(approval_id)


def test_consume_returns_original_action_and_evidence(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    evidence = service.approve(approval_id, "reviewer-001")

    stored_proposal, stored_decision, stored_evidence = (
        service._consume_approved(approval_id)
    )

    assert stored_proposal is proposal
    assert stored_decision is approval_decision
    assert stored_evidence == evidence
    assert service.get_status(approval_id) == ApprovalStatus.CONSUMED


def test_consumed_approval_cannot_be_replayed(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    service.approve(approval_id, "reviewer-001")
    service._consume_approved(approval_id)

    with pytest.raises(ContractViolation, match="CONSUMED"):
        service._consume_approved(approval_id)


def test_pending_approval_cannot_be_consumed(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)

    with pytest.raises(ContractViolation, match="PENDING"):
        service._consume_approved(approval_id)


def test_unknown_approval_id_is_rejected(service: ApprovalService) -> None:
    with pytest.raises(ContractViolation, match="Unknown approval"):
        service.get_status("approval-does-not-exist")


@pytest.mark.parametrize(
    ("approval_id", "approver_id"),
    [
        ("", "reviewer-001"),
        ("   ", "reviewer-001"),
        ("approval-001", ""),
        ("approval-001", "   "),
    ],
)
def test_approval_actions_reject_blank_identifiers(
    service: ApprovalService,
    approval_id: str,
    approver_id: str,
) -> None:
    with pytest.raises(ContractViolation):
        service.approve(approval_id, approver_id)


def test_clock_must_return_aware_datetime(
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    service = ApprovalService(
        clock=lambda: datetime(2026, 11, 5, 12, 0)
    )

    with pytest.raises(ContractViolation, match="aware datetime"):
        service.request_approval(proposal, approval_decision)


def test_clock_must_return_datetime(
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    service = ApprovalService(clock=lambda: "2026-11-05T12:00:00Z")  # type: ignore[arg-type]

    with pytest.raises(ContractViolation, match="must return a datetime"):
        service.request_approval(proposal, approval_decision)


@pytest.mark.parametrize(
    "ttl",
    [
        timedelta(0),
        timedelta(seconds=-1),
        "15 minutes",
    ],
)
def test_service_rejects_invalid_ttl(ttl: object) -> None:
    with pytest.raises(ValueError, match="positive timedelta"):
        ApprovalService(ttl=ttl)  # type: ignore[arg-type]


def test_service_rejects_non_callable_clock() -> None:
    with pytest.raises(ValueError, match="callable"):
        ApprovalService(clock=None)  # type: ignore[arg-type]


def test_concurrent_consumption_allows_exactly_one_winner(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    approval_id = service.request_approval(proposal, approval_decision)
    service.approve(approval_id, "reviewer-001")

    def consume() -> bool:
        try:
            service._consume_approved(approval_id)
            return True
        except ContractViolation:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(2)))

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert service.get_status(approval_id) == ApprovalStatus.CONSUMED


def test_each_request_gets_a_distinct_identifier(
    service: ApprovalService,
    proposal: ActionProposal,
    approval_decision: PolicyDecision,
) -> None:
    first_id = service.request_approval(proposal, approval_decision)
    second_id = service.request_approval(proposal, approval_decision)

    assert first_id != second_id
