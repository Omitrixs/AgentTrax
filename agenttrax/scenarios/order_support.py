"""Deterministic operations for the order support scenario."""

from enum import StrEnum

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


class OperationErrorCode(StrEnum):
    """Stable error codes for rejected scenario operations."""

    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    UNKNOWN_CASE = "UNKNOWN_CASE"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CASE_CLOSED = "CASE_CLOSED"
    ORDER_UNPAID = "ORDER_UNPAID"
    REFUND_EXCEEDS_BALANCE = "REFUND_EXCEEDS_BALANCE"
    REFUND_REQUIRED = "REFUND_REQUIRED"
    CASE_NOTE_REQUIRED = "CASE_NOTE_REQUIRED"
    CASE_ALREADY_CLOSED = "CASE_ALREADY_CLOSED"


class ScenarioOperationError(Exception):
    """A structured, expected rejection from a scenario operation."""

    def __init__(self, code: OperationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioOperationError(
            OperationErrorCode.INVALID_ARGUMENT,
            f"{field_name} must be a non-empty string.",
        )
    return value


def get_order(
    state: OrderSupportScenarioState,
    order_id: str,
) -> SimulatedOrder:
    """Return the requested simulated order without changing state."""

    order_id = _validate_identifier(order_id, "order_id")

    if order_id != DEMO_ORDER_ID or order_id != state.order.order_id:
        raise ScenarioOperationError(
            OperationErrorCode.UNKNOWN_ORDER,
            f"Order '{order_id}' was not found.",
        )

    return state.order


def add_case_note(
    state: OrderSupportScenarioState,
    case_id: str,
    note: str,
) -> SupportCase:
    """Append a deterministic note to an open support case."""

    case_id = _validate_identifier(case_id, "case_id")

    if not isinstance(note, str) or not note.strip() or len(note) > 500:
        raise ScenarioOperationError(
            OperationErrorCode.INVALID_ARGUMENT,
            "note must contain 1 to 500 non-whitespace characters.",
        )

    case = state.support_case

    if case_id != DEMO_CASE_ID or case_id != case.case_id:
        raise ScenarioOperationError(
            OperationErrorCode.UNKNOWN_CASE,
            f"Case '{case_id}' was not found.",
        )

    if case.status == CaseStatus.CLOSED:
        raise ScenarioOperationError(
            OperationErrorCode.CASE_CLOSED,
            "Cannot add a note to a closed case.",
        )

    new_note = CaseNote(
        sequence=len(case.notes) + 1,
        note=note,
    )
    updated_case = SupportCase(
        case_id=case.case_id,
        order_id=case.order_id,
        status=case.status,
        notes=(*case.notes, new_note),
    )

    state.replace_support_case(updated_case)
    return updated_case


def issue_refund(
    state: OrderSupportScenarioState,
    order_id: str,
    amount_minor_units: int,
) -> SimulatedOrder:
    """Apply a simulated refund in integer minor currency units."""

    order_id = _validate_identifier(order_id, "order_id")

    if (
        isinstance(amount_minor_units, bool)
        or not isinstance(amount_minor_units, int)
        or amount_minor_units <= 0
    ):
        raise ScenarioOperationError(
            OperationErrorCode.INVALID_ARGUMENT,
            "amount_minor_units must be a positive integer.",
        )

    order = state.order

    if order_id != DEMO_ORDER_ID or order_id != order.order_id:
        raise ScenarioOperationError(
            OperationErrorCode.UNKNOWN_ORDER,
            f"Order '{order_id}' was not found.",
        )

    if order.payment_status == PaymentStatus.UNPAID:
        raise ScenarioOperationError(
            OperationErrorCode.ORDER_UNPAID,
            "Cannot refund an unpaid order.",
        )

    if amount_minor_units > order.remaining_refundable_minor_units:
        raise ScenarioOperationError(
            OperationErrorCode.REFUND_EXCEEDS_BALANCE,
            "Refund amount exceeds the remaining refundable balance.",
        )

    refunded_total = order.refunded_minor_units + amount_minor_units
    payment_status = (
        PaymentStatus.REFUNDED
        if refunded_total == order.total_minor_units
        else PaymentStatus.PARTIALLY_REFUNDED
    )

    updated_order = SimulatedOrder(
        order_id=order.order_id,
        status=order.status,
        payment_status=payment_status,
        currency=order.currency,
        total_minor_units=order.total_minor_units,
        refunded_minor_units=refunded_total,
    )

    state.replace_order(updated_order)
    return updated_order


def close_case(
    state: OrderSupportScenarioState,
    case_id: str,
) -> SupportCase:
    """Close a case after a successful refund and at least one note."""

    case_id = _validate_identifier(case_id, "case_id")

    case = state.support_case

    if case_id != DEMO_CASE_ID or case_id != case.case_id:
        raise ScenarioOperationError(
            OperationErrorCode.UNKNOWN_CASE,
            f"Case '{case_id}' was not found.",
        )

    if case.status == CaseStatus.CLOSED:
        raise ScenarioOperationError(
            OperationErrorCode.CASE_ALREADY_CLOSED,
            "Case is already closed.",
        )

    if state.order.refunded_minor_units <= 0:
        raise ScenarioOperationError(
            OperationErrorCode.REFUND_REQUIRED,
            "A successful simulated refund is required before closing.",
        )

    if not case.notes:
        raise ScenarioOperationError(
            OperationErrorCode.CASE_NOTE_REQUIRED,
            "At least one case note is required before closing.",
        )

    updated_case = SupportCase(
        case_id=case.case_id,
        order_id=case.order_id,
        status=CaseStatus.CLOSED,
        notes=case.notes,
    )

    state.replace_support_case(updated_case)
    return updated_case
