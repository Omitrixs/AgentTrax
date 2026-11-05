"""Tests for the gated tool executor."""

from datetime import UTC, datetime
from typing import Any

import pytest

from agenttrax.contracts.models import (
    ActionProposal,
    ContractViolation,
    ExecutionErrorCode,
    ExecutionStatus,
    NotExecutedReason,
    PolicyDecisionType,
    PolicyReasonCode,
    check_lifecycle_consistency,
)
from agenttrax.execution.executor import GatedToolExecutor
from agenttrax.scenarios.order_support import (
    OperationErrorCode,
    ScenarioOperationError,
)
from agenttrax.scenarios.registry import (
    RegistryErrorCode,
    ScenarioRegistryError,
)
from agenttrax.scenarios.state import DEMO_CASE_ID, DEMO_ORDER_ID


def fixed_clock() -> datetime:
    """Return a deterministic UTC timestamp."""
    return datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def executor() -> GatedToolExecutor:
    return GatedToolExecutor(clock=fixed_clock)


def make_proposal(
    tool_name: str,
    arguments: dict[str, Any],
) -> ActionProposal:
    return ActionProposal(
        action_id="act-001",
        task_id="task-001",
        tool_name=tool_name,
        arguments=arguments,
        requested_by="test-agent",
        created_at=datetime(2026, 11, 5, 11, 0, 0, tzinfo=UTC),
    )


def evaluate_decision(
    executor: GatedToolExecutor,
    proposal: ActionProposal,
):
    """Obtain the actual policy decision for the current state."""
    return executor.policy_engine.evaluate(
        proposal,
        executor.state.snapshot(),
    )


def prevent_registry_invocation(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail the test if the registry is invoked."""

    def unexpected_invocation(*args: object, **kwargs: object) -> None:
        pytest.fail("Registry must not be invoked for this decision.")

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        unexpected_invocation,
    )


# ---------------------------------------------------------------------------
# Successful execution
# ---------------------------------------------------------------------------


def test_get_order_execution_succeeds(
    executor: GatedToolExecutor,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.action_id == proposal.action_id
    assert result.result is not None
    assert result.result["order_id"] == DEMO_ORDER_ID
    assert result.completed_at == fixed_clock()
    check_lifecycle_consistency(proposal, decision, result)


def test_add_case_note_execution_succeeds(
    executor: GatedToolExecutor,
) -> None:
    proposal = make_proposal(
        "add_case_note",
        {"case_id": DEMO_CASE_ID, "note": "Valid note."},
    )
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.result is not None
    assert result.result["case_id"] == DEMO_CASE_ID
    assert result.completed_at == fixed_clock()
    check_lifecycle_consistency(proposal, decision, result)


# ---------------------------------------------------------------------------
# Execution failure handling
# ---------------------------------------------------------------------------


def test_registry_failure_returns_tool_error(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    def failing_invoke(*args: object, **kwargs: object) -> None:
        raise ScenarioRegistryError(
            RegistryErrorCode.INVALID_ARGUMENTS,
            "Simulated registry failure.",
        )

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        failing_invoke,
    )

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.TOOL_ERROR
    assert result.result is None
    assert result.not_executed_reason is None
    assert result.completed_at == fixed_clock()


def test_scenario_operation_failure_returns_tool_error(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    def raise_operation_error(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise ScenarioOperationError(
            OperationErrorCode.UNKNOWN_ORDER,
            "The scenario operation was rejected.",
        )

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        raise_operation_error,
    )

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.TOOL_ERROR
    assert result.result is None
    assert result.not_executed_reason is None
    assert result.completed_at == fixed_clock()


def test_unexpected_registry_exception_returns_internal_error(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    def unexpected_failure(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Simulated unexpected failure.")

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        unexpected_failure,
    )

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.INTERNAL_ERROR
    assert result.result is None
    assert result.not_executed_reason is None
    assert result.completed_at == fixed_clock()


def test_unsupported_registry_result_returns_invalid_result(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    def unsupported_result(*args: object, **kwargs: object) -> object:
        return object()

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        unsupported_result,
    )

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.INVALID_RESULT
    assert result.result is None
    assert result.not_executed_reason is None
    assert result.completed_at == fixed_clock()


# ---------------------------------------------------------------------------
# Policy denials
# ---------------------------------------------------------------------------


def test_block_decision_returns_not_executed(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": "invalid-order", "amount_minor_units": 100},
    )
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.BLOCK

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason == NotExecutedReason.POLICY_BLOCKED
    assert result.result is None
    assert executor.state.order.refunded_minor_units == 0
    check_lifecycle_consistency(proposal, decision, result)


def test_require_approval_returns_not_executed(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": DEMO_ORDER_ID, "amount_minor_units": 100},
    )
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.REQUIRE_APPROVAL

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason == NotExecutedReason.APPROVAL_PENDING
    assert result.result is None
    assert executor.state.order.refunded_minor_units == 0
    check_lifecycle_consistency(proposal, decision, result)


# ---------------------------------------------------------------------------
# Integrity protection
# ---------------------------------------------------------------------------


def test_mismatched_action_id_fails(
    executor: GatedToolExecutor,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    decision = decision.model_copy(update={"action_id": "wrong-id"})

    with pytest.raises(ContractViolation, match="H1"):
        executor.execute(proposal, decision)


def test_mismatched_proposal_digest_fails(
    executor: GatedToolExecutor,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    decision = decision.model_copy(update={"proposal_digest": "0" * 64})

    with pytest.raises(ContractViolation, match="H2"):
        executor.execute(proposal, decision)


def test_fabricated_decision_fails(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal(
        "issue_refund",
        {"order_id": "invalid-order", "amount_minor_units": 100},
    )
    actual_decision = evaluate_decision(executor, proposal)

    assert actual_decision.decision == PolicyDecisionType.BLOCK

    # Keep the proposal linkage, but fabricate an ALLOW decision.
    fabricated_decision = actual_decision.model_copy(
        update={
            "decision": PolicyDecisionType.ALLOW,
            "reason_code": PolicyReasonCode.ALLOWED_BY_POLICY,
        }
    )

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, fabricated_decision)

    assert result.status == ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason == NotExecutedReason.INTEGRITY_CHECK_FAILED
    assert result.result is None
    assert executor.state.order.refunded_minor_units == 0
    check_lifecycle_consistency(proposal, fabricated_decision, result)


# ---------------------------------------------------------------------------
# Additional acceptance and security tests
# ---------------------------------------------------------------------------


def test_close_case_execution_succeeds_after_valid_preconditions(
    executor: GatedToolExecutor,
) -> None:
    from agenttrax.scenarios.models import (
        CaseNote,
        CaseStatus,
        PaymentStatus,
        SimulatedOrder,
        SupportCase,
    )

    # Prepare a valid simulated state without executing a refund.
    executor.state.replace_order(
        SimulatedOrder(
            order_id=DEMO_ORDER_ID,
            status=executor.state.order.status,
            payment_status=PaymentStatus.PARTIALLY_REFUNDED,
            currency="USD",
            total_minor_units=12_999,
            refunded_minor_units=2_500,
        )
    )
    executor.state.replace_support_case(
        SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.OPEN,
            notes=(CaseNote(sequence=1, note="Refund recorded."),),
        )
    )

    proposal = make_proposal("close_case", {"case_id": DEMO_CASE_ID})
    decision = evaluate_decision(executor, proposal)

    assert decision.decision == PolicyDecisionType.ALLOW

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.action_id == proposal.action_id
    assert result.result is not None
    assert result.result["case_id"] == DEMO_CASE_ID
    assert result.result["status"] == CaseStatus.CLOSED.value
    assert executor.state.snapshot().support_case.status == CaseStatus.CLOSED
    check_lifecycle_consistency(proposal, decision, result)


def test_executor_and_registry_share_the_same_state(
    executor: GatedToolExecutor,
) -> None:
    assert executor._registry._state is executor.state


def test_successful_mutation_is_visible_to_subsequent_policy_evaluation(
    executor: GatedToolExecutor,
) -> None:
    proposal = make_proposal(
        "add_case_note",
        {"case_id": DEMO_CASE_ID, "note": "State mutation test."},
    )
    decision = evaluate_decision(executor, proposal)

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert len(executor.state.snapshot().support_case.notes) == 1

    next_proposal = make_proposal(
        "add_case_note",
        {"case_id": DEMO_CASE_ID, "note": "Second note."},
    )
    next_decision = evaluate_decision(executor, next_proposal)

    assert next_decision.decision == PolicyDecisionType.ALLOW


def test_stale_allow_decision_fails_after_state_changes(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agenttrax.scenarios.models import CaseStatus, SupportCase

    proposal = make_proposal(
        "add_case_note",
        {"case_id": DEMO_CASE_ID, "note": "Must not be added."},
    )
    stale_decision = evaluate_decision(executor, proposal)

    assert stale_decision.decision == PolicyDecisionType.ALLOW

    executor.state.replace_support_case(
        SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.CLOSED,
            notes=(),
        )
    )

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, stale_decision)

    assert result.status == ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason == NotExecutedReason.INTEGRITY_CHECK_FAILED
    assert executor.state.support_case.status == CaseStatus.CLOSED
    check_lifecycle_consistency(proposal, stale_decision, result)


@pytest.mark.parametrize(
    "decision_update",
    [
        {"policy_version": "different_policy_version"},
        {"reason": "Fabricated reason text."},
        {"reason_code": PolicyReasonCode.MALFORMED_DECISION},
    ],
)
def test_inconsistent_decision_fields_fail_closed(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
    decision_update: dict[str, object],
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)
    fabricated = decision.model_copy(update=decision_update)

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, fabricated)

    assert result.status == ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason == NotExecutedReason.INTEGRITY_CHECK_FAILED


def test_action_id_mismatch_never_invokes_registry(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)
    mismatched = decision.model_copy(update={"action_id": "wrong-action"})

    prevent_registry_invocation(executor, monkeypatch)

    with pytest.raises(ContractViolation, match="H1"):
        executor.execute(proposal, mismatched)


def test_digest_mismatch_never_invokes_registry(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)
    mismatched = decision.model_copy(update={"proposal_digest": "0" * 64})

    prevent_registry_invocation(executor, monkeypatch)

    with pytest.raises(ContractViolation, match="H2"):
        executor.execute(proposal, mismatched)


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("unknown_tool", {}),
        ("get_order", {"order_id": DEMO_ORDER_ID, "extra": "value"}),
        ("get_order", {"order_id": 123}),
        ("issue_refund", {"order_id": DEMO_ORDER_ID, "amount_minor_units": True}),
        ("close_case", {"case_id": DEMO_CASE_ID}),
    ],
)
def test_invalid_or_blocked_proposals_do_not_invoke_registry(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    proposal = make_proposal(tool_name, arguments)
    decision = evaluate_decision(executor, proposal)

    assert decision.decision is PolicyDecisionType.BLOCK

    original_order = executor.state.order
    original_case = executor.state.support_case

    prevent_registry_invocation(executor, monkeypatch)

    result = executor.execute(proposal, decision)

    assert result.status is ExecutionStatus.NOT_EXECUTED
    assert result.not_executed_reason is NotExecutedReason.POLICY_BLOCKED
    assert executor.state.order == original_order
    assert executor.state.support_case == original_case


@pytest.mark.parametrize(
    ("proposal", "decision_type"),
    [
        (object(), "valid"),
        (
            make_proposal("get_order", {"order_id": DEMO_ORDER_ID}),
            "invalid",
        ),
    ],
)
def test_invalid_contract_input_is_rejected_without_registry_invocation(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
    proposal: object,
    decision_type: str,
) -> None:
    valid_proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    valid_decision = evaluate_decision(executor, valid_proposal)

    prevent_registry_invocation(executor, monkeypatch)

    with pytest.raises(TypeError):
        if decision_type == "valid":
            executor.execute(proposal, valid_decision)
        else:
            executor.execute(valid_proposal, object())


def test_execution_failure_passes_lifecycle_consistency(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    def unexpected_failure(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Controlled internal failure.")

    monkeypatch.setattr(executor._registry, "invoke", unexpected_failure)

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.INTERNAL_ERROR
    check_lifecycle_consistency(proposal, decision, result)


def test_unsupported_result_passes_lifecycle_consistency(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = make_proposal("get_order", {"order_id": DEMO_ORDER_ID})
    decision = evaluate_decision(executor, proposal)

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        lambda *args, **kwargs: object(),
    )

    result = executor.execute(proposal, decision)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_code == ExecutionErrorCode.INVALID_RESULT
    check_lifecycle_consistency(proposal, decision, result)


def test_serialization_exception_returns_invalid_result(
    executor: GatedToolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import BaseModel

    from agenttrax.contracts.models import check_lifecycle_consistency

    class UnserializableResult(BaseModel):
        value: object

    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )
    decision = evaluate_decision(executor, proposal)

    assert decision.decision is PolicyDecisionType.ALLOW

    def unserializable_result(
        *args: object,
        **kwargs: object,
    ) -> BaseModel:
        return UnserializableResult(value=object())

    monkeypatch.setattr(
        executor._registry,
        "invoke",
        unserializable_result,
    )

    result = executor.execute(proposal, decision)

    assert result.status is ExecutionStatus.FAILED
    assert result.error_code is ExecutionErrorCode.INVALID_RESULT
    assert result.result is None
    assert result.not_executed_reason is None
    assert result.completed_at == fixed_clock()

    check_lifecycle_consistency(proposal, decision, result)
