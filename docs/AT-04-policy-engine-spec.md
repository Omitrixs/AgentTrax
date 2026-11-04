# AgentTrax AT-04: Deterministic Policy Engine

Status: **Implementation and focused tests completed; final review pending.**

## 1. Purpose

AT-04 implements a deterministic policy engine for the AgentTrax order-support scenario.

The engine evaluates proposed tool actions and returns one of three decisions:

- `ALLOW`
- `BLOCK`
- `REQUIRE_APPROVAL`

It provides structured reason codes and human-readable explanations for every decision.

Policy evaluation is read-only. It does not execute tools, mutate scenario state, create approvals, or perform external operations.

## 2. Scope

### Included

- Pure policy evaluation for the deterministic order-support scenario.
- Explicit decisions using the existing AT-02 policy decision contracts.
- Deterministic policy version identification.
- Validation of known tools and their argument structures.
- Business-rule evaluation using an immutable scenario snapshot.
- Structured reason codes and human-readable explanations.
- Proposal digest binding for every policy decision.
- Unit tests covering all three decisions, invalid inputs, and boundary conditions.

### Excluded

- Tool execution or a gated execution gateway.
- Approval creation, resolution, expiry, or replay protection.
- Independent task verification.
- Lifecycle tracing or persistent policy storage.
- API routes, user interfaces, model providers, and external integrations.

These responsibilities remain assigned to their respective later features in `feature-registry.md`.

## 3. Policy definition

**Policy version:** `order_support_policy_v1`

**Scenario ID:** `order_refund_support_v1`

The policy evaluates the four registered operations implemented by AT-03.

### Policy decision matrix

| Tool | Condition | Decision |
|---|---|---|
| `get_order` | Existing order | `ALLOW` |
| `get_order` | Unknown order | `BLOCK` |
| `add_case_note` | Existing open case and valid note | `ALLOW` |
| `add_case_note` | Unknown or closed case | `BLOCK` |
| `issue_refund` | Valid refund for an eligible order with sufficient balance | `REQUIRE_APPROVAL` |
| `issue_refund` | Unknown or unpaid order | `BLOCK` |
| `issue_refund` | Invalid amount or insufficient balance | `BLOCK` |
| `close_case` | Successful refund and at least one note exist | `ALLOW` |
| `close_case` | Unknown, already closed, or missing prerequisites | `BLOCK` |
| Any operation | Unknown tool | `BLOCK` |
| Any operation | Invalid arguments | `BLOCK` |

Every otherwise valid refund requires approval, regardless of its amount.

The policy does not use an arbitrary monetary threshold.

## 4. Policy engine implementation

The implementation is defined in `agenttrax/policy/engine.py`.

The public package interface is exposed through `agenttrax/policy/__init__.py`.

`PolicyEngine.evaluate()` accepts:

- An AT-02 `ActionProposal`.
- An immutable AT-03 `ScenarioSnapshot`.

It returns an AT-02 `PolicyDecision`.

The evaluation process:

1. Validates the proposal and snapshot types.
2. Checks whether the tool is explicitly supported.
3. Validates the exact argument names and value types.
4. Evaluates the operation's scenario-specific business conditions.
5. Produces a structured policy decision.

The engine does not call `ScenarioToolRegistry` or any operation handler.

## 5. Decision and reason codes

The engine uses the existing AT-02 decision and reason-code contracts.

### Decisions

- `ALLOW`: The proposed action satisfies the policy and may proceed to a later execution gate.
- `BLOCK`: The proposed action is not permitted.
- `REQUIRE_APPROVAL`: The action is valid but requires approval before execution.

### Reason codes

| Reason code | Meaning |
|---|---|
| `ALLOWED_BY_POLICY` | The action satisfies the policy. |
| `BLOCKED_BY_POLICY` | A scenario business rule prevents the action. |
| `APPROVAL_REQUIRED` | The action requires approval before execution. |
| `UNKNOWN_TOOL` | The proposed tool is not recognized by the policy. |
| `INVALID_ARGUMENTS` | The proposed arguments do not satisfy the tool's requirements. |

Every decision includes:

- Action ID.
- Proposal digest.
- Decision.
- Reason code.
- Human-readable reason.
- Policy version.

The existing `PolicyDecision` contract validates compatible decision and reason-code combinations.

## 6. Tool-specific policy rules

### `get_order`

- Requires exactly `order_id`.
- Requires a nonblank string identifier.
- Allows access to the scenario's existing order.
- Blocks unknown order identifiers.

### `add_case_note`

- Requires exactly `case_id` and `note`.
- Requires a nonblank case identifier.
- Requires a nonblank string note of no more than 500 characters.
- Allows notes on an existing open case.
- Blocks unknown and closed cases.

### `issue_refund`

- Requires exactly `order_id` and `amount_minor_units`.
- Requires a nonblank order identifier.
- Requires a positive integer refund amount.
- Rejects booleans, floats, strings, zero, and negative amounts.
- Requires an existing order that is not unpaid.
- Requires the refund amount not to exceed the remaining refundable balance.
- Returns `REQUIRE_APPROVAL` for every otherwise valid refund.

A policy decision does not perform the refund.

### `close_case`

- Requires exactly `case_id`.
- Requires a nonblank case identifier.
- Requires an existing open support case.
- Requires a successful simulated refund.
- Requires at least one support-case note.
- Allows closure only when all prerequisites are satisfied.

## 7. Determinism and proposal binding

The policy engine uses the fixed policy version:

`order_support_policy_v1`

The decision is deterministic for the same proposal, scenario snapshot, and policy version.

Every decision includes the proposal's SHA-256 digest, calculated using the existing AT-02 `compute_proposal_digest()` function.

This binds the policy decision to the exact action proposal rather than merely to a tool name.

The engine does not introduce timestamps, random values, network requests, or external dependencies into policy evaluation.

## 8. Safety boundaries

AT-04 preserves the simulator-first MVP constraints:

- Policy evaluation is read-only.
- No scenario state mutation occurs.
- No tool handler or registry dispatch occurs.
- Unknown tools are blocked.
- Invalid arguments are blocked.
- Refunds cannot proceed directly from a policy decision.
- Approval-required actions are not executed by this feature.
- Policy decisions are bound to their originating proposals.
- No external account, payment provider, or production system is accessed.

`ALLOW` is a policy decision, not proof that execution has occurred.

The mandatory execution gate remains the responsibility of AT-05.

## 9. Tests and verification

The AT-04 tests are located in `tests/policy/test_engine.py`.

They cover:

- Allowed order reads.
- Allowed case notes.
- Maximum-length valid notes.
- Allowed case closure after refund and note prerequisites.
- Approval requirements for valid refunds of different amounts.
- Unknown tool rejection.
- Unknown order and case rejection.
- Missing and unexpected arguments.
- Invalid identifiers and note values.
- Invalid refund amount types and boundaries.
- Refunds exceeding the remaining balance.
- Refunds on unpaid orders.
- Notes on closed cases.
- Case closure without refund or notes.
- Case closure on an already closed case.
- Proposal digest and action ID binding.
- Deterministic decisions for identical inputs.
- No scenario state mutation during evaluation.
- Rejection of incorrect top-level input types.

Current verification:

- Policy tests: 35 passed.
- Full project regression suite: 397 passed.
- Full-project Ruff lint check: passed.
- AT-04 formatting check: all 3 Python files already formatted.
- Python syntax checks: passed.
- Staged Git whitespace check: passed.

## 10. Dependencies and follow-on features

AT-04 depends on:

- AT-02: Core contracts.
- AT-03: Deterministic scenario simulator.

It provides the policy foundation for:

- AT-05: Gated tool executor.
- AT-06: Approval workflow.
- AT-07: Independent verifier.
- AT-08: Trace recorder.
- AT-09: End-to-end showcase scenario.

AT-04 does not claim to implement any of those features.

## 11. Completion conditions

AT-04 can be marked complete after final review confirms:

1. All three policy decisions are implemented.
2. Unknown tools and invalid arguments fail closed.
3. Business-rule boundaries are enforced.
4. Valid refunds require approval.
5. Decisions are deterministic and proposal-bound.
6. Policy evaluation causes no side effects.
7. Focused and full regression tests pass.
8. Ruff and formatting checks pass.
9. Git diff and whitespace checks are clean.
10. Documentation accurately describes the implementation and its limitations.