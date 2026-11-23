"""Acceptance tests for the AgentTrax end-to-end showcase."""

from dataclasses import replace

import agenttrax.showcase as showcase
from agenttrax.tracing.recorder import TraceRecorder


def _event_types(report: showcase.ShowcaseReport, action_id: str) -> list[str]:
    return [
        event.event_type.value
        for event in report.trace_events
        if event.action_id == action_id
    ]


def _assert_order(actual: list[str], expected: tuple[str, ...]) -> None:
    previous_position = -1

    for event_type in expected:
        position = actual.index(event_type, previous_position + 1)
        previous_position = position


def test_showcase_completes_expected_task() -> None:
    report = showcase.run_showcase()

    assert report.passed is True
    assert len(report.actions) == 4
    assert report.task_verification.status.value == "VERIFIED_SUCCESS"

    assert report.final_snapshot.order.refunded_minor_units == 2_500
    assert report.final_snapshot.order.remaining_refundable_minor_units == 10_499
    assert report.final_snapshot.support_case.status.value == "CLOSED"
    assert report.final_snapshot.support_case.notes


def test_blocked_action_is_skipped_and_verified_without_execution() -> None:
    report = showcase.run_showcase()
    blocked = report.actions[0]

    assert blocked.policy_decision == "BLOCK"
    assert blocked.execution_status == "NOT_EXECUTED"
    assert blocked.verification_status == "VERIFIED_SUCCESS"
    assert blocked.state_change == "NONE"

    event_types = _event_types(report, "act-showcase-001")

    assert "EXECUTION_STARTED" not in event_types
    assert event_types.count("EXECUTION_SKIPPED") == 1
    _assert_order(
        event_types,
        ("EXECUTION_SKIPPED", "VERIFICATION_COMPLETED"),
    )


def test_approved_refund_has_complete_ordered_lifecycle() -> None:
    report = showcase.run_showcase()
    refund = report.actions[1]

    assert refund.policy_decision == "REQUIRE_APPROVAL"
    assert refund.approval_status == "GRANTED"
    assert refund.execution_status == "SUCCEEDED"
    assert refund.verification_status == "VERIFIED_SUCCESS"

    event_types = _event_types(report, "act-showcase-002")

    _assert_order(
        event_types,
        (
            "APPROVAL_REQUESTED",
            "APPROVAL_GRANTED",
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )

    assert event_types.count("EXECUTION_STARTED") == 1
    assert event_types.count("EXECUTION_SUCCEEDED") == 1


def test_note_and_case_closure_are_executed_and_verified() -> None:
    report = showcase.run_showcase()

    assert report.actions[2].policy_decision == "ALLOW"
    assert report.actions[2].execution_status == "SUCCEEDED"
    assert report.actions[2].verification_status == "VERIFIED_SUCCESS"

    assert report.actions[3].policy_decision == "ALLOW"
    assert report.actions[3].execution_status == "SUCCEEDED"
    assert report.actions[3].verification_status == "VERIFIED_SUCCESS"

    _assert_order(
        _event_types(report, "act-showcase-003"),
        (
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )

    _assert_order(
        _event_types(report, "act-showcase-004"),
        (
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "VERIFICATION_COMPLETED",
        ),
    )


def test_task_verification_is_recorded_separately() -> None:
    report = showcase.run_showcase()

    assert report.task_verification.status.value == "VERIFIED_SUCCESS"
    assert any(
        event.action_id is None
        and event.event_type.value == "VERIFICATION_COMPLETED"
        for event in report.trace_events
    )


def test_replay_is_semantically_deterministic() -> None:
    first = showcase.run_showcase()
    second = showcase.run_showcase()

    assert first.normalized() == second.normalized()


def test_each_run_starts_with_fresh_scenario_state() -> None:
    first = showcase.run_showcase()
    second = showcase.run_showcase()

    assert first.final_snapshot == second.final_snapshot
    assert first.final_snapshot.order.refunded_minor_units == 2_500
    assert second.final_snapshot.order.refunded_minor_units == 2_500
    assert first.final_snapshot.support_case.status.value == "CLOSED"
    assert second.final_snapshot.support_case.status.value == "CLOSED"


def test_unverified_action_outcome_causes_showcase_failure(
    monkeypatch,
) -> None:
    original_action_report = showcase._action_report
    calls = 0

    def report_with_inconclusive_first_action(*args, **kwargs):
        nonlocal calls
        action = original_action_report(*args, **kwargs)
        calls += 1

        if calls == 1:
            return replace(action, verification_status="INCONCLUSIVE")

        return action

    monkeypatch.setattr(
        showcase,
        "_action_report",
        report_with_inconclusive_first_action,
    )

    report = showcase.run_showcase()

    assert report.actions[0].verification_status == "INCONCLUSIVE"
    assert report.passed is False


def test_cli_returns_nonzero_and_reports_failure(monkeypatch, capsys) -> None:
    successful_report = showcase.run_showcase()
    failed_report = replace(successful_report, passed=False)

    monkeypatch.setattr(
        showcase,
        "run_showcase",
        lambda: failed_report,
    )

    exit_code = showcase.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "SHOWCASE RESULT: FAIL" in output


def test_showcase_fails_when_proposal_trace_is_missing(monkeypatch) -> None:
    original_record_proposal = TraceRecorder.record_proposal

    def skip_proposal_recording(self, proposal):
        if proposal.action_id == "act-showcase-001":
            return None
        return original_record_proposal(self, proposal)

    monkeypatch.setattr(
        TraceRecorder,
        "record_proposal",
        skip_proposal_recording,
    )

    report = showcase.run_showcase()

    assert report.passed is False


def test_showcase_fails_when_lifecycle_event_is_duplicated(
    monkeypatch,
) -> None:
    original_record_proposal = TraceRecorder.record_proposal

    def duplicate_first_proposal(self, proposal):
        event = original_record_proposal(self, proposal)

        if proposal.action_id == "act-showcase-001":
            original_record_proposal(self, proposal)

        return event

    monkeypatch.setattr(
        TraceRecorder,
        "record_proposal",
        duplicate_first_proposal,
    )

    report = showcase.run_showcase()

    assert report.passed is False


def test_showcase_fails_when_task_verification_is_misassociated(
    monkeypatch,
) -> None:
    original_record_task_verification = (
        TraceRecorder.record_task_verification
    )

    def record_under_wrong_task(self, task_id, verification):
        return original_record_task_verification(
            self,
            "incorrect-task-id",
            verification,
        )

    monkeypatch.setattr(
        TraceRecorder,
        "record_task_verification",
        record_under_wrong_task,
    )

    report = showcase.run_showcase()

    assert report.passed is False
