# AT-06 — Approval Workflow

## 1. Feature Overview

**Feature ID:** AT-06
**Feature Name:** Approval Workflow
**Dependency:** AT-05 — Gated Tool Executor
**Implementation Branch:** `feature/at-06-approval-workflow`
**Status:** Completed
**Approval Storage:** In-memory only
**Execution Environment:** Deterministic local simulator

### 1.1 Purpose

AT-06 introduces an explicit human approval workflow for actions that the
AgentTrax policy engine classifies as `REQUIRE_APPROVAL`.

The workflow must ensure that an action cannot execute merely because an
agent proposed it or because the policy engine requested approval.

Execution requires an explicit approval associated with the exact original
action proposal and its relevant policy context.

### 1.2 Objectives

- Store pending approval requests in memory.
- Require an explicit approval or denial decision.
- Bind approval to the exact action proposal.
- Bind approval to the policy context under which it was requested.
- Enforce approval expiration.
- Prevent approval replay and duplicate execution.
- Reevaluate policy before approved execution.
- Preserve the existing gated execution boundary.
- Fail closed whenever approval integrity cannot be established.
- Provide deterministic tests using an injectable clock.

## 2. Scope

### 2.1 Included

- Immutable approval evidence contract.
- Approval lifecycle states and internal records.
- In-memory approval service.
- Approval request creation.
- Explicit approval and denial.
- Expiration checks.
- Exact proposal digest validation.
- Policy-context validation.
- One-time approval consumption.
- Thread-safe approval state transitions.
- Integration with `GatedToolExecutor`.
- Lifecycle consistency updates.
- Acceptance and regression tests.
- Feature documentation.

### 2.2 Excluded

AT-06 does not implement:

- Database or persistent approval storage.
- HTTP endpoints or API routes.
- User interfaces.
- External identity providers.
- Email or notification services.
- Cryptographic signatures or claims of production-grade identity assurance.
- Real order, payment, customer, or external service operations.
- Arbitrary shell commands or repository execution.
- AT-07 independent verification.
- AT-08 trace recording.
- AT-09 showcase.
- AT-10 API layer.

All operations remain within the deterministic in-memory simulator.

## 3. Architectural Responsibilities

### 3.1 Policy Engine

The policy engine remains responsible for deciding whether an action is:

- `ALLOW`
- `BLOCK`
- `REQUIRE_APPROVAL`

AT-06 must not change policy decisions to bypass approval.

### 3.2 Gated Tool Executor

The executor remains the only public route to simulator tool execution.

It will expose the approval workflow through:

- `request_approval(proposal, decision)`
- `approve(approval_id, approver_id)`
- `deny(approval_id, approver_id)`
- `execute_approved(approval_id)`

The existing `execute(proposal, supplied_decision)` behavior remains unchanged.

### 3.3 Approval Service

The internal approval service is responsible for:

- Creating pending approval records.
- Retaining the original proposal and policy decision.
- Recording the proposal digest and policy version.
- Recording approval creation and expiration times.
- Recording the explicit approver and decision time.
- Enforcing valid state transitions.
- Preventing duplicate consumption.
- Rejecting expired, denied, mismatched, or consumed requests.

The executor must not accept a replacement proposal or caller-created
approval evidence when executing an approved action.

## 4. Approval Contracts

### 4.1 Approval Evidence

Introduce an immutable `ApprovalEvidence` contract using the existing
`StrictContractModel`.

The evidence must identify:

- Approval ID.
- Action ID.
- Proposal digest.
- Policy version.
- Approval timestamp.
- Expiration timestamp.

All timestamps must be timezone-aware and normalized to UTC.

The evidence must reject blank identifiers, malformed digests, and invalid
timestamp relationships.

### 4.2 Approval State

The approval lifecycle must distinguish at least:

- `PENDING`
- `APPROVED`
- `DENIED`
- `EXPIRED`
- `CONSUMED`

State changes must be controlled by the approval service.

An approval must never transition from `DENIED`, `EXPIRED`, or `CONSUMED`
back to an executable state.

### 4.3 Approval Record

The internal approval record must retain:

- Approval ID.
- Original immutable action proposal.
- Original policy decision.
- Proposal digest.
- Policy version.
- Creation timestamp.
- Expiration timestamp.
- Current approval state.
- Approver identity when decided.
- Decision timestamp when decided.

Records are held in memory for the lifetime of the service.

## 5. Exact Action Binding

Approval is valid only for the original action.

The approval service must bind the record to:

- `action_id`
- `task_id`
- `tool_name`
- Exact validated arguments
- `requested_by`
- Proposal digest
- Policy version
- Original policy decision context

The existing `compute_proposal_digest()` function must be reused.

A changed action payload must not inherit an earlier approval.

The executor must load the original proposal from the approval service.
Callers must not supply a replacement proposal to `execute_approved()`.

## 6. Approval Lifecycle

### 6.1 Request

The executor receives an action proposal and policy decision.

Before creating a pending request, it must:

1. Validate the proposal and decision linkage.
2. Recompute the proposal digest.
3. Obtain a fresh simulator snapshot.
4. Reevaluate policy.
5. Confirm that the current decision is `REQUIRE_APPROVAL`.
6. Confirm that the supplied decision matches the current decision.
7. Store the original proposal and decision.

A `BLOCK` or `ALLOW` decision must not be converted into an approval request.

### 6.2 Explicit Approval

A caller explicitly approves a pending approval ID.

The supplied approver identifier is an audit label only. AT-06 does not
authenticate the caller or establish that the caller is authorized. No
external identity provider or production identity assurance is included.

The service records the approver identifier and approval timestamp.

Approval is not a model-generated string, boolean supplied as execution
authorization, or replacement policy decision.

### 6.3 Explicit Denial

A pending approval may be explicitly denied.

A denied request cannot be approved or executed later.

### 6.4 Expiration

The default approval lifetime is 15 minutes.

The lifetime must be configurable for tests and controlled use.

All time comparisons use an injected UTC clock.

An approval is expired when:

`now >= expires_at`

An expired approval cannot be revived.

### 6.5 Approved Execution

The executor receives only an approval ID.

It must:

1. Retrieve the original approval record.
2. Confirm the record is approved.
3. Confirm it has not expired.
4. Recompute and compare the proposal digest.
5. Confirm the action ID and policy context.
6. Obtain a fresh simulator snapshot.
7. Reevaluate the policy.
8. Confirm the action still requires approval and remains valid.
9. Construct evidence from the service-owned record.
10. Atomically consume the approval.
11. Invoke the existing simulator registry through the gated executor.
12. Validate the resulting lifecycle using the approval evidence.

The approval must be consumed before tool invocation.

A failed tool invocation does not restore approval eligibility.

### 6.6 Replay Protection

An approval may be consumed at most once.

A second execution attempt using the same approval ID must not invoke the
simulator registry.

Concurrent attempts must not both consume the same approval.

State transitions and consumption must be protected by a thread-safe lock.

## 7. Expiration and Policy Context

The policy must be reevaluated immediately before approved execution.

If the current policy context no longer matches the stored approval context,
execution must fail closed.

Approval cannot authorize:

- A different action.
- Changed arguments.
- A different tool.
- A different policy version.
- An action that is now blocked.
- An unknown tool.
- Invalid arguments.
- An operation outside simulator permissions.

The approval workflow must not manufacture an `ALLOW` decision.

The original `REQUIRE_APPROVAL` decision remains the policy decision.

## 8. Lifecycle Contract Integration

The existing `check_lifecycle_consistency()` function will receive a narrow,
backward-compatible optional approval evidence parameter.

Existing calls without approval evidence must retain their current behavior.

For `REQUIRE_APPROVAL`:

- `NOT_EXECUTED` remains valid for pending, denied, expired, and integrity
  failure outcomes.
- `SUCCEEDED` and `FAILED` are permitted only when valid matching approval
  evidence is supplied.
- Evidence must match the proposal action ID, proposal digest, and policy
  version.
- Approval timestamps must be consistent with the evidence expiration time.

The lifecycle checker validates contract consistency. It is not itself the
security boundary.

The executor must independently ensure that evidence came from its
service-owned approval record and that the approval was consumed exactly once.

## 9. Failure Handling

The workflow must fail closed.

| Condition | Expected behavior |
|---|---|
| Approval is pending | No execution |
| Approval is denied | No execution |
| Approval is expired | No execution |
| Approval ID is unknown | Reject request; no execution |
| Approval already consumed | Reject replay; no execution |
| Proposal digest mismatch | Integrity failure; no execution |
| Action ID mismatch | Integrity failure; no execution |
| Policy version mismatch | Integrity failure; no execution |
| Current policy blocks action | No execution |
| Current policy context changed | No execution |
| Approval service cannot validate state | No execution |
| Registry operation fails after consumption | Failed execution; approval remains consumed |

Existing `NotExecutedReason` values should be reused wherever they accurately
represent the outcome:

- `APPROVAL_PENDING`
- `APPROVAL_DENIED`
- `APPROVAL_EXPIRED`
- `INTEGRITY_CHECK_FAILED`

Unknown identifiers and invalid state transitions may raise
`ContractViolation`, provided they cannot reach the registry.

## 10. Security Invariants

1. No approval-required action executes before explicit approval.
2. Approval applies only to the exact original proposal.
3. Approval applies only to the original policy context.
4. Changed arguments invalidate the approval.
5. Expired approvals cannot execute.
6. Denied approvals cannot execute.
7. Consumed approvals cannot execute again.
8. Concurrent attempts cannot execute the same approval twice.
9. Policy is reevaluated before execution.
10. Policy `BLOCK` is never bypassed.
11. Approval never expands simulator permissions.
12. The executor retrieves the original proposal from internal storage.
13. Caller-supplied evidence cannot authorize execution.
14. Approval is consumed before registry invocation.
15. A failed operation does not restore approval eligibility.
16. No real external side effects are introduced.

## 11. Implementation Files

Expected files:

| File | Responsibility |
|---|---|
| `agenttrax/contracts/models.py` | Approval evidence and lifecycle consistency |
| `agenttrax/execution/approval.py` | In-memory approval service and records |
| `agenttrax/execution/executor.py` | Public approval workflow and gated execution |
| `agenttrax/execution/__init__.py` | Public exports |
| `tests/contracts/test_models.py` | Approval evidence contract tests |
| `tests/execution/test_approval.py` | Approval service lifecycle and security tests |
| `tests/execution/test_executor.py` | Approved execution and regression tests |
| `docs/AT-06-approval-workflow-spec.md` | Feature specification and implementation record |
| `progress-tracker.md` | Feature completion status |

No new dependency is expected.

## 12. Acceptance Test Plan

### 12.1 Contract Tests

- Valid approval evidence is accepted.
- Blank approval identifiers are rejected.
- Invalid proposal digests are rejected.
- Naive timestamps are rejected.
- Expiration before approval is rejected.
- Evidence for another action is rejected.
- Evidence for another proposal digest is rejected.
- Evidence for another policy version is rejected.
- Existing lifecycle behavior without evidence is unchanged.
- `REQUIRE_APPROVAL` cannot produce a successful result without evidence.

### 12.2 Approval Service Tests

- A valid request creates a pending record.
- The original proposal and decision are retained.
- A non-approval decision cannot create a request.
- Explicit approval transitions pending to approved.
- Explicit denial transitions pending to denied.
- Duplicate decisions are rejected.
- Unknown approval IDs are rejected.
- Expiration occurs at the exact expiry boundary.
- Expired approvals cannot be approved or consumed.
- Consumed approvals cannot be reused.
- Concurrent consumption permits at most one successful consumer.
- Changed proposal payload cannot reuse approval.

### 12.3 Executor Integration Tests

- Approval-required action does not execute before approval.
- Approved action executes through the existing registry.
- Denied action does not execute.
- Expired action does not execute.
- Duplicate execution does not invoke the registry twice.
- Changed proposal or policy context fails closed.
- Policy is reevaluated immediately before execution.
- A newly blocked action does not execute.
- Approval cannot authorize an unknown tool.
- Approval cannot authorize invalid arguments.
- Failed registry execution leaves approval consumed.
- Existing `execute()` behavior remains unchanged.
- Existing AT-05 tests remain passing.

### 12.4 Regression Tests

- Full contract test suite passes.
- Full execution test suite passes.
- Full project test suite passes.
- Ruff lint passes.
- Relevant formatting checks pass.
- Compilation passes.
- Git whitespace checks pass.

## 13. Implementation Stages

1. Implement approval evidence and in-memory approval service.
2. Test contract validation and approval state transitions.
3. Extend lifecycle consistency with optional approval evidence.
4. Integrate approval request, approval, denial, and approved execution into
   `GatedToolExecutor`.
5. Add executor acceptance and replay-protection tests.
6. Run regression checks.
7. Finalize this specification and update `progress-tracker.md`.

## 14. Completion Criteria

AT-06 is complete only when:

- All acceptance criteria are implemented.
- Approval is explicit, exact-payload-bound, time-limited, and single-use.
- The executor remains the only route to simulator tool execution.
- All approval failure paths fail closed.
- Existing AT-02 through AT-05 behavior remains compatible.
- Focused and full regression tests pass.
- Ruff and required validation checks pass.
- Documentation reflects the implemented behavior.
- `progress-tracker.md` is updated.

No commit or push is implied by feature completion.
