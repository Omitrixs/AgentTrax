# Feature Registry

This file is the source of truth for feature boundaries and acceptance criteria. Implement one feature ID at a time. Status lives in `progress-tracker.md`.

## Feature IDs and dependencies

### AT-00: Product specification
**Depends on:** None

**Scope**
- Approve product overview, architecture, security boundaries, and showcase goal.
- Resolve any blocking questions.

**Acceptance criteria**
- Owner confirms the initial scope.
- Stack and demo scenario are approved.
- No conflicting requirements remain unresolved for AT-01.

### AT-01: Repository and environment baseline
**Depends on:** AT-00

**Scope**
- Inspect current repository and Git state.
- Confirm Python version, environment, test runner, and lint setup.
- Add only the minimal missing project scaffolding.

**Acceptance criteria**
- Setup instructions work from a clean checkout.
- A smoke test passes.
- Lint passes if configured.
- No secrets or unrelated files are added.
- Actual status is recorded in `progress-tracker.md`.

### AT-02: Core contracts
**Depends on:** AT-01

**Scope**
- Define typed action proposal, policy decision, execution result, verification result, and trace event contracts.
- Define status enums and reason codes.

**Acceptance criteria**
- Valid examples parse.
- Invalid and unknown fields are rejected according to the chosen schema policy.
- Contracts distinguish proposal, decision, execution, and verification.
- Tests cover valid and invalid cases.

### AT-03: Deterministic scenario simulator
**Depends on:** AT-02

**Scope**
- Implement one in-memory business scenario.
- Register a small set of explicit tools.
- Define initial state and objective postconditions.

**Acceptance criteria**
- Scenario reset returns the same initial state.
- Tools operate only on simulator state.
- Unknown tools cannot be resolved.
- Scenario success conditions are explicit and testable.

### AT-04: Policy engine
**Depends on:** AT-02, AT-03

**Scope**
- Implement pure policy evaluation returning `ALLOW`, `BLOCK`, or `REQUIRE_APPROVAL`.
- Provide reason codes and human-readable explanations.
- Start with deterministic scenario rules.

**Acceptance criteria**
- Same input and policy version produce the same decision.
- Invalid or unknown actions fail closed.
- Tests cover all three decisions and boundary cases.
- Policy evaluation itself causes no side effects.

### AT-05: Gated tool executor
**Depends on:** AT-03, AT-04

**Scope**
- Route every action through the policy decision.
- Execute only allowlisted simulator tools.
- Prevent blocked or pending actions from executing.

**Acceptance criteria**
- Executor independently checks action/decision linkage.
- Blocked actions never invoke tools.
- Unknown tools and invalid arguments never invoke tools.
- Execution failure is represented distinctly from policy denial.
- Tests prove these boundaries.

### AT-06: Approval workflow
**Depends on:** AT-05

**Scope**
- Store a pending action and require explicit approval for designated actions.
- Bind approval to the exact action payload and expire it.

**Acceptance criteria**
- No execution before approval.
- Changed payload requires a new approval.
- Duplicate, expired, or mismatched approval is rejected.
- Approval cannot expand beyond the simulator's permissions.

### AT-07: Independent verifier
**Depends on:** AT-03, AT-05
**Status:** Completed

**Scope**
- Independently verify supported action transitions against observed simulator state.
- Evaluate task-level postconditions against the explicit scenario objective.
- Reconcile executor-reported results with observed state and fail closed when evidence is missing, conflicting, or unverifiable.
- Keep action-level `NO_CHANGE_CONFIRMED` distinct from task-level completion.

**Acceptance criteria**
- Model-generated claims cannot set verification status.
- A tool success with an unmet postcondition does not become verified task success.
- Verifier errors cannot produce verified success.
- Missing or conflicting evidence produces an inconclusive result.
- `NO_CHANGE_CONFIRMED` cannot establish task-level success.
- Tests cover success, failure, inconclusive outcomes, and task-level objective evaluation.

**Specification:** `docs/AT-07-independent-verifier-spec.md`

### AT-08: Trace recorder
**Depends on:** AT-02, AT-04, AT-05, AT-07

**Scope**
- Record correlated proposals, policy decisions, approval outcomes, executions, and verification results.
- Preserve task and action correlation.
- Maintain deterministic event sequencing and immutable snapshots.
- Redact sensitive values through the existing trace contract sanitizer.
- Keep action-level verification distinct from task-level verification.
- Implement an independent in-memory recorder without changing executor or verifier behavior.

**Acceptance criteria**
- Trace order is deterministic in tests.
- Each event links to a task and action where applicable.
- Invalid lifecycle relationships and digest mismatches are rejected.
- Execution labels reflect actual execution results.
- Approval labels reflect actual approval-service outcomes.
- Action and task verification scopes are distinguishable.
- Secrets are redacted and caller-owned data is not mutated.
- Concurrent recording preserves sequence integrity.
- Failed records do not consume sequence numbers.

### AT-09: End-to-end showcase scenario
**Depends on:** AT-03 through AT-08

**Scope**
- Provide one repeatable scenario with at least one blocked action, one approval-required action, and one successful verified task.

**Acceptance criteria**
- One documented command or endpoint runs the scenario.
- Reset and replay are deterministic.
- Output shows policy decision, execution, and independent verification separately.
- Failure paths are visible and honest.

### AT-10: API layer
**Depends on:** AT-09

**Scope**
- Add a thin FastAPI boundary for starting a scenario, retrieving status, approving an action, and retrieving a trace, only if needed for the chosen demo.

**Acceptance criteria**
- Request and response models are validated.
- Errors are structured.
- No API route bypasses the policy gateway.
- No secrets or internal stack traces are returned.

### AT-11: Showcase UI
**Depends on:** AT-10

**Scope**
- Add a focused dashboard for scenario control and trace inspection.

**Acceptance criteria**
- User can start/reset a scenario.
- User can inspect policy decisions and reasons.
- User can approve a pending action when appropriate.
- Task completion state reflects verifier output.
- Loading, error, blocked, and inconclusive states are visible.

### AT-12: Model adapter
**Depends on:** AT-09

**Scope**
- Add an optional adapter to a selected model provider.
- Keep the deterministic mock agent as the test baseline.

**Acceptance criteria**
- Provider output is parsed and validated as an action proposal.
- Provider failure does not bypass policy.
- Core tests run without credentials or network access.
- No silent provider fallback occurs.

### AT-13: Evaluation suite
**Depends on:** AT-09

**Scope**
- Define a fixed set of scenarios and metrics comparing an unprotected baseline with AgentTrax-protected execution.

**Metrics**
- Task completion rate.
- Unsafe or policy-violating actions executed.
- Correctly blocked actions.
- False blocks.
- Verification accuracy against known scenario state.
- Recovery after a failed tool call.
- Added latency and cost where measurable.

**Acceptance criteria**
- Scenario set and expected outcomes are versioned.
- Metrics have explicit definitions.
- Results are reproducible.
- No results are fabricated or inferred from a tiny sample without qualification.

### AT-14: Showcase hardening
**Depends on:** AT-09; AT-11 if UI is included

**Scope**
- Clean setup instructions, demo script, limitations, and final regression pass.

**Acceptance criteria**
- Fresh setup instructions are followed successfully.
- Demo works without relying on undocumented state.
- Security and policy tests pass.
- README describes what is implemented and what is not.
- Known limitations are clearly disclosed.
