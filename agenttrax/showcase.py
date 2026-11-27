"""Repeatable end-to-end AgentTrax showcase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agenttrax.contracts.models import ActionProposal
from agenttrax.execution.executor import GatedToolExecutor
from agenttrax.scenarios.state import OrderSupportScenarioState
from agenttrax.tracing.recorder import TraceRecorder
from agenttrax.verification.verifier import IndependentVerifier

TASK_ID = "task-showcase-001"
REQUESTED_BY = "showcase-agent"
FIXED_TIME = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return FIXED_TIME


@dataclass(frozen=True)
class ShowcaseAction:
    """Observed lifecycle outcomes for one showcase action."""

    name: str
    action_id: str
    policy_decision: str
    execution_status: str
    verification_status: str
    state_change: str
    approval_status: str | None = None


@dataclass(frozen=True)
class ShowcaseReport:
    """Actual outcomes from one complete showcase run."""

    scenario_id: str
    actions: tuple[ShowcaseAction, ...]
    task_verification: Any
    final_snapshot: Any
    trace_events: tuple[Any, ...]
    passed: bool

    def normalized(self) -> dict[str, object]:
        """Return deterministic semantic results without generated IDs or times."""
        return {
            "scenario_id": self.scenario_id,
            "actions": [
                {
                    "name": action.name,
                    "policy_decision": action.policy_decision,
                    "execution_status": action.execution_status,
                    "verification_status": action.verification_status,
                    "state_change": action.state_change,
                    "approval_status": action.approval_status,
                }
                for action in self.actions
            ],
            "task_verification": self.task_verification.status.value,
            "final_state": {
                "refund_minor_units": (
                    self.final_snapshot.order.refunded_minor_units
                ),
                "remaining_minor_units": (
                    self.final_snapshot.order.remaining_refundable_minor_units
                ),
                "case_status": self.final_snapshot.support_case.status.value,
                "case_notes": list(self.final_snapshot.support_case.notes),
            },
            "trace": [
                {
                    "action_id": event.action_id,
                    "event_type": event.event_type.value,
                }
                for event in self.trace_events
            ],
            "passed": self.passed,
        }


def _proposal(
    *,
    action_id: str,
    tool_name: str,
    arguments: dict[str, object],
) -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        task_id=TASK_ID,
        tool_name=tool_name,
        arguments=arguments,
        requested_by=REQUESTED_BY,
        created_at=FIXED_TIME,
    )


def _action_report(
    *,
    name: str,
    proposal: ActionProposal,
    decision: Any,
    result: Any,
    verification: Any,
    before_snapshot: Any,
    after_snapshot: Any,
    approval_status: str | None = None,
) -> ShowcaseAction:
    return ShowcaseAction(
        name=name,
        action_id=proposal.action_id,
        policy_decision=decision.decision.value,
        execution_status=result.status.value,
        verification_status=verification.status.value,
        state_change=(
            "NONE" if before_snapshot == after_snapshot else "CHANGED"
        ),
        approval_status=approval_status,
    )


def run_showcase() -> ShowcaseReport:
    """Run the blocked, approval-required, and successful task paths."""
    state = OrderSupportScenarioState()
    executor = GatedToolExecutor(state=state, clock=_fixed_clock)
    verifier = IndependentVerifier(state=state, clock=_fixed_clock)

    event_ids = iter(range(1, 1000))
    recorder = TraceRecorder(
        clock=_fixed_clock,
        id_factory=lambda: f"showcase-event-{next(event_ids):04d}",
    )

    initial_snapshot = state.snapshot()
    order_id = initial_snapshot.order.order_id
    case_id = initial_snapshot.support_case.case_id

    actions: list[ShowcaseAction] = []

    # 1. Deliberately blocked: the requested refund exceeds the balance.
    blocked = _proposal(
        action_id="act-showcase-001",
        tool_name="issue_refund",
        arguments={
            "order_id": order_id,
            "amount_minor_units": (
                initial_snapshot.order.remaining_refundable_minor_units + 1
            ),
        },
    )
    recorder.record_proposal(blocked)
    blocked_decision = executor.policy_engine.evaluate(
        blocked, state.snapshot()
    )
    recorder.record_policy_decision(blocked, blocked_decision)

    blocked_before = state.snapshot()
    blocked_result = executor.execute(blocked, blocked_decision)
    recorder.record_execution_result(blocked, blocked_decision, blocked_result)

    blocked_verification = verifier.verify_action(
        blocked, blocked_result, blocked_before
    )
    recorder.record_action_verification(
        blocked, blocked_decision, blocked_result, blocked_verification
    )

    actions.append(
        _action_report(
            name="BLOCKED REFUND",
            proposal=blocked,
            decision=blocked_decision,
            result=blocked_result,
            verification=blocked_verification,
            before_snapshot=blocked_before,
            after_snapshot=state.snapshot(),
        )
    )

    # 2. Valid refund: policy requires approval before execution.
    refund = _proposal(
        action_id="act-showcase-002",
        tool_name="issue_refund",
        arguments={
            "order_id": order_id,
            "amount_minor_units": 2_500,
        },
    )
    recorder.record_proposal(refund)
    refund_decision = executor.policy_engine.evaluate(refund, state.snapshot())
    recorder.record_policy_decision(refund, refund_decision)

    approval_id = executor.request_approval(refund, refund_decision)
    recorder.record_approval_requested(
        refund, refund_decision, approval_id
    )

    approval_evidence = executor.approve(
        approval_id, approver_id="showcase-reviewer"
    )
    recorder.record_approval_granted(refund, approval_evidence)

    refund_before = state.snapshot()
    recorder.record_execution_started(
        refund, refund_decision, approval_evidence
    )
    refund_result = executor.execute_approved(approval_id)
    recorder.record_execution_result(
        refund, refund_decision, refund_result, approval_evidence
    )

    refund_verification = verifier.verify_action(
        refund, refund_result, refund_before
    )
    recorder.record_action_verification(
        refund,
        refund_decision,
        refund_result,
        refund_verification,
        approval_evidence,
    )

    actions.append(
        _action_report(
            name="APPROVED REFUND",
            proposal=refund,
            decision=refund_decision,
            result=refund_result,
            verification=refund_verification,
            before_snapshot=refund_before,
            after_snapshot=state.snapshot(),
            approval_status="GRANTED",
        )
    )

    # 3. Add the required support-case note.
    note = _proposal(
        action_id="act-showcase-003",
        tool_name="add_case_note",
        arguments={
            "case_id": case_id,
            "note": "Refund of USD 25.00 processed and verified.",
        },
    )
    recorder.record_proposal(note)
    note_decision = executor.policy_engine.evaluate(note, state.snapshot())
    recorder.record_policy_decision(note, note_decision)

    note_before = state.snapshot()
    if note_decision.decision.value == "ALLOW":
        recorder.record_execution_started(note, note_decision)

    note_result = executor.execute(note, note_decision)
    recorder.record_execution_result(note, note_decision, note_result)

    note_verification = verifier.verify_action(
        note, note_result, note_before
    )
    recorder.record_action_verification(
        note, note_decision, note_result, note_verification
    )

    actions.append(
        _action_report(
            name="SUPPORT CASE NOTE",
            proposal=note,
            decision=note_decision,
            result=note_result,
            verification=note_verification,
            before_snapshot=note_before,
            after_snapshot=state.snapshot(),
        )
    )

    # 4. Close the case after the refund and note.
    close = _proposal(
        action_id="act-showcase-004",
        tool_name="close_case",
        arguments={"case_id": case_id},
    )
    recorder.record_proposal(close)
    close_decision = executor.policy_engine.evaluate(close, state.snapshot())
    recorder.record_policy_decision(close, close_decision)

    close_before = state.snapshot()
    if close_decision.decision.value == "ALLOW":
        recorder.record_execution_started(close, close_decision)

    close_result = executor.execute(close, close_decision)
    recorder.record_execution_result(close, close_decision, close_result)

    close_verification = verifier.verify_action(
        close, close_result, close_before
    )
    recorder.record_action_verification(
        close, close_decision, close_result, close_verification
    )

    actions.append(
        _action_report(
            name="CLOSE SUPPORT CASE",
            proposal=close,
            decision=close_decision,
            result=close_result,
            verification=close_verification,
            before_snapshot=close_before,
            after_snapshot=state.snapshot(),
        )
    )

    # 5. Independently verify the overall task objective.
    task_verification = verifier.verify_task()
    recorder.record_task_verification(TASK_ID, task_verification)

    final_snapshot = state.snapshot()

    final_state_valid = (
        final_snapshot.order.refunded_minor_units == 2_500
        and final_snapshot.order.remaining_refundable_minor_units == 10_499
        and final_snapshot.support_case.status.value == "CLOSED"
        and bool(final_snapshot.support_case.notes)
    )

    events = tuple(recorder.get_events())


    def action_events(action_id: str):
        return tuple(
            event
            for event in events
            if event.action_id == action_id
        )

    def action_trace_valid(
        action_id: str,
        expected_types: tuple[str, ...],
    ) -> bool:
        recorded_events = action_events(action_id)

        actual_types = tuple(
            event.event_type.value
            for event in recorded_events
        )

        return (
            len(recorded_events) == len(expected_types)
            and actual_types == expected_types
            and all(event.task_id == TASK_ID for event in recorded_events)
            and all(
                event.details.get("verification_scope") == "ACTION"
                for event in recorded_events
                if event.event_type.value == "VERIFICATION_COMPLETED"
            )
        )

    blocked_trace_valid = action_trace_valid(
        "act-showcase-001",
        (
            "PROPOSAL_CREATED",
            "POLICY_DECIDED",
            "EXECUTION_SKIPPED",
            "VERIFICATION_COMPLETED",
        ),
    )

    refund_trace_valid = action_trace_valid(
        "act-showcase-002",
        (
            "PROPOSAL_CREATED",
            "POLICY_DECIDED",
            "APPROVAL_REQUESTED",
            "APPROVAL_GRANTED",
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )

    note_trace_valid = action_trace_valid(
        "act-showcase-003",
        (
            "PROPOSAL_CREATED",
            "POLICY_DECIDED",
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )

    close_trace_valid = action_trace_valid(
        "act-showcase-004",
        (
            "PROPOSAL_CREATED",
            "POLICY_DECIDED",
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )

    task_verification_events = tuple(
        event
        for event in events
        if event.action_id is None
    )

    task_trace_valid = (
        len(task_verification_events) == 1
        and task_verification_events[0].task_id == TASK_ID
        and task_verification_events[0].event_type.value
        == "VERIFICATION_COMPLETED"
        and task_verification_events[0].details.get("verification_scope")
        == "TASK"
        and task_verification_events[0].details.get("verification_status")
        == task_verification.status.value
    )

    expected_action_ids = {
        "act-showcase-001",
        "act-showcase-002",
        "act-showcase-003",
        "act-showcase-004",
    }

    trace_events_valid = (
        len(events) == 22
        and all(
            event.action_id is None or event.action_id in expected_action_ids
            for event in events
        )
    )

    expected = (
        len(actions) == 4
        and actions[0].policy_decision == "BLOCK"
        and actions[0].execution_status == "NOT_EXECUTED"
        and actions[0].verification_status == "VERIFIED_SUCCESS"
        and actions[0].state_change == "NONE"
        and actions[1].policy_decision == "REQUIRE_APPROVAL"
        and actions[1].approval_status == "GRANTED"
        and actions[1].execution_status == "SUCCEEDED"
        and actions[1].verification_status == "VERIFIED_SUCCESS"
        and actions[2].policy_decision == "ALLOW"
        and actions[2].execution_status == "SUCCEEDED"
        and actions[2].verification_status == "VERIFIED_SUCCESS"
        and actions[3].policy_decision == "ALLOW"
        and actions[3].execution_status == "SUCCEEDED"
        and actions[3].verification_status == "VERIFIED_SUCCESS"
        and task_verification.status.value == "VERIFIED_SUCCESS"
        and final_state_valid
        and trace_events_valid
        and blocked_trace_valid
        and refund_trace_valid
        and note_trace_valid
        and close_trace_valid
        and task_trace_valid
    )

    return ShowcaseReport(
        scenario_id=final_snapshot.scenario_id,
        actions=tuple(actions),
        task_verification=task_verification,
        final_snapshot=final_snapshot,
        trace_events=events,
        passed=expected,
    )


def main() -> int:
    """Run the showcase and print its observed outcomes."""
    report = run_showcase()

    print("AGENTTRAX SHOWCASE")
    print(f"Scenario: {report.scenario_id}")

    for index, action in enumerate(report.actions, start=1):
        approval = (
            f", approval {action.approval_status}"
            if action.approval_status is not None
            else ""
        )
        print(
            f"[{index}] {action.name}: "
            f"policy {action.policy_decision}, "
            f"execution {action.execution_status}, "
            f"verification {action.verification_status}, "
            f"state change {action.state_change}{approval}"
        )

    print(
        "TASK VERIFICATION: "
        f"{report.task_verification.status.value}"
    )

    order = report.final_snapshot.order
    support_case = report.final_snapshot.support_case
    print(
        "Final state: "
        f"refund {order.refunded_minor_units / 100:.2f} "
        f"{order.currency}, "
        f"remaining {order.remaining_refundable_minor_units / 100:.2f} "
        f"{order.currency}, "
        f"case {support_case.status.value}"
    )
    print(f"Trace events recorded: {len(report.trace_events)}")
    print(f"SHOWCASE RESULT: {'PASS' if report.passed else 'FAIL'}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())