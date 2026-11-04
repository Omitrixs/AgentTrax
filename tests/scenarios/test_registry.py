"""Tests for the strict order-support scenario tool registry."""

import pytest

from agenttrax.scenarios.order_support import (
    OperationErrorCode,
    ScenarioOperationError,
)
from agenttrax.scenarios.registry import (
    RegistryErrorCode,
    ScenarioRegistryError,
    ScenarioToolRegistry,
)
from agenttrax.scenarios.state import OrderSupportScenarioState


@pytest.fixture
def state() -> OrderSupportScenarioState:
    return OrderSupportScenarioState()


@pytest.fixture
def registry(state: OrderSupportScenarioState) -> ScenarioToolRegistry:
    return ScenarioToolRegistry(state)


def test_registry_exposes_exactly_four_tools(
    registry: ScenarioToolRegistry,
) -> None:
    assert registry.tool_names == frozenset(
        {"get_order", "add_case_note", "issue_refund", "close_case"}
    )


def test_get_order_returns_current_order(
    registry: ScenarioToolRegistry,
    state: OrderSupportScenarioState,
) -> None:
    result = registry.invoke("get_order", {"order_id": "ord_demo_001"})

    assert result == state.order


def test_add_case_note_routes_to_operation(
    registry: ScenarioToolRegistry,
    state: OrderSupportScenarioState,
) -> None:
    result = registry.invoke(
        "add_case_note",
        {"case_id": "case_demo_001", "note": "Customer contacted support."},
    )

    assert result == state.support_case
    assert len(state.support_case.notes) == 1


def test_issue_refund_routes_to_operation(
    registry: ScenarioToolRegistry,
    state: OrderSupportScenarioState,
) -> None:
    result = registry.invoke(
        "issue_refund",
        {"order_id": "ord_demo_001", "amount_minor_units": 2500},
    )

    assert result == state.order
    assert state.order.refunded_minor_units == 2500


def test_close_case_routes_to_operation(
    registry: ScenarioToolRegistry,
    state: OrderSupportScenarioState,
) -> None:
    registry.invoke(
        "add_case_note",
        {"case_id": "case_demo_001", "note": "Refund processed."},
    )
    registry.invoke(
        "issue_refund",
        {"order_id": "ord_demo_001", "amount_minor_units": 2500},
    )

    result = registry.invoke("close_case", {"case_id": "case_demo_001"})

    assert result == state.support_case
    assert state.support_case.status.value == "CLOSED"


def test_unknown_tool_is_rejected(
    registry: ScenarioToolRegistry,
) -> None:
    with pytest.raises(ScenarioRegistryError) as exc_info:
        registry.invoke("delete_customer", {})

    assert exc_info.value.code == RegistryErrorCode.UNKNOWN_TOOL


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"order_id": "ord_demo_001", "extra": "not allowed"},
        {"order_id": 123},
        {"order_id": "ord_demo_001", "amount_minor_units": 100},
        {"order_id": "ord_demo_001", 1: "unexpected"},
    ],
)
def test_get_order_rejects_invalid_argument_shapes_and_types(
    registry: ScenarioToolRegistry,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ScenarioRegistryError) as exc_info:
        registry.invoke("get_order", arguments)

    assert exc_info.value.code == RegistryErrorCode.INVALID_ARGUMENTS


@pytest.mark.parametrize("amount", [True, 0, -1, 2.5, "2500", None])
def test_issue_refund_rejects_invalid_amount_types_or_values(
    registry: ScenarioToolRegistry,
    amount: object,
) -> None:
    with pytest.raises(ScenarioRegistryError) as exc_info:
        registry.invoke(
            "issue_refund",
            {"order_id": "ord_demo_001", "amount_minor_units": amount},
        )

    assert exc_info.value.code == RegistryErrorCode.INVALID_ARGUMENTS


def test_registry_validation_does_not_mutate_state(
    registry: ScenarioToolRegistry,
    state: OrderSupportScenarioState,
) -> None:
    before = state.snapshot()

    with pytest.raises(ScenarioRegistryError):
        registry.invoke("issue_refund", {"order_id": "ord_demo_001"})

    assert state.snapshot() == before


def test_business_rule_errors_are_not_hidden_by_registry(
    registry: ScenarioToolRegistry,
) -> None:
    with pytest.raises(ScenarioOperationError) as exc_info:
        registry.invoke(
            "issue_refund",
            {"order_id": "unknown_order", "amount_minor_units": 2500},
        )
    assert exc_info.value.code == OperationErrorCode.UNKNOWN_ORDER
