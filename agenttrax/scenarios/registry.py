"""Allowlisted tool registry for the deterministic order-support scenario."""

from __future__ import annotations

from enum import StrEnum

from agenttrax.scenarios.order_support import (
    add_case_note,
    close_case,
    get_order,
    issue_refund,
)
from agenttrax.scenarios.state import OrderSupportScenarioState


class RegistryErrorCode(StrEnum):
    """Machine-readable reasons for registry-level rejection."""

    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"


class ScenarioRegistryError(Exception):
    """Raised when a tool call is rejected by the scenario registry."""

    def __init__(self, code: RegistryErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ScenarioToolRegistry:
    """Expose only the four explicitly approved scenario operations."""

    def __init__(self, state: OrderSupportScenarioState) -> None:
        if not isinstance(state, OrderSupportScenarioState):
            raise TypeError("state must be an OrderSupportScenarioState.")

        self._state = state
        self._handlers = {
            "get_order": ({"order_id"}, get_order),
            "add_case_note": ({"case_id", "note"}, add_case_note),
            "issue_refund": (
                {"order_id", "amount_minor_units"},
                issue_refund,
            ),
            "close_case": ({"case_id"}, close_case),
        }

    @property
    def tool_names(self) -> frozenset[str]:
        """Return the immutable set of registered tool names."""
        return frozenset(self._handlers)

    def invoke(self, tool_name: str, arguments: dict[str, object]) -> object:
        """Validate and invoke one registered scenario operation."""

        if not isinstance(tool_name, str) or tool_name not in self._handlers:
            raise ScenarioRegistryError(
                RegistryErrorCode.UNKNOWN_TOOL,
                f"Tool is not registered: {tool_name!r}.",
            )

        if type(arguments) is not dict:
            raise ScenarioRegistryError(
                RegistryErrorCode.INVALID_ARGUMENTS,
                "Tool arguments must be a plain dictionary.",
            )

        if any(type(key) is not str for key in arguments):
            raise ScenarioRegistryError(
                RegistryErrorCode.INVALID_ARGUMENTS,
                "All tool argument names must be strings.",
            )

        required_arguments, handler = self._handlers[tool_name]
        supplied_arguments = set(arguments)

        if supplied_arguments != required_arguments:
            missing = sorted(required_arguments - supplied_arguments)
            unexpected = sorted(supplied_arguments - required_arguments)
            details = []
            if missing:
                details.append(f"missing arguments: {missing}")
            if unexpected:
                details.append(f"unexpected arguments: {unexpected}")

            raise ScenarioRegistryError(
                RegistryErrorCode.INVALID_ARGUMENTS,
                "; ".join(details),
            )

        if tool_name == "get_order":
            valid_types = type(arguments["order_id"]) is str
        elif tool_name == "add_case_note":
            valid_types = (
                type(arguments["case_id"]) is str
                and type(arguments["note"]) is str
            )
        elif tool_name == "issue_refund":
            valid_types = (
                type(arguments["order_id"]) is str
                and type(arguments["amount_minor_units"]) is int
                and arguments["amount_minor_units"] > 0
            )
        else:  # close_case
            valid_types = type(arguments["case_id"]) is str

        if not valid_types:
            raise ScenarioRegistryError(
                RegistryErrorCode.INVALID_ARGUMENTS,
                f"Arguments have invalid types or values for {tool_name!r}.",
            )

        return handler(self._state, **arguments)
