# AT-09: End-to-End Showcase Specification

## 1. Objective

Provide one repeatable, offline CLI scenario demonstrating the complete
AgentTrax safety lifecycle: policy evaluation, gated execution, approval,
independent action verification, task-level verification, and trace recording.

The showcase demonstrates both a blocked action and an approval-required
action, followed by successful completion of the scenario objective.

## 2. Scope

### Included

- A single deterministic order-support scenario.
- A deliberately blocked refund proposal.
- A valid refund requiring explicit approval.
- Successful support-case note creation and case closure.
- Independent verification of each action.
- Independent task-level objective verification.
- Lifecycle recording through the AT-08 TraceRecorder.
- A CLI entry point runnable with `python -m agenttrax.showcase`.
- Automated acceptance tests for outcomes, ordering, replay, isolation,
  and failure reporting.

### Excluded

- External APIs, databases, or persistent trace storage.
- Real-world order-management integrations or side effects.
- A web dashboard or HTTP endpoint.
- A real human approval integration.
- Model-provider integration or nondeterministic agent planning.
- Changes to existing policy, executor, approval, verifier, or recorder
  security boundaries.

## 3. Implementation Structure

```text
agenttrax/
    showcase.py

tests/
    test_showcase.py

docs/
    AT-09-showcase-spec.md
```

The showcase composes the existing scenario state, gated executor,
independent verifier, and trace recorder. It does not replace their
responsibilities or bypass their public interfaces.

## 4. Scenario Definition

Scenario ID: `order_refund_support_v1`

Task ID: `task-showcase-001`

The scenario starts from a fresh order-support simulator state.

The initial order has a total of 12,999 minor currency units, is paid,
and has no previous refund.

The objective is to:

- Refund 2,500 minor currency units.
- Leave 10,499 minor currency units unrefunded.
- Add the required support-case note.
- Close the support case.

The expected final refund is 25.00 USD, with 104.99 USD remaining.

## 5. Action Sequence

### Action 1: Blocked refund

Propose a refund of 13,000 minor currency units, exceeding the
available refundable balance.

Expected behavior:

- Policy decision: `BLOCK`.
- Execution status: `NOT_EXECUTED`.
- Not-executed reason: policy blocked.
- No execution-start event.
- Simulator state remains unchanged.
- Independent action verification confirms no change.

A `VERIFIED_SUCCESS` action result here means the expected no-change
condition was confirmed. It does not mean the task objective succeeded.

### Action 2: Approval-required refund

Propose the valid refund of 2,500 minor currency units.

Expected behavior:

- Policy decision: `REQUIRE_APPROVAL`.
- Approval request is recorded.
- Explicit approval is obtained through the existing approval service.
- Approved execution succeeds.
- Independent action verification confirms the expected state transition.

### Action 3: Support-case note

Propose and execute the required support-case note operation.

Expected behavior:

- Policy decision: `ALLOW`.
- Execution status: `SUCCEEDED`.
- Independent verification confirms the note was added.

### Action 4: Close support case

Propose and execute the case-closure operation.

Expected behavior:

- Policy decision: `ALLOW`.
- Execution status: `SUCCEEDED`.
- Independent verification confirms the case is closed.

### Task-level verification

After the action sequence, the independent verifier evaluates the
scenario objective against observed simulator state.

Expected result: `VERIFIED_SUCCESS`.

The task result is recorded separately from action-level verification.

## 6. Determinism and Isolation

Every invocation creates fresh instances of:

- `OrderSupportScenarioState`
- `GatedToolExecutor`
- `IndependentVerifier`
- `TraceRecorder`

The components use a shared fixed, timezone-aware UTC clock.

Task and action identifiers, tool arguments, and trace event ID generation
are deterministic.

The approval service may generate a random approval UUID. Generated
identifiers and timestamps are excluded from semantic replay comparison.

Replay comparison evaluates semantic action outcomes, policy decisions,
execution and verification statuses, final simulator state, and trace
event ordering.

Each invocation begins with fresh simulator state; one run must not
contaminate another.

## 7. Trace Requirements

The showcase records actual lifecycle outcomes using the existing
AT-08 recorder.

The trace must distinguish:

- Proposal creation.
- Policy decisions.
- Approval requested and granted.
- Execution started.
- Execution succeeded or skipped.
- Action-level verification.
- Task-level verification.

The blocked action must not produce `EXECUTION_STARTED`.

The approval-required refund must preserve this lifecycle order:

1. `APPROVAL_REQUESTED`
2. `APPROVAL_GRANTED`
3. `EXECUTION_STARTED`
4. `EXECUTION_SUCCEEDED`
5. `VERIFICATION_COMPLETED`

The support note and case closure must each record execution and
subsequent action verification.

Task verification must be recorded as a separate event without an
action ID.

The showcase must not invent lifecycle events or infer success from
policy decisions.

## 8. Output and Failure Semantics

Run the showcase:

```powershell
python -m agenttrax.showcase
```

The CLI reports each action's policy decision, execution status,
verification status, and state-change outcome.

It also reports task-level verification, final state, trace event count,
and the overall showcase result.

The process returns:

- Exit code `0` when all required semantic and lifecycle checks pass.
- Exit code `1` when the showcase does not satisfy its required checks.

A failed or inconclusive action verification must not be presented as
successful task completion.

The output must reflect actual component results rather than a
hard-coded success message.

## 9. Acceptance Criteria

1. One documented CLI command runs the complete showcase.
2. The blocked refund is rejected and never starts execution.
3. The blocked action's unchanged state is independently verified.
4. The valid refund requires approval before execution.
5. The approved refund executes and is independently verified.
6. The support note and case closure execute and are independently verified.
7. Task-level verification is recorded separately.
8. The final simulator state satisfies every scenario objective.
9. Trace lifecycle events are present and correctly ordered.
10. Replay produces equivalent semantic results.
11. Each invocation starts with fresh simulator state.
12. An invalid or inconclusive outcome causes the showcase to fail honestly.
13. The CLI returns a nonzero exit code when the showcase fails.
14. The complete test suite, project-wide Ruff checks, and Git diff
    whitespace validation pass.

## 10. Automated Tests

`tests/test_showcase.py` covers:

- Successful completion of the expected task.
- Blocked action behavior and absence of execution.
- Approval lifecycle ordering.
- Support note and case closure execution and verification.
- Separate task-level verification recording.
- Semantic replay determinism.
- Fresh state isolation between runs.
- Failure when an action verification is inconclusive.
- Nonzero CLI exit behavior when the showcase fails.

## 11. Validation

Run targeted acceptance tests:

```powershell
python -m pytest -p no:cacheprovider tests/test_showcase.py -q
```

Run the complete suite:

```powershell
python -m pytest -p no:cacheprovider -q
```

Run project-wide lint and whitespace validation:

```powershell
python -m ruff check .
git diff --check
```

Run the showcase:

```powershell
python -m agenttrax.showcase
```

## 12. Implementation Boundary

AT-09 is a CLI composition of the completed AT-03 through AT-08
components.

It introduces no new policy permissions, execution bypasses,
approval semantics, verification rules, or trace event types.

The MVP remains local, deterministic, offline, and simulator-only.