"""Gated tool executor for AgentTrax.

Ensures an action can execute only when:
1. The proposal is a valid ActionProposal.
2. The supplied policy decision is a valid PolicyDecision.
3. The proposal and decision refer to the same action.
4. The decision is linked to the exact proposal digest.
5. The policy decision is independently reevaluated against current simulator state.
6. The supplied decision matches the independently calculated decision.
7. The independently calculated decision is ALLOW.
8. The requested tool exists in the simulator's allowlisted registry.
9. The tool invocation succeeds and produces a supported result.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from agenttrax.contracts.models import (
    ActionProposal,
    ContractViolation,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    NotExecutedReason,
    PolicyDecision,
    PolicyDecisionType,
    check_lifecycle_consistency,
    compute_proposal_digest,
    thaw_json_value,
)
from agenttrax.contracts.serialization import freeze_json_value
from agenttrax.policy import PolicyEngine
from agenttrax.scenarios.order_support import ScenarioOperationError
from agenttrax.scenarios.registry import (
    ScenarioRegistryError,
    ScenarioToolRegistry,
)
from agenttrax.scenarios.state import OrderSupportScenarioState


class Clock(Protocol):
    """Injectable clock for deterministic timestamps."""

    def __call__(self) -> datetime: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GatedToolExecutor:
    """Controlled execution gateway between policy and simulator."""

    def __init__(
        self,
        state: OrderSupportScenarioState | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        if state is None:
            state = OrderSupportScenarioState()

        self._state = state
        self._registry = ScenarioToolRegistry(state)
        self._policy_engine = PolicyEngine()
        self._clock = clock

    @property
    def state(self) -> OrderSupportScenarioState:
        return self._state

    @property
    def policy_engine(self) -> PolicyEngine:
        return self._policy_engine

    def execute(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
    ) -> ExecutionResult:
        """Execute an action proposal after validating all integrity constraints.

        Returns an ExecutionResult reflecting the outcome. The registry is never
        invoked unless every integrity check passes and the independent policy
        reevaluation yields ALLOW.
        """
        # 1. Validate contract types.
        self._validate_types(proposal, supplied_decision)

        # 2. Validate action ID and proposal digest linkage.
        self._validate_linkage(proposal, supplied_decision)

        # 3. Obtain current simulator snapshot.
        snapshot = self._state.snapshot()

        # 4. Independently reevaluate policy.
        expected_decision = self._policy_engine.evaluate(proposal, snapshot)

        # 5. Compare supplied decision with expected decision.
        if not self._decisions_match(expected_decision, supplied_decision):
            return self._integrity_failure(proposal, supplied_decision)

        # 6. Only ALLOW decisions may proceed to execution.
        if expected_decision.decision != PolicyDecisionType.ALLOW:
            return self._policy_denial(
                proposal,
                supplied_decision,
                expected_decision,
            )

        # 7. Invoke the allowlisted simulator tool.
        return self._invoke_tool(proposal, supplied_decision)

    def _validate_types(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
    ) -> None:
        if not isinstance(proposal, ActionProposal):
            raise TypeError("proposal must be an ActionProposal.")

        if not isinstance(supplied_decision, PolicyDecision):
            raise TypeError("supplied_decision must be a PolicyDecision.")

    def _validate_linkage(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
    ) -> None:
        if supplied_decision.action_id != proposal.action_id:
            raise ContractViolation("H1: Decision action_id does not match proposal.")

        expected_digest = compute_proposal_digest(proposal)

        if supplied_decision.proposal_digest != expected_digest:
            raise ContractViolation("H2: Decision digest does not match proposal.")

    def _decisions_match(
        self,
        expected: PolicyDecision,
        supplied: PolicyDecision,
    ) -> bool:
        """Compare all meaningful decision fields."""
        if expected.action_id != supplied.action_id:
            return False

        if expected.proposal_digest != supplied.proposal_digest:
            return False

        if expected.decision != supplied.decision:
            return False

        if expected.reason_code != supplied.reason_code:
            return False

        if expected.reason != supplied.reason:
            return False

        if expected.policy_version != supplied.policy_version:
            return False

        return True

    def _integrity_failure(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
    ) -> ExecutionResult:
        """Return NOT_EXECUTED with INTEGRITY_CHECK_FAILED."""
        return self._finalize(
            proposal,
            supplied_decision,
            ExecutionResult(
                action_id=proposal.action_id,
                status=ExecutionStatus.NOT_EXECUTED,
                result=None,
                error_code=None,
                not_executed_reason=NotExecutedReason.INTEGRITY_CHECK_FAILED,
                completed_at=self._clock(),
            ),
        )

    def _policy_denial(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
        expected_decision: PolicyDecision,
    ) -> ExecutionResult:
        """Return NOT_EXECUTED for BLOCK or REQUIRE_APPROVAL decisions."""
        if expected_decision.decision == PolicyDecisionType.BLOCK:
            reason = NotExecutedReason.POLICY_BLOCKED
        else:
            reason = NotExecutedReason.APPROVAL_PENDING

        return self._finalize(
            proposal,
            supplied_decision,
            ExecutionResult(
                action_id=proposal.action_id,
                status=ExecutionStatus.NOT_EXECUTED,
                result=None,
                error_code=None,
                not_executed_reason=reason,
                completed_at=self._clock(),
            ),
        )

    def _invoke_tool(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
    ) -> ExecutionResult:
        """Invoke the tool through the registry and build the execution result."""
        tool_name = proposal.tool_name
        arguments = thaw_json_value(proposal.arguments)

        try:
            raw_result = self._registry.invoke(tool_name, arguments)
        except (ScenarioRegistryError, ScenarioOperationError) as exc:
            return self._registry_failure(proposal, supplied_decision, exc)
        except Exception as exc:
            return self._internal_failure(proposal, supplied_decision, exc)

        # Convert simulator result to a JSON-compatible dictionary.
        try:
            result_dict = self._serialize_result(raw_result)
        except Exception:
            return self._finalize(
                proposal,
                supplied_decision,
                ExecutionResult(
                    action_id=proposal.action_id,
                    status=ExecutionStatus.FAILED,
                    result=None,
                    error_code=ExecutionErrorCode.INVALID_RESULT,
                    not_executed_reason=None,
                    completed_at=self._clock(),
                ),
            )

        result = ExecutionResult(
            action_id=proposal.action_id,
            status=ExecutionStatus.SUCCEEDED,
            result=result_dict,
            error_code=None,
            not_executed_reason=None,
            completed_at=self._clock(),
        )

        return self._finalize(
            proposal,
            supplied_decision,
            result,
        )

    def _serialize_result(self, raw_result: object) -> dict[str, object]:
        """Serialize a supported Pydantic simulator result into a JSON object."""
        if not isinstance(raw_result, BaseModel):
            raise ValueError(
                f"Unsupported simulator result type: {type(raw_result).__name__}"
            )

        dumped = raw_result.model_dump(mode="json")

        # Validate and freeze the data, then return a plain JSON-compatible dict.
        frozen = freeze_json_value(dumped)
        thawed = thaw_json_value(frozen)

        if type(thawed) is not dict:
            raise ValueError("Simulator result must serialize to a JSON object.")

        return thawed

    def _registry_failure(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
        exc: ScenarioRegistryError | ScenarioOperationError,
    ) -> ExecutionResult:
        """Handle expected registry and scenario operation failures."""
        return self._finalize(
            proposal,
            supplied_decision,
            ExecutionResult(
                action_id=proposal.action_id,
                status=ExecutionStatus.FAILED,
                result=None,
                error_code=ExecutionErrorCode.TOOL_ERROR,
                not_executed_reason=None,
                completed_at=self._clock(),
            ),
        )

    def _internal_failure(
        self,
        proposal: ActionProposal,
        supplied_decision: PolicyDecision,
        exc: Exception,
    ) -> ExecutionResult:
        """Handle unexpected internal executor failures."""
        return self._finalize(
            proposal,
            supplied_decision,
            ExecutionResult(
                action_id=proposal.action_id,
                status=ExecutionStatus.FAILED,
                result=None,
                error_code=ExecutionErrorCode.INTERNAL_ERROR,
                not_executed_reason=None,
                completed_at=self._clock(),
            ),
        )

    def _finalize(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Validate lifecycle consistency before returning any result."""
        check_lifecycle_consistency(proposal, decision, result)
        return result
