# Progress Tracker

Update this file whenever the active feature, implementation status, or an architectural decision changes.

## Current Phase

- Phase 1: Core runtime implementation.

## Current Goal

- Implement AT-03: Deterministic scenario simulator.
- Keep the first implementation entirely in-memory and simulator-only.
- Preserve the approved feature boundaries and acceptance criteria.

## Project status

The initial project specification, repository baseline, and development environment are complete. AT-02 core contracts have been implemented and verified against the approved specification.

The project remains simulator-only. No real-world tool side effects are permitted in the MVP.

## Feature status

| Feature | Status | Evidence / notes |
|---|---|---|
| AT-00 Product specification | Approved | Simulator-first MVP, initial stack, CLI-first approach, order-management demo, and in-memory-first trace storage approved and recorded |
| AT-01 Repository and environment baseline | Completed | Python 3.12.10 and project-local `.venv` verified; development dependencies installed; smoke test passes; Ruff passes; fresh-clone installation and verification passed |
| AT-02 Core contracts | Completed | All five contracts and enums implemented; strict validation, immutable nested JSON, UTC timestamps, canonical proposal digest, trace sanitization, and lifecycle consistency implemented; H1–H10 covered by tests; 302 tests pass; Ruff and `git diff --check` pass |
| AT-03 Deterministic scenario simulator | Not started | One in-memory business scenario, explicit tools, initial state, and objective postconditions |
| AT-04 Policy engine | Not started | Pure allow/block/approval decision logic |
| AT-05 Gated tool executor | Not started | Executor independently validates decisions and refuses unauthorized execution |
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

- AT-03: Deterministic scenario simulator.

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

## Deferred requirements

- AT-02 / AT-07: Task-level aggregation must not count `NO_CHANGE_CONFIRMED` as goal completion. A successfully verified absence of state change for a non-executed action is not equivalent to successful completion of the user's task. Enforce this in the independent verifier and task-level outcome aggregation.
- AT-10: API layer remains deferred until the core CLI workflow is proven.
- AT-12: Real model integration remains optional and deferred.

## Next Up

1. AT-03: Implement the deterministic in-memory scenario.
2. AT-04: Implement pure policy evaluation.
3. AT-05: Implement the gated tool executor.

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