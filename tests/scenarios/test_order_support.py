"""Tests for deterministic order support operations."""

import pytest

from agenttrax.scenarios.models import (
    CaseStatus,
    OrderStatus,
    PaymentStatus,
    SimulatedOrder,
)
from agenttrax.scenarios.order_support import (
    OperationErrorCode,
    ScenarioOperationError,
    add_case_note,
    close_case,
    get_order,
    issue_refund,
)
from agenttrax.scenarios.state import (
    DEMO_CASE_ID,
    DEMO_ORDER_ID,
    OrderSupportScenarioState,
)


def assert_operation_error(
    expected_code: OperationErrorCode,
    operation,
    *args,
) -> None:
    with pytest.raises(ScenarioOperationError) as exc_info:
        operation(*args)

    assert exc_info.value.code == expected_code


def test_get_order_returns_order_without_mutating_state() -> None:
    state = OrderSupportScenarioState()

    order = get_order(state, DEMO_ORDER_ID)

    assert order == state.order
    assert state.order.refunded_minor_units == 0


def test_get_order_rejects_unknown_order() -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.UNKNOWN_ORDER,
        get_order,
        state,
        "ord_missing",
    )


@pytest.mark.parametrize("order_id", ["", " ", None, 123])
def test_get_order_rejects_invalid_identifier(order_id) -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.INVALID_ARGUMENT,
        get_order,
        state,
        order_id,
    )


def test_add_case_note_appends_sequential_note() -> None:
    state = OrderSupportScenarioState()

    first = add_case_note(state, DEMO_CASE_ID, "Customer requested a refund.")
    second = add_case_note(state, DEMO_CASE_ID, "Refund processed.")

    assert [note.sequence for note in first.notes] == [1]
    assert [note.sequence for note in second.notes] == [1, 2]
    assert second.notes[1].note == "Refund processed."


@pytest.mark.parametrize("note", ["", " ", "\n", None, 123, "x" * 501])
def test_add_case_note_rejects_invalid_note(note) -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.INVALID_ARGUMENT,
        add_case_note,
        state,
        DEMO_CASE_ID,
        note,
    )

    assert state.support_case.notes == ()


def test_add_case_note_rejects_unknown_case() -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.UNKNOWN_CASE,
        add_case_note,
        state,
        "case_missing",
        "A valid note.",
    )


def test_add_case_note_rejects_closed_case() -> None:
    state = OrderSupportScenarioState()
    add_case_note(state, DEMO_CASE_ID, "Initial note.")
    issue_refund(state, DEMO_ORDER_ID, 2_500)
    close_case(state, DEMO_CASE_ID)

    assert_operation_error(
        OperationErrorCode.CASE_CLOSED,
        add_case_note,
        state,
        DEMO_CASE_ID,
        "This must be rejected.",
    )


def test_issue_refund_updates_balance_and_payment_status() -> None:
    state = OrderSupportScenarioState()

    order = issue_refund(state, DEMO_ORDER_ID, 2_500)

    assert order.refunded_minor_units == 2_500
    assert order.remaining_refundable_minor_units == 10_499
    assert order.payment_status == PaymentStatus.PARTIALLY_REFUNDED

def test_issue_refund_rejects_unpaid_order_without_mutation() -> None:
    state = OrderSupportScenarioState()

    unpaid_order = SimulatedOrder(
        order_id=DEMO_ORDER_ID,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.UNPAID,
        currency="USD",
        total_minor_units=12_999,
        refunded_minor_units=0,
    )
    state.replace_order(unpaid_order)
    before = state.snapshot()

    assert_operation_error(
        OperationErrorCode.ORDER_UNPAID,
        issue_refund,
        state,
        DEMO_ORDER_ID,
        2_500,
    )

    assert state.snapshot() == before

def test_issue_refund_can_fully_refund_order() -> None:
    state = OrderSupportScenarioState()

    order = issue_refund(state, DEMO_ORDER_ID, 12_999)

    assert order.refunded_minor_units == 12_999
    assert order.remaining_refundable_minor_units == 0
    assert order.payment_status == PaymentStatus.REFUNDED


@pytest.mark.parametrize("amount", [0, -1, 1.5, True, False, "2500", None])
def test_issue_refund_rejects_invalid_amount(amount) -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.INVALID_ARGUMENT,
        issue_refund,
        state,
        DEMO_ORDER_ID,
        amount,
    )

    assert state.order.refunded_minor_units == 0


def test_issue_refund_rejects_unknown_order() -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.UNKNOWN_ORDER,
        issue_refund,
        state,
        "ord_missing",
        2_500,
    )


def test_issue_refund_rejects_amount_above_balance_without_mutation() -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.REFUND_EXCEEDS_BALANCE,
        issue_refund,
        state,
        DEMO_ORDER_ID,
        13_000,
    )

    assert state.order.refunded_minor_units == 0


def test_close_case_requires_refund() -> None:
    state = OrderSupportScenarioState()
    add_case_note(state, DEMO_CASE_ID, "Refund requested.")

    assert_operation_error(
        OperationErrorCode.REFUND_REQUIRED,
        close_case,
        state,
        DEMO_CASE_ID,
    )

    assert state.support_case.status == CaseStatus.OPEN


def test_close_case_requires_note() -> None:
    state = OrderSupportScenarioState()
    issue_refund(state, DEMO_ORDER_ID, 2_500)

    assert_operation_error(
        OperationErrorCode.CASE_NOTE_REQUIRED,
        close_case,
        state,
        DEMO_CASE_ID,
    )

    assert state.support_case.status == CaseStatus.OPEN


def test_close_case_rejects_unknown_case() -> None:
    state = OrderSupportScenarioState()

    assert_operation_error(
        OperationErrorCode.UNKNOWN_CASE,
        close_case,
        state,
        "case_missing",
    )


def test_close_case_completes_valid_workflow() -> None:
    state = OrderSupportScenarioState()

    add_case_note(state, DEMO_CASE_ID, "Customer requested a partial refund.")
    order = issue_refund(state, DEMO_ORDER_ID, 2_500)
    case = close_case(state, DEMO_CASE_ID)

    assert order.remaining_refundable_minor_units == 10_499
    assert case.status == CaseStatus.CLOSED
    assert len(case.notes) == 1
    assert state.snapshot().order.refunded_minor_units == 2_500


def test_close_case_rejects_second_close() -> None:
    state = OrderSupportScenarioState()
    add_case_note(state, DEMO_CASE_ID, "Refund requested.")
    issue_refund(state, DEMO_ORDER_ID, 2_500)
    close_case(state, DEMO_CASE_ID)

    assert_operation_error(
        OperationErrorCode.CASE_ALREADY_CLOSED,
        close_case,
        state,
        DEMO_CASE_ID,
    )
