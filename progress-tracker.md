# Progress Tracker

Update this file whenever the active feature, implementation status, or an architecture decision changes.

## Current Phase

- Phase 0: Project specification and scope definition.

## Current Goal

- Review and approve the context files.
- Inspect the actual repository before claiming any implementation is complete.
- Establish a minimal, reproducible project baseline.

## Project status

No AgentTrax implementation status is assumed by this document. Mark a feature complete only after inspecting the repository and running the required checks.

## Feature status

| Feature | Status | Evidence / notes |
|---|---|---|
| AT-00 Project specification | In review | Context files drafted; owner approval required |
| AT-01 Repository and environment baseline | Not started | Inspect actual files, Python version, dependencies, Git status |
| AT-02 Core contracts | Not started | Typed action, decision, execution, verification, trace models |
| AT-03 Deterministic scenario simulator | Not started | One scenario, explicit state and success conditions |
| AT-04 Policy engine | Not started | Pure allow/block/approval decision logic |
| AT-05 Gated tool executor | Not started | Executor refuses calls without valid allow decision |
| AT-06 Independent verifier | Not started | Verifies observed state and postconditions |
| AT-07 Trace recorder | Not started | Correlated events and secret redaction |
| AT-08 End-to-end demo workflow | Not started | Repeatable scenario showing blocked and successful actions |
| AT-09 API layer | Not started | Thin FastAPI endpoints, if approved after core logic |
| AT-10 Dashboard | Not started | Focused UI for trace inspection, if time allows |
| AT-11 Model adapter | Deferred | Mock agent remains sufficient for core tests |
| AT-12 Evaluation suite | Not started | Fixed scenarios and measurable metrics |
| AT-13 Showcase hardening | Not started | Clean setup, documented limitations, demo script |

## In Progress

- None.

## Completed

- None confirmed yet.

## Next Up

1. Confirm the repository path and inspect current files.
2. Approve the product scope and initial stack.
3. Implement AT-01 only.
4. Run and record environment checks before proceeding.

## Open Questions

- Will the initial showcase use a CLI-only demo, a FastAPI endpoint, or a separate web dashboard?
- Is the repository already created, and what is its current path?
- Which Python version and package manager are installed in the target environment?
- Is a live model API available, or should the showcase remain fully offline with a deterministic mock agent?
- Which exact demo scenario should be the flagship: order cancellation/refund, customer-support case handling, or another simulated workflow?

## Session Notes

- Do not infer that planned features exist.
- Keep the MVP simulator-only. No real-world tool side effects.
- Update this tracker after each approved feature.
