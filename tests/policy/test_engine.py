"""Tests for the deterministic order-support policy engine."""

from datetime import UTC, datetime

import pytest

from agenttrax.contracts.models import (
    ActionProposal,
    PolicyDecisionType,
    PolicyReasonCode,
    compute_proposal_digest,
)
from agenttrax.policy import POLICY_VERSION, PolicyEngine
from agenttrax.scenarios.models import (
    CaseNote,
    CaseStatus,
    PaymentStatus,
    SimulatedOrder,
    SupportCase,
)
from agenttrax.scenarios.state import (
    DEMO_CASE_ID,
    DEMO_ORDER_ID,
    OrderSupportScenarioState,
)


@pytest.fixture
def state() -> OrderSupportScenarioState:
    return OrderSupportScenarioState()


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine()


def make_proposal(
    tool_name: str,
    arguments: dict[str, object],
) -> ActionProposal:
    return ActionProposal(
        action_id="action_test_001",
        task_id="task_test_001",
        tool_name=tool_name,
        arguments=arguments,
        requested_by="test_agent",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def evaluate(
    engine: PolicyEngine,
    state: OrderSupportScenarioState,
    tool_name: str,
    arguments: dict[str, object],
):
    proposal = make_proposal(tool_name, arguments)
    return engine.evaluate(proposal, state.snapshot())


def assert_decision(decision, expected_type, expected_reason_code):
    assert decision.decision == expected_type
    assert decision.reason_code == expected_reason_code
    assert decision.reason.strip()
    assert decision.policy_version == POLICY_VERSION


# ---------------------------------------------------------------------------
# ALLOW decisions
# ---------------------------------------------------------------------------


def test_get_order_is_allowed(engine, state):
    decision = evaluate(
        engine,
        state,
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )

    assert_decision(
        decision,
        PolicyDecisionType.ALLOW,
        PolicyReasonCode.ALLOWED_BY_POLICY,
    )


def test_add_case_note_accepts_maximum_length(engine, state):
    decision = evaluate(
        engine,
        state,
        "add_case_note",
        {
            "case_id": DEMO_CASE_ID,
            "note": "x" * 500,
        },
    )

    assert_decision(
        decision,
        PolicyDecisionType.ALLOW,
        PolicyReasonCode.ALLOWED_BY_POLICY,
    )


def test_close_case_is_allowed_after_refund_and_note(engine, state):
    state.replace_order(
        SimulatedOrder(
            order_id=DEMO_ORDER_ID,
            status=state.order.status,
            payment_status=PaymentStatus.PARTIALLY_REFUNDED,
            currency=state.order.currency,
            total_minor_units=state.order.total_minor_units,
            refunded_minor_units=2_500,
        )
    )

    state.replace_support_case(
        SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.OPEN,
            notes=(CaseNote(sequence=1, note="Refund completed."),),
        )
    )

    decision = evaluate(
        engine,
        state,
        "close_case",
        {"case_id": DEMO_CASE_ID},
    )

    assert_decision(
        decision,
        PolicyDecisionType.ALLOW,
        PolicyReasonCode.ALLOWED_BY_POLICY,
    )


# ---------------------------------------------------------------------------
# REQUIRE_APPROVAL decisions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", [1, 2_500, 12_999])
def test_valid_refund_requires_approval(engine, state, amount):
    decision = evaluate(
        engine,
        state,
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": amount,
        },
    )

    assert_decision(
        decision,
        PolicyDecisionType.REQUIRE_APPROVAL,
        PolicyReasonCode.APPROVAL_REQUIRED,
    )


def test_refund_requires_approval_at_exact_remaining_balance(engine, state):
    decision = evaluate(
        engine,
        state,
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": state.order.remaining_refundable_minor_units,
        },
    )

    assert decision.decision == PolicyDecisionType.REQUIRE_APPROVAL


# ---------------------------------------------------------------------------
# BLOCK decisions
# ---------------------------------------------------------------------------


def test_unknown_tool_is_blocked(engine, state):
    decision = evaluate(engine, state, "delete_order", {})

    assert_decision(
        decision,
        PolicyDecisionType.BLOCK,
        PolicyReasonCode.UNKNOWN_TOOL,
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("get_order", {"order_id": "ord_missing"}),
        ("add_case_note", {"case_id": "case_missing", "note": "Valid note."}),
        (
            "issue_refund",
            {"order_id": "ord_missing", "amount_minor_units": 100},
        ),
        ("close_case", {"case_id": "case_missing"}),
    ],
)
def test_unknown_records_are_blocked(
    engine,
    state,
    tool_name,
    arguments,
):
    decision = evaluate(engine, state, tool_name, arguments)

    assert_decision(
        decision,
        PolicyDecisionType.BLOCK,
        PolicyReasonCode.BLOCKED_BY_POLICY,
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("get_order", {}),
        ("get_order", {"order_id": DEMO_ORDER_ID, "extra": "value"}),
        ("add_case_note", {"case_id": DEMO_CASE_ID}),
        ("add_case_note", {"case_id": DEMO_CASE_ID, "note": " ", "extra": 1}),
        ("issue_refund", {"order_id": DEMO_ORDER_ID}),
        ("close_case", {"case_id": DEMO_CASE_ID, "extra": "value"}),
        ("get_order", {"order_id": 123}),
        ("add_case_note", {"case_id": DEMO_CASE_ID, "note": 123}),
        ("add_case_note", {"case_id": DEMO_CASE_ID, "note": "x" * 501}),
        (
            "issue_refund",
            {"order_id": DEMO_ORDER_ID, "amount_minor_units": True},
        ),
        (
            "issue_refund",
            {"order_id": DEMO_ORDER_ID, "amount_minor_units": 0},
        ),
        (
            "issue_refund",
            {"order_id": DEMO_ORDER_ID, "amount_minor_units": -1},
        ),
        (
            "issue_refund",
            {"order_id": DEMO_ORDER_ID, "amount_minor_units": 1.5},
        ),
    ],
)
def test_invalid_arguments_are_blocked(
    engine,
    state,
    tool_name,
    arguments,
):
    decision = evaluate(engine, state, tool_name, arguments)

    assert_decision(
        decision,
        PolicyDecisionType.BLOCK,
        PolicyReasonCode.INVALID_ARGUMENTS,
    )


def test_refund_exceeding_remaining_balance_is_blocked(engine, state):
    decision = evaluate(
        engine,
        state,
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": 13_000,
        },
    )

    assert decision.decision == PolicyDecisionType.BLOCK


def test_refund_on_unpaid_order_is_blocked(engine, state):
    state.replace_order(
        SimulatedOrder(
            order_id=DEMO_ORDER_ID,
            status=state.order.status,
            payment_status=PaymentStatus.UNPAID,
            currency=state.order.currency,
            total_minor_units=state.order.total_minor_units,
            refunded_minor_units=0,
        )
    )

    decision = evaluate(
        engine,
        state,
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": 2_500,
        },
    )

    assert decision.decision == PolicyDecisionType.BLOCK


def test_note_on_closed_case_is_blocked(engine, state):
    state.replace_support_case(
        SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.CLOSED,
            notes=(),
        )
    )

    decision = evaluate(
        engine,
        state,
        "add_case_note",
        {
            "case_id": DEMO_CASE_ID,
            "note": "This must be rejected.",
        },
    )

    assert decision.decision == PolicyDecisionType.BLOCK


def test_close_case_without_refund_is_blocked(engine, state):
    decision = evaluate(
        engine,
        state,
        "close_case",
        {"case_id": DEMO_CASE_ID},
    )

    assert decision.decision == PolicyDecisionType.BLOCK


def test_close_case_without_note_is_blocked(engine, state):
    state.replace_order(
        SimulatedOrder(
            order_id=DEMO_ORDER_ID,
            status=state.order.status,
            payment_status=PaymentStatus.PARTIALLY_REFUNDED,
            currency=state.order.currency,
            total_minor_units=state.order.total_minor_units,
            refunded_minor_units=2_500,
        )
    )

    decision = evaluate(
        engine,
        state,
        "close_case",
        {"case_id": DEMO_CASE_ID},
    )

    assert decision.decision == PolicyDecisionType.BLOCK


def test_close_already_closed_case_is_blocked(engine, state):
    state.replace_support_case(
        SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.CLOSED,
            notes=(),
        )
    )

    decision = evaluate(
        engine,
        state,
        "close_case",
        {"case_id": DEMO_CASE_ID},
    )

    assert decision.decision == PolicyDecisionType.BLOCK


# ---------------------------------------------------------------------------
# Integrity and purity
# ---------------------------------------------------------------------------


def test_decision_is_bound_to_proposal(engine, state):
    proposal = make_proposal(
        "get_order",
        {"order_id": DEMO_ORDER_ID},
    )

    decision = engine.evaluate(proposal, state.snapshot())

    assert decision.action_id == proposal.action_id
    assert decision.proposal_digest == compute_proposal_digest(proposal)


def test_same_input_produces_same_decision(engine, state):
    proposal = make_proposal(
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": 2_500,
        },
    )
    snapshot = state.snapshot()

    first = engine.evaluate(proposal, snapshot)
    second = engine.evaluate(proposal, snapshot)

    assert first == second


def test_policy_evaluation_does_not_mutate_state(engine, state):
    before = state.snapshot()

    evaluate(
        engine,
        state,
        "issue_refund",
        {
            "order_id": DEMO_ORDER_ID,
            "amount_minor_units": 2_500,
        },
    )

    assert state.snapshot() == before


def test_policy_engine_rejects_wrong_input_types(engine, state):
    with pytest.raises(TypeError):
        engine.evaluate("not a proposal", state.snapshot())

    with pytest.raises(TypeError):
        engine.evaluate(
            make_proposal("get_order", {"order_id": DEMO_ORDER_ID}),
            "not a snapshot",
        )
