"""Tests for deterministic order support scenario state."""

import pytest
from pydantic import ValidationError

from agenttrax.scenarios.models import (
    CaseStatus,
    OrderStatus,
    PaymentStatus,
    ScenarioObjective,
    ScenarioSnapshot,
    SimulatedOrder,
    SupportCase,
)
from agenttrax.scenarios.state import (
    DEMO_CASE_ID,
    DEMO_ORDER_ID,
    SCENARIO_ID,
    OrderSupportScenarioState,
)


def test_initial_state_is_deterministic() -> None:
    state = OrderSupportScenarioState()

    snapshot = state.snapshot()

    assert snapshot.scenario_id == SCENARIO_ID
    assert snapshot.order.order_id == DEMO_ORDER_ID
    assert snapshot.order.status == OrderStatus.DELIVERED
    assert snapshot.order.payment_status == PaymentStatus.PAID
    assert snapshot.order.total_minor_units == 12_999
    assert snapshot.order.refunded_minor_units == 0
    assert snapshot.order.remaining_refundable_minor_units == 12_999
    assert snapshot.support_case.case_id == DEMO_CASE_ID
    assert snapshot.support_case.status == CaseStatus.OPEN
    assert snapshot.support_case.notes == ()
    assert snapshot.objective.refund_minor_units == 2_500
    assert snapshot.objective.expected_remaining_minor_units == 10_499


def test_reset_restores_initial_state() -> None:
    state = OrderSupportScenarioState()

    updated_order = SimulatedOrder(
        order_id=DEMO_ORDER_ID,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PARTIALLY_REFUNDED,
        currency="USD",
        total_minor_units=12_999,
        refunded_minor_units=2_500,
    )
    state.replace_order(updated_order)

    reset_snapshot = state.reset()

    assert reset_snapshot.order.refunded_minor_units == 0
    assert reset_snapshot.order.payment_status == PaymentStatus.PAID
    assert reset_snapshot.order.remaining_refundable_minor_units == 12_999


def test_snapshot_is_immutable() -> None:
    state = OrderSupportScenarioState()
    snapshot = state.snapshot()

    with pytest.raises(ValidationError):
        snapshot.order.refunded_minor_units = 2_500


def test_replacing_order_preserves_scenario_identity() -> None:
    state = OrderSupportScenarioState()

    replacement = SimulatedOrder(
        order_id=DEMO_ORDER_ID,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PARTIALLY_REFUNDED,
        currency="USD",
        total_minor_units=12_999,
        refunded_minor_units=2_500,
    )
    state.replace_order(replacement)

    assert state.snapshot().order.refunded_minor_units == 2_500
    assert state.snapshot().order.remaining_refundable_minor_units == 10_499


def test_replacing_order_with_another_order_is_rejected() -> None:
    state = OrderSupportScenarioState()

    other_order = SimulatedOrder(
        order_id="ord_other_001",
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        currency="USD",
        total_minor_units=5_000,
    )

    with pytest.raises(ValueError, match="another order"):
        state.replace_order(other_order)


def test_replacing_case_preserves_scenario_identity() -> None:
    state = OrderSupportScenarioState()

    replacement = SupportCase(
        case_id=DEMO_CASE_ID,
        order_id=DEMO_ORDER_ID,
        status=CaseStatus.OPEN,
        notes=(),
    )
    state.replace_support_case(replacement)

    assert state.snapshot().support_case == replacement


def test_replacing_case_with_another_case_is_rejected() -> None:
    state = OrderSupportScenarioState()

    other_case = SupportCase(
        case_id="case_other_001",
        order_id=DEMO_ORDER_ID,
        status=CaseStatus.OPEN,
    )

    with pytest.raises(ValueError, match="another case"):
        state.replace_support_case(other_case)


def test_replacing_case_for_another_order_is_rejected() -> None:
    state = OrderSupportScenarioState()

    unrelated_case = SupportCase(
        case_id=DEMO_CASE_ID,
        order_id="ord_other_001",
        status=CaseStatus.OPEN,
    )

    with pytest.raises(ValueError, match="scenario order"):
        state.replace_support_case(unrelated_case)

def test_snapshot_rejects_inconsistent_objective_balance() -> None:
    state = OrderSupportScenarioState()
    snapshot = state.snapshot()

    inconsistent_objective = ScenarioObjective(
        refund_minor_units=2_500,
        expected_remaining_minor_units=10_498,
    )

    with pytest.raises(
        ValidationError,
        match="Expected remaining balance does not match the objective refund",
    ):
        ScenarioSnapshot(
            scenario_id=snapshot.scenario_id,
            order=snapshot.order,
            support_case=snapshot.support_case,
            objective=inconsistent_objective,
        )
