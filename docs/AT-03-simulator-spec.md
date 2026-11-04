# AgentTrax AT-03: Deterministic Scenario Simulator

Status: **Completed; final review passed.**

## 1. Purpose

AT-03 implements one deterministic, in-memory business scenario for
AgentTrax. It provides a controlled environment in which later features
can evaluate policies, execute permitted actions, and independently
verify task outcomes.

The implementation is simulator-only. It does not connect to real
orders, payment providers, customer accounts, external services, or
production systems.

## 2. Scope

### Included

- One simulated order-support scenario.
- Immutable, validated scenario data models.
- Deterministic initial state and reset behavior.
- Four explicitly registered simulator operations.
- Argument validation and business-rule rejection.
- In-memory state mutation only.
- Unit tests for models, state, operations, and registry behavior.

### Excluded

- Policy evaluation (`ALLOW`, `BLOCK`, `REQUIRE_APPROVAL`).
- Approval creation, resolution, expiry, or replay protection.
- A gated execution service or public agent execution gateway.
- Independent task verification.
- Lifecycle tracing or persistent storage.
- API routes, UI, model providers, and external integrations.

These responsibilities remain assigned to their respective later
features in `feature-registry.md`.

## 3. Scenario definition

**Scenario ID:** `order_refund_support_v1`

The scenario represents a support agent handling a refund request.

### Initial order

| Field | Initial value |
|---|---|
| Order ID | `ord_demo_001` |
| Order status | `DELIVERED` |
| Payment status | `PAID` |
| Currency | `USD` |
| Total | 12,999 minor units ($129.99) |
| Refunded | 0 minor units |
| Remaining refundable balance | 12,999 minor units |

### Initial support case

| Field | Initial value |
|---|---|
| Case ID | `case_demo_001` |
| Associated order | `ord_demo_001` |
| Status | `OPEN` |
| Notes | Empty |

### Scenario objective

The intended demonstration outcome is:

1. Add at least one support-case note.
2. Issue a simulated refund of 2,500 minor units ($25.00).
3. Close the support case.

Expected resulting state:

- Refunded amount: 2,500 minor units.
- Remaining refundable balance: 10,499 minor units ($104.99).
- Support case status: `CLOSED`.
- At least one support-case note exists.

The objective is scenario metadata. It does not itself establish that
the task has been independently verified. That responsibility belongs
to AT-07.

## 4. Data models

The scenario models are defined in `agenttrax/scenarios/models.py`.

They use the existing strict contract foundation from AT-02 and enforce
validation, immutability, and explicit state representations.

The models include:

- `SimulatedOrder`
- `CaseNote`
- `SupportCase`
- `ScenarioObjective`
- `ScenarioSnapshot`

The scenario also defines explicit order, payment, and case status
enums.

Important validation rules include:

- Identifiers must not be blank.
- Currency must use a three-letter uppercase code.
- Monetary amounts are represented as integer minor units.
- Refund amounts cannot exceed the order total.
- Payment status must remain consistent with the refunded amount.
- Notes cannot be blank and cannot exceed 500 characters.
- Note sequence numbers must be contiguous.
- A support case must reference the scenario's order.
- Objective refund cannot exceed the order total.
- Expected remaining balance must equal the order total minus the
  objective refund, regardless of the current refund state.

## 5. Deterministic state

The state implementation is defined in
`agenttrax/scenarios/state.py`.

`OrderSupportScenarioState` owns the scenario's order, support case,
and objective.

Its `reset()` method reconstructs the same initial state and returns
a validated snapshot.

The state exposes read-only properties and a snapshot operation.
State replacement methods enforce the expected record type and
scenario identifiers.

State is held in memory. Resetting the scenario does not access or
modify external systems.

## 6. Registered operations

The operations are defined in
`agenttrax/scenarios/order_support.py`.

The registry exposes exactly four tools.

### `get_order(order_id)`

- Reads the simulated order.
- Does not mutate state.
- Rejects an unknown order.

### `add_case_note(case_id, note)`

- Appends a note to the specified support case.
- Rejects unknown cases and closed cases.
- Rejects non-string, empty, whitespace-only, or over-500-character
  notes.
- Assigns the next deterministic sequence number.

### `issue_refund(order_id, amount_minor_units)`

- Applies a simulated refund to the order.
- Requires a known order with payment status `PAID` or
  `PARTIALLY_REFUNDED`.
- Requires a positive integer amount in minor units.
- Rejects booleans, floats, strings, and other non-integer values.
- Rejects amounts greater than the remaining refundable balance.
- Updates the refunded amount and payment status consistently.

No real payment or financial transaction is performed.

### `close_case(case_id)`

- Closes the specified support case.
- Rejects unknown or already closed cases.
- Requires an associated order with a successful simulated refund.
- Requires at least one case note.

## 7. Registry and error behavior

The registry is defined in `agenttrax/scenarios/registry.py`.

`ScenarioToolRegistry` provides an explicit allowlist containing:

- `get_order`
- `add_case_note`
- `issue_refund`
- `close_case`

It rejects unknown tool names, non-dictionary argument payloads,
missing arguments, unexpected arguments, and invalid basic argument
types before dispatching an operation.

Registry-level errors use `ScenarioRegistryError` and
`RegistryErrorCode`.

Operation-level business-rule failures use
`ScenarioOperationError` and `OperationErrorCode`.

These are intentionally distinct error boundaries:

- Registry errors describe tool resolution or argument-shape failures.
- Operation errors describe invalid operation inputs or business-rule
  failures encountered by a known operation.

Operation errors propagate to the caller. They must not be converted
into successful results or hidden by a generic success response.

The registry is an internal simulator dispatcher. It is not a public
agent execution gateway and does not independently authorize actions.
Later execution features must enforce the mandatory policy path.

## 8. Safety boundaries

AT-03 preserves the simulator-first MVP constraints:

- No network access is required by scenario operations.
- No shell commands or arbitrary code execution are exposed.
- No real filesystem mutation is performed by scenario tools.
- No external account or payment provider is accessed.
- Only explicitly registered operations can be dispatched.
- Invalid inputs and unknown operations are rejected.
- State changes are limited to the in-memory scenario.
- Operation failures are not reported as successful execution.

The registry alone does not provide policy enforcement. All future
agent-driven execution must use the policy gateway and gated executor
defined by later features.

## 9. Tests and verification

The AT-03 tests are located in `tests/scenarios/`.

They cover:

- State initialization, reset, snapshots, and replacement validation.
- Operation success and rejection paths.
- Refund amount and payment-status boundaries.
- Case-note validation and sequencing.
- Case closure preconditions.
- Registry allowlisting and unknown-tool rejection.
- Missing, unexpected, and invalid arguments.
- Separation of registry errors from operation errors.

Final verification:

- Scenario state tests: 9 passed.
- Scenario operation tests: 32 passed.
- Scenario registry tests: 18 passed.
- Total scenario tests: 59 passed.
- Full test suite: 362 passed.
- Ruff: all checks passed.
- `git diff --check`: clean.


## 10. Dependencies and follow-on features

AT-03 depends on AT-02 core contracts.

The implementation provides the simulator foundation for:

- AT-04: Policy engine.
- AT-05: Gated tool executor.
- AT-06: Approval workflow.
- AT-07: Independent verifier.
- AT-08: Trace recorder.
- AT-09: End-to-end showcase scenario.

AT-03 does not claim to implement any of those features.

## 11. Completion conditions

AT-03 can be marked complete after final review confirms:

1. Reset produces the same initial state.
2. Only the four specified tools are registered.
3. Unknown tools and invalid arguments are rejected.
4. Operations enforce their documented business rules.
5. State changes remain deterministic and in memory.
6. The scenario objective is explicit and testable.
7. Tests, Ruff, and diff checks pass.
8. Documentation accurately describes the implementation and its
   limitations.
