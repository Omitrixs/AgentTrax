# AgentTrax AT-05: Gated Tool Executor

## 1. Purpose

AT-05 implements the mandatory execution gateway between policy evaluation
and simulator tool invocation.

The executor accepts a validated action proposal and a policy decision. It
independently checks the decision against the current simulator state and
executes a registered simulator tool only when the independently evaluated
decision is a valid ALLOW decision matching the supplied decision.

The executor is a safety boundary. It must fail closed when the supplied
decision is inconsistent, stale, fabricated, malformed, or does not permit
execution.

AT-05 does not implement approval resolution or independent task
verification. Those responsibilities belong to later features.

## 2. Dependencies and scope

### Dependencies

- AT-02: Core contracts.
- AT-03: Deterministic scenario simulator.
- AT-04: Deterministic policy engine.

All three dependencies are completed.

### Included

- A gated execution service.
- Reuse of existing action, policy, and execution contracts.
- Reuse of the existing proposal digest and lifecycle consistency checker.
- Independent policy reevaluation using fresh simulator state.
- Comparison of the supplied and independently evaluated policy decisions.
- Invocation exclusively through the existing scenario tool registry.
- Structured execution results and deterministic timestamps.
- Explicit handling of policy denial, approval pending, integrity failure,
  tool failure, invalid tool results, and unexpected internal errors.
- Focused deterministic tests proving execution boundaries.

### Excluded

- AT-06 approval storage, tokens, expiry, signatures, or approval resolution.
- AT-07 independent task verification.
- AT-08 trace recording.
- AT-09 end-to-end showcase.
- AT-10 API layer.
- Real payment, order, customer, or external account operations.
- Network access, shell execution, arbitrary Python execution, or external
  tool adapters.
- Database persistence, queues, cloud deployment, and new dependencies.
- Rewriting AT-02 contracts, AT-03 simulator functionality, or AT-04 policy
  logic.

## 3. Execution architecture

The execution flow is:

1. Receive an ActionProposal and supplied PolicyDecision.
2. Validate their contract types.
3. Validate action identity and proposal digest linkage.
4. Obtain a fresh snapshot from the executor's simulator state.
5. Independently evaluate the proposal using the existing PolicyEngine.
6. Compare the supplied decision with the independently evaluated decision.
7. Reject inconsistent decisions.
8. Return a non-executed result for BLOCK or REQUIRE_APPROVAL.
9. Invoke the registered simulator tool only for a matching ALLOW decision.
10. Serialize the supported tool result into JSON-compatible data.
11. Construct an ExecutionResult with the injected UTC clock.
12. Validate the final lifecycle using check_lifecycle_consistency.

The executor owns or receives the simulator state and constructs its
ScenarioToolRegistry against that same state. Policy evaluation and tool
execution therefore operate against the same scenario instance.

The executor must not accept an arbitrary caller-provided snapshot as a
substitute for obtaining fresh state immediately before policy reevaluation.

## 4. Decision integrity

The executor independently reevaluates every proposal.

The supplied and independently evaluated decisions must match on all six
fields:

- action_id
- proposal_digest
- decision
- reason_code
- reason
- policy_version

A difference in any field fails closed.

The proposal digest is checked using the existing AT-02 digest function.
The executor must not introduce a second digest implementation or alter the
existing canonical digest definition.

### Contract linkage failures

An action ID mismatch or proposal digest mismatch is rejected with
ContractViolation before tool invocation.

This behavior preserves the existing AT-02 lifecycle contract: a lifecycle
result cannot be validated for a proposal and decision whose identity or
digest linkage is inconsistent.

These linkage failures are distinct from a linked but stale or fabricated
policy decision. The latter can be represented as:

NOT_EXECUTED / INTEGRITY_CHECK_FAILED

No registry invocation is permitted in either case.

## 5. Execution decision behavior

### ALLOW

Execution may proceed only when:

- The proposal and decision have valid contract types.
- Action identity and digest linkage are valid.
- Independent policy evaluation completes successfully.
- All six decision fields match.
- The independently evaluated decision is ALLOW.
- The tool is supported by the existing registry.
- The registry accepts the validated arguments.

The executor invokes the registry rather than calling scenario operations
directly.

### BLOCK

A matching BLOCK decision returns:

- Execution status: NOT_EXECUTED
- Not-executed reason: POLICY_BLOCKED

The registry must not be invoked.

### REQUIRE_APPROVAL

A matching REQUIRE_APPROVAL decision returns:

- Execution status: NOT_EXECUTED
- Not-executed reason: APPROVAL_PENDING

The registry must not be invoked.

AT-05 intentionally has no approval bypass. A valid approval mechanism is
deferred to AT-06.

## 6. Tool invocation and result handling

Only tools exposed through the existing ScenarioToolRegistry may execute.

The executor must not dynamically resolve arbitrary tool names, call
scenario operations directly, or provide an alternate execution path.

Execution outcomes are represented using the existing ExecutionResult
contract.

Expected failure categories:

| Condition | Execution status | Error code |
|---|---|---|
| Expected registry or scenario operation failure | FAILED | TOOL_ERROR |
| Unexpected internal invocation failure | FAILED | INTERNAL_ERROR |
| Unsupported or invalid result serialization | FAILED | INVALID_RESULT |
| Successful supported tool result | SUCCEEDED | None |

Successful results must be serialized into JSON-compatible dictionaries.

Only supported Pydantic result models are accepted for successful result
serialization. Unsupported results must not be converted into success.

The executor uses an injectable clock and produces timezone-aware UTC
completion timestamps.

No artificial timeout behavior or automatic retry mechanism is introduced.

## 7. Lifecycle consistency

Every ExecutionResult returned by the executor is checked with the existing
AT-02 check_lifecycle_consistency function.

The executor must preserve the distinction between:

- Policy denial.
- Approval pending.
- Integrity failure.
- Tool execution failure.
- Successful tool execution.

A successful tool execution is not proof that the overall task succeeded.
Independent task verification remains an AT-07 responsibility.

## 8. Error handling and fail-closed behavior

The executor must not invoke the registry when:

- Proposal or decision types are invalid.
- Action identity does not match.
- Proposal digest linkage does not match.
- Independent policy evaluation fails.
- The supplied decision differs from the independent decision.
- The decision is BLOCK.
- The decision is REQUIRE_APPROVAL.
- The tool is unknown.
- Arguments are invalid.

Contract linkage failures are rejected before execution. Other linked
integrity failures are represented using the existing NOT_EXECUTED and
INTEGRITY_CHECK_FAILED contract semantics where permitted.

Tool failures, serialization failures, and internal failures must remain
distinguishable.

Exceptions must not be converted into success-shaped results.

## 9. Test and acceptance criteria

The AT-05 test suite must cover:

1. Successful execution of get_order.
2. Successful execution of add_case_note.
3. Successful execution of close_case when its prerequisites are met.
4. BLOCK returns POLICY_BLOCKED without registry invocation.
5. REQUIRE_APPROVAL returns APPROVAL_PENDING without registry invocation.
6. Action ID mismatch is rejected without registry invocation.
7. Proposal digest mismatch is rejected without registry invocation.
8. Fabricated or stale decisions fail closed.
9. Each of the six decision fields is checked.
10. Unknown tools do not execute.
11. Invalid arguments do not execute.
12. Registry errors map to TOOL_ERROR.
13. Scenario operation errors map to TOOL_ERROR.
14. Unexpected invocation errors map to INTERNAL_ERROR.
15. Unsupported results map to INVALID_RESULT.
16. Serialization failures map to INVALID_RESULT.
17. The executor and registry share the same simulator state.
18. State changes affect subsequent policy evaluations.
19. Stale ALLOW decisions are rejected after relevant state changes.
20. The injected clock produces deterministic UTC timestamps.
21. Returned lifecycle results pass the AT-02 consistency checker.
22. Tests use deterministic fakes and do not require external services.
23. No real-world side effects occur.

Registry invocation spies must prove that blocked, pending, invalid, and
integrity-failing actions never reach the registry.

## 10. Current implementation

Implementation files:

- agenttrax/execution/executor.py
- tests/execution/test_executor.py

The executor reuses:

- ActionProposal and PolicyDecision.
- ExecutionResult and existing status/error enums.
- compute_proposal_digest and check_lifecycle_consistency.
- PolicyEngine.
- OrderSupportScenarioState.
- ScenarioToolRegistry.

The implementation uses a fresh simulator snapshot for independent policy
evaluation, compares all six decision fields, and invokes tools through the
registry only after a matching ALLOW decision.

The registry is kept as an internal implementation detail rather than
exposed through a public executor property.

## 11. Verification status

AT-05 implementation and acceptance review are complete.

Recorded verification:

- AT-05 execution tests: 30 passed.
- Full project test suite: 427 passed.
- Project-wide Ruff lint (`python -m ruff check .`): passed.
- AT-05 formatting (`python -m ruff format --check agenttrax/execution tests/execution`): passed; all three files are formatted.
- Python compilation (`python -m compileall -q agenttrax tests`): passed.
- Git whitespace validation (`git diff --check`): passed.

Repository-wide formatting limitation:

- `python -m ruff format --check .` reports existing formatting differences in
  `agenttrax/contracts/models.py`, `agenttrax/contracts/serialization.py`,
  `agenttrax/scenarios/__init__.py`, and `agenttrax/scenarios/models.py`.
- Ruff then crashes while rendering its report because an annotation range
  exceeds the source buffer.
- These files belong to completed AT-02/AT-03 work and were not reformatted as
  part of AT-05. The AT-05 execution files pass their own formatting check.

This limitation is documented rather than concealed. It does not change the
passing AT-05 formatting, lint, test, compilation, or diff-check results.

## 12. Safety boundaries

- Simulator-only execution.
- No real-world orders, refunds, payments, or customer accounts.
- No external network or provider integrations.
- No shell or arbitrary code execution.
- No approval bypass.
- No independent verification claims.
- No trace or task status claims introduced by the executor.
- No commits or pushes without explicit project-owner authorization.

AT-05 demonstrates a deterministic policy-enforced execution boundary. It
does not claim production security or general-purpose protection for
arbitrary external tools.