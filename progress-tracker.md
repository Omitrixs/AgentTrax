# Progress Tracker

Update this file whenever the active feature, implementation status, or an architectural decision changes.

## Current Phase

- Phase 1: Core runtime implementation.

## Current Goal

- AT-05: Gated Tool Executor completed and verified.
- Independently validate policy decisions and refuse unauthorized execution.
- Integrate with AT-02 contracts, AT-03 simulator, and AT-04 policy engine.
- Preserve the approved feature boundaries and acceptance criteria.

## Project status

The initial project specification, repository baseline, and development environment are complete. AT-02 core contracts have been implemented and verified against the approved specification.

The project remains simulator-only. No real-world tool side effects are permitted in the MVP.

AT-03 deterministic scenario simulator has been implemented and passed final verification.

## Feature status

| Feature | Status | Evidence / notes |
|---|---|---|
| AT-00 Product specification | Approved | Simulator-first MVP, initial stack, CLI-first approach, order-management demo, and in-memory-first trace storage approved and recorded |
| AT-01 Repository and environment baseline | Completed | Python 3.12.10 and project-local `.venv` verified; development dependencies installed; smoke test passes; Ruff passes; fresh-clone installation and verification passed |
| AT-02 Core contracts | Completed | All five contracts and enums implemented; strict validation, immutable nested JSON, UTC timestamps, canonical proposal digest, trace sanitization, and lifecycle consistency implemented; H1–H10 covered by tests; 302 tests pass; Ruff and `git diff --check` pass |
| AT-03 Deterministic scenario simulator | Completed | One deterministic in-memory order-support scenario; immutable validated models; reset behavior; four allowlisted tools; business-rule validation; 59 scenario tests pass; full suite: 362 passed; Ruff and diff checks clean |
| AT-04 Policy engine | Completed | Pure allow/block/approval decision logic; 35 policy tests pass; full suite: 397 passed; Ruff and diff checks clean |
| AT-05 Gated tool executor | Completed | 30 AT-05 tests pass; full suite: 427 passed; project-wide Ruff lint passes; AT-05 formatting, compilation, and diff checks pass; repository-wide format check has documented pre-existing AT-02/AT-03 formatting differences and a Ruff crash; spec: `docs/AT-05-gated-tool-executor-spec.md` |
| AT-06 Approval workflow | Not started | Explicit approval bound to the exact action payload, with expiry and replay protection |
| AT-07 Independent verifier | Not started | Verifies observed simulator state and task postconditions |
| AT-08 Trace recorder | Not started | Correlated lifecycle events and sensitive-value redaction |
| AT-09 End-to-end showcase scenario | Not started | Repeatable scenario showing blocked, approval-required, and successfully verified actions |
| AT-10 API layer | Deferred | Reconsider FastAPI after the CLI workflow is proven |
| AT-11 Showcase UI | Not started | Focused dashboard for scenario control and trace inspection |
| AT-12 Model adapter | Deferred | Optional real model integration; deterministic mock agent remains a proposed architectural decision |
| AT-13 Evaluation suite | Not started | Fixed scenarios and measurable evaluation metrics |
| AT-14 Showcase hardening | Not started | Clean setup, documented limitations, demo script, and final regression checks |

## In Progress

- None. AT-05 is complete; AT-06 is the next planned feature.

## Completed

- Repository baseline commit created and verified.
- Approved initial decisions D-001 and D-005 through D-009 recorded in `decisions-log.md`.
- AT-01: Repository and environment baseline completed and verified from a fresh Git clone.
- AT-02: Core contracts implemented and verified against `docs/AT-02-core-contracts-spec.md`.
  - All five contracts and their enums implemented.
  - Strict validation and immutable JSON structures enforced.
  - Timestamp conventions and trace-redaction requirements enforced.
  - `compute_proposal_digest`, `sanitize_details`, and `check_lifecycle_consistency` implemented.
  - Lifecycle rules H1–H10 covered by tests.
  - AT-02 resolved decisions AT02-Q1 through AT02-Q4 implemented.
  - Full test suite: 302 passed.
  - Ruff: all checks passed.
  - `git diff --check`: clean.

- AT-03: Deterministic scenario simulator completed and verified.
  - Deterministic order-support scenario implemented.
  - Strict immutable models and objective consistency validation implemented.
  - Deterministic reset and isolated in-memory state implemented.
  - Four explicitly allowlisted operations implemented.
  - Registry and operation errors remain distinct.
  - Regression tests cover inconsistent scenario objectives.
  - Scenario tests: 59 passed.
  - Full test suite: 362 passed.
  - Ruff: all checks passed.
  - `git diff --check`: clean.
  - Specification recorded in `docs/AT-03-simulator-spec.md`.

- AT-04: Policy engine completed and verified.
  - Pure deterministic policy evaluation returning ALLOW, BLOCK, REQUIRE_APPROVAL.
  - Business-rule boundaries enforced for all four tools.
  - Every valid refund requires approval.
  - Decisions are deterministic and bound to proposal digests.
  - Policy evaluation causes no side effects.
  - Policy tests: 35 passed.
  - Full test suite: 397 passed.
  - Ruff: all checks passed.
  - Specification recorded in `docs/AT-04-policy-engine-spec.md`.

- AT-05: Gated Tool Executor completed and verified.
  - Independently reevaluates policy against fresh simulator state.
  - Compares all six policy-decision fields before execution.
  - Invokes tools only through the existing simulator registry after a
    matching ALLOW decision.
  - BLOCK returns NOT_EXECUTED / POLICY_BLOCKED.
  - REQUIRE_APPROVAL returns NOT_EXECUTED / APPROVAL_PENDING.
  - Integrity failures fail closed; action ID and digest linkage
    mismatches raise ContractViolation before registry invocation.
  - Tool, serialization, and internal failures remain distinct.
  - AT-05 execution tests: 30 passed.
  - Full project test suite: 427 passed.
  - Project-wide Ruff lint: passed.
  - AT-05 formatting, compilation, and git diff checks: passed.
  - Repository-wide formatting limitation documented in the AT-05 spec.
  - Specification: `docs/AT-05-gated-tool-executor-spec.md`.
  - Implementation: `agenttrax/execution/executor.py`.
  - Tests: `tests/execution/test_executor.py`.


## Deferred requirements

- AT-02 / AT-07: Task-level aggregation must not count `NO_CHANGE_CONFIRMED` as goal completion. A successfully verified absence of state change for a non-executed action is not equivalent to successful completion of the user's task. Enforce this in the independent verifier and task-level outcome aggregation.
- AT-10: API layer remains deferred until the core CLI workflow is proven.
- AT-12: Real model integration remains optional and deferred.

## Next Up

1. AT-06: Implement the approval workflow.
2. AT-07: Implement the independent verifier.
3. AT-08: Implement the trace recorder.

Follow the feature registry for dependencies and acceptance criteria. Do not skip feature boundaries.

## Open Questions

- Should the showcase UI be included in the first showcase, or deferred until the core workflow is proven?
- Should the mock-agent approach be formally accepted as an architectural decision? D-002 remains proposed.
- Should the modular monolith and separation of policy, execution, and verification be formally accepted? D-003 and D-004 remain proposed.

## Session Notes

- Keep the MVP simulator-only. No real-world tool side effects.
- Do not infer that planned features exist.
- Keep documentation aligned with verified repository state.
- Implement one approved feature at a time.
- Preserve existing Git history and verify changes before committing.
- Do not mark proposed architectural decisions as accepted without explicit approval.