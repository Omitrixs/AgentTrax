"""Independent verification of observed scenario outcomes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from agenttrax.contracts.models import (
    ActionProposal,
    ExecutionResult,
    ExecutionStatus,
    TaskVerificationResult,
    VerificationReasonCode,
    VerificationResult,
    VerificationStatus,
)
from agenttrax.contracts.serialization import thaw_json_value
from agenttrax.scenarios.models import (
    CaseStatus,
    PaymentStatus,
    ScenarioSnapshot,
)
from agenttrax.scenarios.state import OrderSupportScenarioState

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(UTC)


class IndependentVerifier:
    """Verify simulator outcomes using observed state, not agent claims."""

    def __init__(
        self,
        state: OrderSupportScenarioState,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(state, OrderSupportScenarioState):
            raise TypeError("state must be an OrderSupportScenarioState.")

        if not callable(clock):
            raise TypeError("clock must be callable.")

        self._state = state
        self._clock = clock

    def verify_action(
        self,
        proposal: ActionProposal,
        execution_result: ExecutionResult,
        before_snapshot: ScenarioSnapshot,
    ) -> VerificationResult:
        """Verify one action against its pre-execution and observed state."""

        if not isinstance(proposal, ActionProposal):
            raise TypeError("proposal must be an ActionProposal.")

        if not isinstance(execution_result, ExecutionResult):
            raise TypeError("execution_result must be an ExecutionResult.")

        if not isinstance(before_snapshot, ScenarioSnapshot):
            raise TypeError("before_snapshot must be a ScenarioSnapshot.")

        if proposal.action_id != execution_result.action_id:
            raise ValueError("Proposal and execution action IDs must match.")

        try:
            after_snapshot = self._state.snapshot()
            evidence = {
                "tool_name": proposal.tool_name,
                "execution_status": execution_result.status.value,
                "before": before_snapshot.model_dump(mode="json"),
                "after": after_snapshot.model_dump(mode="json"),
            }

            if before_snapshot.scenario_id != after_snapshot.scenario_id:
                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.INCONCLUSIVE,
                    VerificationReasonCode.EVIDENCE_CONFLICTING,
                    "The scenario identity changed during verification.",
                    evidence,
                )

            changed = before_snapshot != after_snapshot

            if execution_result.status == ExecutionStatus.NOT_EXECUTED:
                if not changed:
                    return self._action_result(
                        proposal.action_id,
                        VerificationStatus.VERIFIED_SUCCESS,
                        VerificationReasonCode.NO_CHANGE_CONFIRMED,
                        "Action was not executed; scenario state is unchanged.",
                        evidence,
                    )

                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.VERIFIED_FAILURE,
                    VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
                    "Scenario state changed even though the action was not executed.",
                    evidence,
                )

            if execution_result.status == ExecutionStatus.FAILED:
                if changed:
                    return self._action_result(
                        proposal.action_id,
                        VerificationStatus.VERIFIED_FAILURE,
                        VerificationReasonCode.UNEXPECTED_STATE_CHANGE,
                        "State changed despite the reported execution failure.",
                        evidence,
                    )

                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.VERIFIED_FAILURE,
                    VerificationReasonCode.OUTCOME_MISMATCH,
                    "The action failed and its expected outcome was not achieved.",
                    evidence,
                )

            transition_matches, observed_record = self._check_transition(
                proposal,
                before_snapshot,
                after_snapshot,
            )

            if transition_matches is None:
                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.INCONCLUSIVE,
                    VerificationReasonCode.EVIDENCE_MISSING,
                    "The verifier does not recognize this action or its arguments.",
                    evidence,
                )

            if not transition_matches:
                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.VERIFIED_FAILURE,
                    VerificationReasonCode.OUTCOME_MISMATCH,
                    "The observed state does not satisfy the expected action outcome.",
                    evidence,
                )

            if execution_result.result is None:
                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.INCONCLUSIVE,
                    VerificationReasonCode.EVIDENCE_MISSING,
                    "The execution result is missing its expected output.",
                    evidence,
                )

            reported_result = thaw_json_value(execution_result.result)
            observed_result = observed_record.model_dump(mode="json")

            if reported_result != observed_result:
                return self._action_result(
                    proposal.action_id,
                    VerificationStatus.INCONCLUSIVE,
                    VerificationReasonCode.EVIDENCE_CONFLICTING,
                    "The execution output conflicts with the observed simulator state.",
                    evidence,
                )

            return self._action_result(
                proposal.action_id,
                VerificationStatus.VERIFIED_SUCCESS,
                VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
                "Observed state and execution output match the expected outcome.",
                evidence,
            )

        except Exception:
            return self._action_result(
                proposal.action_id,
                VerificationStatus.INCONCLUSIVE,
                VerificationReasonCode.VERIFIER_ERROR,
                "An unexpected error prevented independent action verification.",
                None,
            )

    def verify_task(self) -> TaskVerificationResult:
        """Verify the overall task objective against current observed state."""

        try:
            snapshot = self._state.snapshot()
            objective = snapshot.objective
            order = snapshot.order
            support_case = snapshot.support_case

            refund_matches = (
                order.refunded_minor_units == objective.refund_minor_units
            )
            remaining_matches = (
                order.remaining_refundable_minor_units
                == objective.expected_remaining_minor_units
            )
            note_requirement_met = (
                not objective.require_case_note or bool(support_case.notes)
            )
            closure_requirement_met = (
                not objective.require_case_closed
                or support_case.status == CaseStatus.CLOSED
            )

            checks = {
                "refund_matches_objective": refund_matches,
                "remaining_balance_matches": remaining_matches,
                "required_case_note_exists": note_requirement_met,
                "required_case_is_closed": closure_requirement_met,
            }

            evidence = {
                "scenario_id": snapshot.scenario_id,
                "checks": checks,
                "observed_refunded_minor_units": order.refunded_minor_units,
                "expected_refund_minor_units": objective.refund_minor_units,
                "observed_remaining_minor_units": (
                    order.remaining_refundable_minor_units
                ),
                "expected_remaining_minor_units": (
                    objective.expected_remaining_minor_units
                ),
                "observed_case_status": support_case.status.value,
                "observed_case_note_count": len(support_case.notes),
            }

            if all(checks.values()):
                return self._task_result(
                    VerificationStatus.VERIFIED_SUCCESS,
                    VerificationReasonCode.OUTCOME_MATCHES_EXPECTED,
                    "All task objectives are satisfied by observed simulator state.",
                    evidence,
                )

            return self._task_result(
                VerificationStatus.VERIFIED_FAILURE,
                VerificationReasonCode.OUTCOME_MISMATCH,
                "One or more required task objectives remain unsatisfied.",
                evidence,
            )

        except Exception:
            return self._task_result(
                VerificationStatus.INCONCLUSIVE,
                VerificationReasonCode.VERIFIER_ERROR,
                "An unexpected error prevented independent task verification.",
                None,
            )

    def _check_transition(
        self,
        proposal: ActionProposal,
        before: ScenarioSnapshot,
        after: ScenarioSnapshot,
    ) -> tuple[bool | None, object | None]:
        """Check one tool's exact expected state transition."""

        arguments = thaw_json_value(proposal.arguments)

        if proposal.tool_name == "get_order":
            if set(arguments) != {"order_id"}:
                return None, None

            if arguments["order_id"] != before.order.order_id:
                return None, None

            return before == after, after.order

        if proposal.tool_name == "issue_refund":
            if set(arguments) != {"order_id", "amount_minor_units"}:
                return None, None

            order = before.order
            amount = arguments["amount_minor_units"]

            if (
                arguments["order_id"] != order.order_id
                or type(amount) is not int
                or amount <= 0
                or amount > order.remaining_refundable_minor_units
                or order.payment_status == PaymentStatus.UNPAID
            ):
                return None, None

            refunded_total = order.refunded_minor_units + amount
            expected_payment_status = (
                PaymentStatus.REFUNDED
                if refunded_total == order.total_minor_units
                else PaymentStatus.PARTIALLY_REFUNDED
            )

            expected = (
                after.order.order_id == order.order_id
                and after.order.status == order.status
                and after.order.currency == order.currency
                and after.order.total_minor_units == order.total_minor_units
                and after.order.refunded_minor_units == refunded_total
                and after.order.payment_status == expected_payment_status
                and after.support_case == before.support_case
                and after.objective == before.objective
            )

            return expected, after.order

        if proposal.tool_name == "add_case_note":
            if set(arguments) != {"case_id", "note"}:
                return None, None

            case = before.support_case
            note = arguments["note"]

            if (
                arguments["case_id"] != case.case_id
                or not isinstance(note, str)
                or not note.strip()
                or len(note) > 500
                or case.status != CaseStatus.OPEN
            ):
                return None, None

            expected_notes = (
                *case.notes,
                {
                    "sequence": len(case.notes) + 1,
                    "note": note,
                },
            )
            observed_notes = tuple(
                item.model_dump(mode="json")
                for item in after.support_case.notes
            )

            expected = (
                after.support_case.case_id == case.case_id
                and after.support_case.order_id == case.order_id
                and after.support_case.status == case.status
                and observed_notes == expected_notes
                and after.order == before.order
            )

            return expected, after.support_case

        if proposal.tool_name == "close_case":
            if set(arguments) != {"case_id"}:
                return None, None

            case = before.support_case

            if (
                arguments["case_id"] != case.case_id
                or case.status != CaseStatus.OPEN
                or before.order.refunded_minor_units <= 0
                or not case.notes
            ):
                return None, None

            expected = (
                after.support_case.case_id == case.case_id
                and after.support_case.order_id == case.order_id
                and after.support_case.status == CaseStatus.CLOSED
                and after.support_case.notes == case.notes
                and after.order == before.order
            )

            return expected, after.support_case

        return None, None

    def _action_result(
        self,
        action_id: str,
        status: VerificationStatus,
        reason_code: VerificationReasonCode,
        reason: str,
        evidence: dict[str, object] | None,
    ) -> VerificationResult:
        """Construct a validated action verification result."""

        return VerificationResult(
            action_id=action_id,
            status=status,
            reason_code=reason_code,
            reason=reason,
            evidence=evidence,
            verified_at=self._clock(),
        )

    def _task_result(
        self,
        status: VerificationStatus,
        reason_code: VerificationReasonCode,
        reason: str,
        evidence: dict[str, object] | None,
    ) -> TaskVerificationResult:
        """Construct a validated task verification result."""

        return TaskVerificationResult(
            status=status,
            reason_code=reason_code,
            reason=reason,
            evidence=evidence,
            verified_at=self._clock(),
        )
