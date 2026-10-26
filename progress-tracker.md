# Progress Tracker

Update this file whenever the active feature, implementation status, or an architecture decision changes.

## Current Phase

- Phase 0: Project specification and repository baseline.

## Current Goal

- Record the approved initial scope and development decisions.
- Verify the Python environment and development tooling.
- Complete the remaining AT-01 acceptance criteria before implementing core contracts.

## Project status

The initial project specification and approved decisions are documented. The repository baseline and decision records are committed to Git. No application code or implemented product features have been confirmed yet.

## Feature status

| Feature | Status | Evidence / notes |
|---|---|---|
| AT-00 Project specification | Approved | Simulator-first MVP, initial stack, CLI-first approach, order-management demo, and in-memory-first trace storage approved and recorded |
| AT-01 Repository and environment baseline | Completed | Python 3.12.10 and project-local `.venv` verified; pinned development dependencies installed from `requirements-dev.txt`; smoke test passes (1 test); Ruff passes; README setup instructions added; fresh-clone installation and verification passed |
| AT-02 Core contracts | Not started | Typed action, decision, execution, verification, and trace models |
| AT-03 Deterministic scenario simulator | Not started | One scenario, explicit state and success conditions |
| AT-04 Policy engine | Not started | Pure allow/block/approval decision logic |
| AT-05 Gated tool executor | Not started | Executor refuses calls without a valid allow decision |
| AT-06 Independent verifier | Not started | Verifies observed state and postconditions |
| AT-07 Trace recorder | Not started | Correlated events and secret redaction |
| AT-08 End-to-end demo workflow | Not started | Repeatable scenario showing blocked and successful actions |
| AT-09 API layer | Deferred | Reconsider FastAPI after the core logic |
| AT-10 Dashboard | Not started | Focused UI for trace inspection, if time allows |
| AT-11 Model adapter | Deferred | Real model integration is optional; confirm mock-agent decision before implementation |
| AT-12 Evaluation suite | Not started | Fixed scenarios and measurable metrics |
| AT-13 Showcase hardening | Not started | Clean setup, documented limitations, demo script |

## In Progress

## Completed

- Repository baseline commit created and verified.
- Approved initial decisions recorded in `decisions-log.md`.
- AT-01: Repository and environment baseline. Verified from a fresh Git clone with a new virtual environment, successful dependency installation, 1 passing test, and clean Ruff checks.

## Next Up

1. Begin AT-02: define and test the core contracts, after reviewing the feature requirements and confirming the implementation scope.

## Open Questions

- Should the dashboard be included in the first showcase, or deferred until the core workflow is proven?
- Should trace persistence remain in-memory for the initial demo, with SQLite considered later? Initial decision: in-memory first.
- Should the mock-agent approach be formally accepted as an architectural decision? The real model adapter remains optional.

## Session Notes

- Keep the MVP simulator-only. No real-world tool side effects.
- Do not infer that planned features exist.
- Keep documentation aligned with verified repository state.
- Implement one approved feature at a time.
- Preserve existing Git history and verify changes before committing.
