# AT-08: Trace Recorder Specification

## 1. Objective

Implement an in-memory trace recorder that captures correlated AgentTrax lifecycle events from proposals through policy decisions, approvals, executions, and verification.

The recorder provides an ordered, auditable account of what actually happened. It must not infer execution or verification outcomes from proposals or policy decisions.

## 2. Scope

### Included

- Record proposal creation.
- Record policy decisions.
- Record approval requests, grants, denials, and expirations.
- Record explicit execution-start notifications.
- Record execution results.
- Record action-level verification results.
- Record task-level verification results.
- Correlate events by task and action identifiers.
- Redact sensitive values using the existing contract sanitizer.
- Provide immutable event snapshots and task-specific event retrieval.
- Support deterministic tests through an injectable clock and event-ID factory.
- Provide a thread-safe in-memory implementation.

### Excluded

- SQLite or other persistent storage.
- REST APIs or external logging services.
- Dashboards or user interfaces.
- Changes to executor, approval-service, policy-engine, or verifier behavior.
- Inference of lifecycle events that were not explicitly reported.

## 3. Package Structure

```text
agenttrax/
├── contracts/
│   └── tracing.py
└── tracing/
    ├── __init__.py
    └── recorder.py

tests/
└── tracing/
    └── test_recorder.py
```

The existing `agenttrax/contracts/tracing.py` remains the authoritative source for trace event contracts and detail sanitization.

## 4. Public API

The `TraceRecorder` exposes:

- `record_proposal(proposal)`
- `record_policy_decision(proposal, decision)`
- `record_approval_requested(proposal, decision, approval_id)`
- `record_approval_granted(proposal, evidence)`
- `record_approval_denied(proposal, decision, approval_id)`
- `record_approval_expired(proposal, decision, approval_id)`
- `record_execution_started(proposal, decision, approval_evidence=None)`
- `record_execution_result(proposal, decision, result, approval_evidence=None)`
- `record_action_verification(proposal, decision, result, verification, approval_evidence=None)`
- `record_task_verification(task_id, verification)`
- `get_events()`
- `get_task_events(task_id)`
- `reset()`

The recorder accepts an injectable clock and event-ID factory for deterministic testing.

## 5. Event Mapping

| Reported occurrence | Trace event |
|---|---|
| Proposal recorded | PROPOSAL_CREATED |
| Policy decision recorded | POLICY_DECIDED |
| Approval requested | APPROVAL_REQUESTED |
| Approval granted | APPROVAL_GRANTED |
| Approval denied | APPROVAL_DENIED |
| Approval expired | APPROVAL_EXPIRED |
| Execution explicitly started | EXECUTION_STARTED |
| ExecutionResult SUCCEEDED | EXECUTION_SUCCEEDED |
| ExecutionResult FAILED | EXECUTION_FAILED |
| ExecutionResult NOT_EXECUTED | EXECUTION_SKIPPED |
| Action verification recorded | VERIFICATION_COMPLETED, scope ACTION |
| Task verification recorded | VERIFICATION_COMPLETED, scope TASK |

Approval events must represent actual approval-service outcomes. An approval request must not be represented as a grant, and an approval decision must not be represented as an execution.

There is no APPROVAL_CONSUMED event in the existing event contract. The recorder must not invent one.

## 6. Correlation and Lifecycle Integrity

- Every event must include a task ID.
- Events associated with an action must include its action ID.
- Proposal, decision, execution, and action-verification records must be correlated.
- Proposal digests must be validated where applicable.
- Execution and action-verification records must respect the existing lifecycle consistency checker.
- Task verification uses an explicit task ID and has no action ID.
- A task-level verification event must reflect the verifier's actual result.

A proposal is not an execution. A policy ALLOW decision is not proof that execution occurred. An action-level no-change confirmation is not proof that the task objective was completed.

## 7. Execution and Verification Semantics

Execution results are mapped from their actual `ExecutionStatus`:

- SUCCEEDED becomes EXECUTION_SUCCEEDED.
- FAILED becomes EXECUTION_FAILED.
- NOT_EXECUTED becomes EXECUTION_SKIPPED.

Action verification and task verification remain distinct through the `verification_scope` detail:

- ACTION for `VerificationResult`.
- TASK for `TaskVerificationResult`.

The recorder must never label a task as verified successfully unless the task verifier explicitly reports success.

## 8. Redaction and Data Minimization

- Call the existing `sanitize_details()` function before constructing a `TraceEvent`.
- Do not mutate caller-owned data.
- Do not dump raw proposal arguments or complete evidence objects into trace details.
- Record only the minimal metadata needed to understand and correlate lifecycle events.
- Preserve the existing sanitizer's behavior and limits.
- Do not rely on the sanitizer to detect secrets embedded in arbitrary free-text values. Avoid recording unrestricted free-text reasons.

## 9. Ordering, Thread Safety, and Snapshots

- Maintain one recorder-wide monotonically increasing sequence.
- Sequence reflects successful recording order, not timestamp order.
- Failed records must not consume a sequence number.
- Protect recording and reset operations with a lock.
- Return immutable tuple snapshots from retrieval methods.
- `reset()` clears recorded events and resets the sequence while retaining the configured clock and ID factory.
- Event timestamps must be timezone-aware and normalized to UTC.
- Event IDs must be nonblank.

## 10. Acceptance Criteria

1. Event ordering is deterministic under an injected clock and ID factory.
2. Events are correlated to the correct task and action.
3. Invalid proposal, decision, digest, execution, and verification relationships are rejected.
4. Approval events represent actual approval outcomes.
5. Execution event types accurately reflect `ExecutionResult.status`.
6. Action and task verification are distinguishable.
7. Sensitive-key values are redacted through the existing sanitizer.
8. Caller-owned data is not mutated.
9. Returned event collections are immutable snapshots.
10. Concurrent recording preserves unique, monotonically increasing sequence numbers.
11. Failed records do not append events or consume sequence numbers.
12. Reset clears events and sequence state without replacing the configured dependencies.
13. The full existing test suite and Ruff checks pass.

## 11. Validation

Run the targeted tests:

```powershell
python -m pytest -p no:cacheprovider tests/tracing/test_recorder.py -q
```

Run the complete test suite:

```powershell
python -m pytest -p no:cacheprovider -q
```

Run lint and whitespace checks:

```powershell
python -m ruff check .
git diff --check
```

## 12. Implementation Boundary

AT-08 adds an independent in-memory trace recorder. It does not introduce tracing hooks into the executor, approval service, or verifier. The caller is responsible for reporting actual lifecycle outcomes to the recorder.