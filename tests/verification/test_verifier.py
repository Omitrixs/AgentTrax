
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from agenttrax.contracts.models import (
    ActionProposal,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    NotExecutedReason,
    VerificationReasonCode,
    VerificationStatus,
)
from agenttrax.scenarios.models import ScenarioSnapshot
from agenttrax.scenarios.order_support import (
    add_case_note,
    close_case,
    issue_refund,
)
from agenttrax.scenarios.state import (
    DEMO_CASE_ID,
    DEMO_ORDER_ID,
    OrderSupportScenarioState,
)
from agenttrax.verification.verifier import IndependentVerifier

FIXED_TIME = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_TIME


@pytest.fixture
def state() -> OrderSupportScenarioState:
    return OrderSupportScenarioState()


@pytest.fixture
def verifier(state: OrderSupportScenarioState) -> IndependentVerifier:
    return IndependentVerifier(state=state, clock=fixed_clock)


def make_proposal(
    tool_name: str,
    arguments: dict[str, Any],
    action_id: str = "action-001",
) -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        task_id="task-001",
        tool_name=tool_name,
        arguments=arguments,
        requested_by="test-agent",
        created_at=FIXED_TIME,
    )


def successful_execution(
    proposal: ActionProposal,
    result: Any,
) -> ExecutionResult:
    return ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result=result.model_dump(mode="json"),
        completed_at=FIXED_TIME,
    )


def execute_and_verify(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
    tool_name: str,
    arguments: dict[str, Any],
    operation: Callable[[], Any] | None = None,
):
    proposal = make_proposal(tool_name, arguments)
    before = state.snapshot()

    if operation is None:
        result = state.order
    else:
        result = operation()

    execution = successful_execution(proposal, result)

    return verifier.verify_action(proposal, execution, before)


def prepare_completed_task(state: OrderSupportScenarioState) -> None:
    issue_refund(
        state,
        DEMO_ORDER_ID,
        state.objective.refund_minor_units,
    )
    add_case_note(
        state,
        DEMO_CASE_ID,
        "Refund completed and customer notified.",
    )
    close_case(state, DEMO_CASE_ID)


def test_get_order_action_is_verified_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    result = execute_and_verify(
        verifier,
        state,
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED


def test_add_case_note_action_is_verified_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    result = execute_and_verify(
        verifier,
        state,
        "add_case_note",
        {"case_id": DEMO_CASE_ID, "note": "Customer contacted."},
        lambda: add_case_note(
            state,
            DEMO_CASE_ID,
            "Customer contacted.",
        ),
    )

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED


def test_issue_refund_action_is_verified_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    amount = state.objective.refund_minor_units

    result = execute_and_verify(
        verifier,
        state,
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": amount},
        lambda: issue_refund(state, DEMO_ORDER_ID, amount),
    )

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED


def test_close_case_action_is_verified_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    issue_refund(
        state,
        DEMO_ORDER_ID,
        state.objective.refund_minor_units,
    )
    add_case_note(state, DEMO_CASE_ID, "Refund processed.")

    result = execute_and_verify(
        verifier,
        state,
        "close_case",
        {"case_id": DEMO_CASE_ID},
        lambda: close_case(state, DEMO_CASE_ID),
    )

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED


def test_not_executed_without_state_change_is_no_change_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 2500},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.NOT_EXECUTED,
        not_executed_reason=NotExecutedReason.POLICY_BLOCKED,
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.NO_CHANGE_CONFIRMED


def test_not_executed_with_state_change_is_verified_failure(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 2500},
    )
    before = state.snapshot()

    issue_refund(state, DEMO_ORDER_ID, 2500)

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.NOT_EXECUTED,
        not_executed_reason=NotExecutedReason.POLICY_BLOCKED,
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.VERIFIED_FAILURE
    assert result.reason_code == VerificationReasonCode.UNEXPECTED_STATE_CHANGE


def test_failed_execution_without_state_change_is_verified_failure(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.FAILED,
        error_code=ExecutionErrorCode.TOOL_ERROR,
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.VERIFIED_FAILURE
    assert result.reason_code == VerificationReasonCode.OUTCOME_MISMATCH


def test_failed_execution_with_state_change_is_unexpected_failure(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 2500},
    )
    before = state.snapshot()

    issue_refund(state, DEMO_ORDER_ID, 2500)

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.FAILED,
        error_code=ExecutionErrorCode.INTERNAL_ERROR,
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.VERIFIED_FAILURE
    assert result.reason_code == VerificationReasonCode.UNEXPECTED_STATE_CHANGE


def test_success_claim_without_required_state_change_is_failure(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 2500},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={},
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.VERIFIED_FAILURE
    assert result.reason_code == VerificationReasonCode.OUTCOME_MISMATCH


def test_conflicting_reported_result_is_inconclusive(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={"order_id": "fabricated-order"},
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.reason_code == VerificationReasonCode.EVIDENCE_CONFLICTING


def test_missing_reported_result_is_inconclusive(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result=None,
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.reason_code == VerificationReasonCode.EVIDENCE_MISSING


def test_unknown_tool_is_inconclusive(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal("unknown_tool", {})
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result={},
        completed_at=FIXED_TIME,
    )

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.reason_code == VerificationReasonCode.EVIDENCE_MISSING


def test_verifier_exception_fails_closed(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.SUCCEEDED,
        result=state.order.model_dump(mode="json"),
        completed_at=FIXED_TIME,
    )

    def raise_verifier_error(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Simulated verifier failure.")

    monkeypatch.setattr(verifier, "_check_transition", raise_verifier_error)

    result = verifier.verify_action(proposal, execution, before)

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.reason_code == VerificationReasonCode.VERIFIER_ERROR


def test_action_id_mismatch_is_rejected(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id="different-action",
        status=ExecutionStatus.SUCCEEDED,
        result=state.order.model_dump(mode="json"),
        completed_at=FIXED_TIME,
    )

    with pytest.raises(ValueError):
        verifier.verify_action(proposal, execution, before)


def test_task_objective_is_verified_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    prepare_completed_task(state)

    result = verifier.verify_task()

    assert result.status == VerificationStatus.VERIFIED_SUCCESS
    assert result.reason_code == VerificationReasonCode.OUTCOME_MATCHES_EXPECTED


def test_unmet_task_objective_is_verified_failure(
    verifier: IndependentVerifier,
) -> None:
    result = verifier.verify_task()

    assert result.status == VerificationStatus.VERIFIED_FAILURE
    assert result.reason_code == VerificationReasonCode.OUTCOME_MISMATCH


def test_task_verifier_exception_is_inconclusive(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_snapshot_error() -> ScenarioSnapshot:
        raise RuntimeError("Simulated snapshot failure.")

    monkeypatch.setattr(state, "snapshot", raise_snapshot_error)

    result = verifier.verify_task()

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.reason_code == VerificationReasonCode.VERIFIER_ERROR


def test_no_change_confirmed_does_not_establish_task_success(
    verifier: IndependentVerifier,
    state: OrderSupportScenarioState,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 2500},
    )
    before = state.snapshot()

    execution = ExecutionResult(
        action_id=proposal.action_id,
        status=ExecutionStatus.NOT_EXECUTED,
        not_executed_reason=NotExecutedReason.POLICY_BLOCKED,
        completed_at=FIXED_TIME,
    )

    action_result = verifier.verify_action(proposal, execution, before)
    task_result = verifier.verify_task()

    assert action_result.status == VerificationStatus.VERIFIED_SUCCESS
    assert action_result.reason_code == VerificationReasonCode.NO_CHANGE_CONFIRMED

    assert task_result.status == VerificationStatus.VERIFIED_FAILURE
    assert task_result.reason_code == VerificationReasonCode.OUTCOME_MISMATCH
