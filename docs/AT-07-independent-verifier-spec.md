# AT-07: Independent Verifier Specification

## 1. Purpose

AT-07 implements an independent verification boundary for AgentTrax.

The verifier determines whether an executed action produced the expected
observable simulator-state transition and whether the scenario's explicit
task-level postconditions have been satisfied.

The verifier does not accept an agent's narrative, confidence, or
model-generated success claim as proof of completion.

A successful tool invocation is not, by itself, evidence that the user's
task succeeded.

## 2. Dependencies

- AT-02: Core contracts
- AT-03: Deterministic scenario simulator
- AT-05: Gated tool executor

AT-07 consumes the established proposal, execution, scenario snapshot,
and verification contracts. It does not replace the policy engine,
approval workflow, tool registry, or executor.

## 3. Scope

AT-07 includes:

- Independent inspection of simulator state before and after an action.
- Verification of the expected transition for each supported scenario tool.
- Reconciliation of observed state with the executor-reported result.
- Explicit handling of successful, failed, and non-executed actions.
- Action-level outcomes: verified success, verified failure, or inconclusive.
- Task-level evaluation against the scenario objective.
- Fail-closed handling of verifier errors and insufficient evidence.
- Tests for normal outcomes, inconsistent evidence, and failure paths.

AT-07 does not include:

- Real-world tool integrations or external side effects.
- Persistent verification storage.
- Model-generated verification decisions.
- Trace recording or lifecycle event aggregation.
- A general-purpose verification language for arbitrary scenarios.
- Changes to policy or approval decisions.

## 4. Package and implementation

Implementation:

- `agenttrax/verification/verifier.py`
- `agenttrax/verification/__init__.py`

Tests:

- `tests/verification/test_verifier.py`

Public service:

- `IndependentVerifier`

The verifier receives an `OrderSupportScenarioState` and an injectable
clock. It reads snapshots from the simulator and does not invoke tools
or mutate simulator state.

## 5. Verification contracts

AT-07 uses the contracts defined in `agenttrax/contracts/models.py`.

### 5.1 Action-level result

`VerificationResult` contains:

- `action_id`
- `status`
- `reason_code`
- `reason`
- optional structured `evidence`
- `verified_at`

The status is one of:

- `VERIFIED_SUCCESS`
- `VERIFIED_FAILURE`
- `INCONCLUSIVE`

The reason code explains the outcome:

| Status | Supported reason codes |
|---|---|
| VERIFIED_SUCCESS | OUTCOME_MATCHES_EXPECTED, NO_CHANGE_CONFIRMED |
| VERIFIED_FAILURE | OUTCOME_MISMATCH, UNEXPECTED_STATE_CHANGE |
| INCONCLUSIVE | EVIDENCE_MISSING, EVIDENCE_CONFLICTING, VERIFIER_ERROR |

Successful and failed action-level results require evidence. Verification
timestamps are timezone-aware and normalized to UTC.

### 5.2 Task-level result

`TaskVerificationResult` represents whether the scenario objective has
actually been achieved.

It contains:

- `status`
- `reason_code`
- `reason`
- optional structured `evidence`
- `verified_at`

Its successful status only permits `OUTCOME_MATCHES_EXPECTED`.

`NO_CHANGE_CONFIRMED` is deliberately not a valid task-level success
reason. An action that did not execute and left state unchanged may be
correctly classified at the action level, but that does not establish
completion of the user's task.

## 6. Action-level verification

The public method is:

`IndependentVerifier.verify_action(proposal, execution_result, before_snapshot)`

The verifier:

1. Validates the proposal, execution result, and supplied pre-execution
   snapshot.
2. Confirms that the proposal and execution result refer to the same
   action.
3. Captures the current simulator snapshot as the observed after-state.
4. Builds evidence containing the tool name, execution status, and
   before/after snapshots.
5. Checks scenario identity and the execution outcome.
6. Evaluates the expected transition for the supported tool.
7. Reconciles the observed state with the executor-reported result.
8. Returns an action-level verification result.

### 6.1 Supported scenario operations

The verifier independently checks the expected behavior of:

- `get_order`
- `issue_refund`
- `add_case_note`
- `close_case`

Each operation is checked against its expected arguments, relevant
preconditions, and exact state transition.

The checks include preservation of unrelated scenario state and
preservation of the scenario objective.

### 6.2 Successful execution

An execution result marked `SUCCEEDED` is not automatically verified.

The verifier checks that:

- The action is recognized and its arguments are valid for that operation.
- The observed after-state matches the expected transition.
- Unrelated state has not changed unexpectedly.
- The executor-reported result agrees with the independently observed
  result.

A transition mismatch produces `VERIFIED_FAILURE` with
`OUTCOME_MISMATCH`.

Missing evidence produces `INCONCLUSIVE` with `EVIDENCE_MISSING`.
Conflicting reported and observed evidence produces `INCONCLUSIVE` with
`EVIDENCE_CONFLICTING`.

Only a matching expected transition and consistent evidence produce
`VERIFIED_SUCCESS` with `OUTCOME_MATCHES_EXPECTED`.

### 6.3 Failed execution

For an execution result marked `FAILED`:

- No observed state change produces `VERIFIED_FAILURE` with
  `OUTCOME_MISMATCH`.
- An observed state change produces `VERIFIED_FAILURE` with
  `UNEXPECTED_STATE_CHANGE`.

A failed tool invocation cannot be promoted to verified success.

### 6.4 Non-executed actions

For an execution result marked `NOT_EXECUTED`:

- An unchanged state produces action-level `VERIFIED_SUCCESS` with
  `NO_CHANGE_CONFIRMED`.
- A changed state produces `VERIFIED_FAILURE` with
  `UNEXPECTED_STATE_CHANGE`.

This action-level classification records that the non-executed action
did not change simulator state. It does not mean the requested task
was completed.

### 6.5 Inconclusive outcomes and errors

The verifier returns `INCONCLUSIVE` when required evidence is missing,
conflicting, or cannot be evaluated.

Unexpected verification exceptions are converted to
`INCONCLUSIVE` with `VERIFIER_ERROR`. An exception must never produce
verified success.

A change in scenario identity is treated as conflicting evidence.

## 7. Task-level verification

The public method is:

`IndependentVerifier.verify_task()`

Task verification evaluates the current simulator snapshot against the
scenario's explicit `ScenarioObjective`.

For the order-support scenario, the verifier checks:

- The observed refunded amount equals the objective's required refund.
- The remaining refundable balance equals the expected remainder.
- A case note exists when a case note is required.
- The support case is closed when closure is required.

When every configured postcondition is satisfied, the result is
`VERIFIED_SUCCESS` with `OUTCOME_MATCHES_EXPECTED`.

When one or more postconditions are unmet, the result is
`VERIFIED_FAILURE` with `OUTCOME_MISMATCH`.

If the snapshot or verification process cannot be completed, the result
is `INCONCLUSIVE` with `VERIFIER_ERROR`.

Task-level success is based on the objective and observed state, not on
whether an individual tool call succeeded.

## 8. Evidence and trust boundaries

- The simulator snapshot is the source of observed state.
- Executor results are checked against observed state; they are not
  accepted as independent proof on their own.
- Agent-generated claims do not determine verification status.
- Action identifiers must remain linked between the proposal and
  execution result.
- Evidence is structured and stored in the immutable verification
  contracts.
- Missing or inconsistent evidence cannot be interpreted as success.

## 9. Determinism and safety

- Verification operates against the in-memory simulator.
- The verifier does not execute tools or cause external side effects.
- The clock is injectable for deterministic timestamp tests.
- Scenario transition checks are explicit and deterministic.
- Unexpected verifier failures fail closed.
- The verifier does not modify the observed scenario state.

## 10. Acceptance criteria

AT-07 is accepted when:

1. Model-generated claims cannot set verification status.
2. A successful tool result with an unmet postcondition cannot become
   verified task success.
3. Verifier errors cannot produce verified success.
4. Action-level verification covers successful, failed, and non-executed
   outcomes.
5. Missing and conflicting evidence produce inconclusive outcomes.
6. Supported scenario tools are checked against their expected state
   transitions.
7. Task-level verification checks the explicit scenario objective.
8. `NO_CHANGE_CONFIRMED` cannot count as task-level success.
9. Tests cover success, failure, inconclusive outcomes, and the
   task-level no-change distinction.
10. The full project test suite and Ruff checks pass.

## 11. Test coverage

AT-07 tests are located in:

`tests/verification/test_verifier.py`

Coverage includes:

- Successful verification for all four supported scenario tools.
- Non-executed actions with unchanged and unexpectedly changed state.
- Failed executions with unchanged and changed state.
- Successful tool execution with unmet postconditions.
- Conflicting, missing, and unrecognized action evidence.
- Unexpected verifier exceptions.
- Proposal/execution action identifier mismatch.
- Successful and unsuccessful task objective evaluation.
- Task snapshot errors.
- Prevention of task success from a no-change action.

## 12. Validation results

At documentation completion:

- Full project test suite: 514 passed.
- Project-wide Ruff: all checks passed.
- `git diff --check`: clean.

These results describe the validation run for the AT-07 implementation
before documentation changes.

## 13. Limitations

- Verification is specific to the deterministic order-support simulator.
- The verifier is in-memory and does not persist verification history.
- Task verification evaluates the current scenario objective; it is not
  a general multi-task aggregation or trace-finalization service.
- Trace recording and lifecycle aggregation remain separate feature work.
- No real-world action or external system is verified by this component.

## 14. Completion

AT-07 implementation and tests are complete. The independent verifier
provides action-level transition verification and task-level objective
verification, with explicit inconclusive outcomes and fail-closed error
handling.

Specification: `docs/AT-07-independent-verifier-spec.md`