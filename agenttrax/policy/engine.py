"""Pure policy evaluation for the deterministic order-support scenario."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from agenttrax.contracts.models import (
    ActionProposal,
    PolicyDecision,
    PolicyDecisionType,
    PolicyReasonCode,
    compute_proposal_digest,
)
from agenttrax.scenarios.models import (
    CaseStatus,
    PaymentStatus,
    ScenarioSnapshot,
)

POLICY_VERSION = "order_support_policy_v1"

_TOOL_ARGUMENTS = MappingProxyType(
    {
        "get_order": frozenset({"order_id"}),
        "add_case_note": frozenset({"case_id", "note"}),
        "issue_refund": frozenset({"order_id", "amount_minor_units"}),
        "close_case": frozenset({"case_id"}),
    }
)


class PolicyEngine:
    """Evaluate order-support actions without executing or mutating them."""

    def evaluate(
        self,
        proposal: ActionProposal,
        snapshot: ScenarioSnapshot,
    ) -> PolicyDecision:
        """Return a deterministic policy decision for one action proposal."""

        if not isinstance(proposal, ActionProposal):
            raise TypeError("proposal must be an ActionProposal.")

        if not isinstance(snapshot, ScenarioSnapshot):
            raise TypeError("snapshot must be a ScenarioSnapshot.")

        tool_name = proposal.tool_name

        if tool_name not in _TOOL_ARGUMENTS:
            return self._decision(
                proposal,
                PolicyDecisionType.BLOCK,
                PolicyReasonCode.UNKNOWN_TOOL,
                f"Tool '{tool_name}' is not allowed by this policy.",
            )

        arguments = proposal.arguments

        if not self._has_valid_arguments(tool_name, arguments):
            return self._decision(
                proposal,
                PolicyDecisionType.BLOCK,
                PolicyReasonCode.INVALID_ARGUMENTS,
                f"Arguments are invalid for tool '{tool_name}'.",
            )

        if tool_name == "get_order":
            return self._evaluate_get_order(proposal, snapshot, arguments)

        if tool_name == "add_case_note":
            return self._evaluate_add_case_note(proposal, snapshot, arguments)

        if tool_name == "issue_refund":
            return self._evaluate_issue_refund(proposal, snapshot, arguments)

        return self._evaluate_close_case(proposal, snapshot, arguments)

    @staticmethod
    def _has_valid_arguments(
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> bool:
        """Validate exact argument names and strict argument value types."""

        if set(arguments) != _TOOL_ARGUMENTS[tool_name]:
            return False

        if tool_name == "get_order":
            return PolicyEngine._valid_identifier(arguments["order_id"])

        if tool_name == "add_case_note":
            note = arguments["note"]
            return (
                PolicyEngine._valid_identifier(arguments["case_id"])
                and type(note) is str
                and bool(note.strip())
                and len(note) <= 500
            )

        if tool_name == "issue_refund":
            amount = arguments["amount_minor_units"]
            return (
                PolicyEngine._valid_identifier(arguments["order_id"])
                and type(amount) is int
                and amount > 0
            )

        return PolicyEngine._valid_identifier(arguments["case_id"])

    @staticmethod
    def _valid_identifier(value: object) -> bool:
        """Return whether a value is a nonblank string identifier."""

        return type(value) is str and bool(value.strip())

    def _evaluate_get_order(
        self,
        proposal: ActionProposal,
        snapshot: ScenarioSnapshot,
        arguments: Mapping[str, object],
    ) -> PolicyDecision:
        if arguments["order_id"] != snapshot.order.order_id:
            return self._blocked(
                proposal,
                "The requested order does not exist in this scenario.",
            )

        return self._allowed(
            proposal,
            "Reading the scenario order is permitted.",
        )

    def _evaluate_add_case_note(
        self,
        proposal: ActionProposal,
        snapshot: ScenarioSnapshot,
        arguments: Mapping[str, object],
    ) -> PolicyDecision:
        if arguments["case_id"] != snapshot.support_case.case_id:
            return self._blocked(
                proposal,
                "The requested support case does not exist in this scenario.",
            )

        if snapshot.support_case.status == CaseStatus.CLOSED:
            return self._blocked(
                proposal,
                "A note cannot be added to a closed support case.",
            )

        return self._allowed(
            proposal,
            "Adding a valid note to an open support case is permitted.",
        )

    def _evaluate_issue_refund(
        self,
        proposal: ActionProposal,
        snapshot: ScenarioSnapshot,
        arguments: Mapping[str, object],
    ) -> PolicyDecision:
        if arguments["order_id"] != snapshot.order.order_id:
            return self._blocked(
                proposal,
                "The requested order does not exist in this scenario.",
            )

        if snapshot.order.payment_status == PaymentStatus.UNPAID:
            return self._blocked(
                proposal,
                "An unpaid order cannot be refunded.",
            )

        amount = arguments["amount_minor_units"]

        if amount > snapshot.order.remaining_refundable_minor_units:
            return self._blocked(
                proposal,
                "The refund amount exceeds the remaining refundable balance.",
            )

        return self._requires_approval(
            proposal,
            "The refund is valid but requires approval before execution.",
        )

    def _evaluate_close_case(
        self,
        proposal: ActionProposal,
        snapshot: ScenarioSnapshot,
        arguments: Mapping[str, object],
    ) -> PolicyDecision:
        if arguments["case_id"] != snapshot.support_case.case_id:
            return self._blocked(
                proposal,
                "The requested support case does not exist in this scenario.",
            )

        if snapshot.support_case.status == CaseStatus.CLOSED:
            return self._blocked(
                proposal,
                "The support case is already closed.",
            )

        if snapshot.order.refunded_minor_units <= 0:
            return self._blocked(
                proposal,
                "A successful simulated refund is required before closing.",
            )

        if not snapshot.support_case.notes:
            return self._blocked(
                proposal,
                "At least one case note is required before closing.",
            )

        return self._allowed(
            proposal,
            "The support case satisfies the closure requirements.",
        )

    def _decision(
        self,
        proposal: ActionProposal,
        decision: PolicyDecisionType,
        reason_code: PolicyReasonCode,
        reason: str,
    ) -> PolicyDecision:
        """Build a decision bound to the exact proposal digest."""

        return PolicyDecision(
            action_id=proposal.action_id,
            proposal_digest=compute_proposal_digest(proposal),
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            policy_version=POLICY_VERSION,
        )

    def _allowed(
        self,
        proposal: ActionProposal,
        reason: str,
    ) -> PolicyDecision:
        return self._decision(
            proposal,
            PolicyDecisionType.ALLOW,
            PolicyReasonCode.ALLOWED_BY_POLICY,
            reason,
        )

    def _blocked(
        self,
        proposal: ActionProposal,
        reason: str,
    ) -> PolicyDecision:
        return self._decision(
            proposal,
            PolicyDecisionType.BLOCK,
            PolicyReasonCode.BLOCKED_BY_POLICY,
            reason,
        )

    def _requires_approval(
        self,
        proposal: ActionProposal,
        reason: str,
    ) -> PolicyDecision:
        return self._decision(
            proposal,
            PolicyDecisionType.REQUIRE_APPROVAL,
            PolicyReasonCode.APPROVAL_REQUIRED,
            reason,
        )
