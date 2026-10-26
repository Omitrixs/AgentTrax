# AI Workflow Rules

## Approach

Build AgentTrax incrementally using a spec-driven workflow. The context files define what to build, how to build it, what is protected, and what is actually complete. Read the relevant docs before changing code.

## Scoping rules

- Implement one feature unit at a time.
- Prefer small changes that can be tested end to end.
- Do not combine unrelated backend, UI, persistence, and provider-integration changes in one task.
- Do not silently add features, dependencies, services, or architectural patterns.
- Do not replace a working implementation merely because another approach is fashionable.
- Preserve the user's existing work and inspect repository state before editing.

## Before implementation

1. Read `project-overview.md`, `architecture-context.md`, `code-standards.md`, and `progress-tracker.md`.
2. Read `security-context.md` before touching tools, policies, execution, approvals, logs, or external integrations.
3. Read `feature-registry.md` and identify the exact feature ID and acceptance criteria.
4. Inspect the current code and tests. Do not assume files or features exist because a plan mentions them.
5. State the intended files and narrow scope before making broad changes.
6. If requirements are missing, record an open question in `progress-tracker.md`; do not invent security-sensitive behaviour.

## During implementation

- Keep changes within the approved feature.
- Do not weaken a policy, test, type, validation rule, or approval gate to make a demo pass.
- Never let an agent call a tool directly while bypassing the policy gateway.
- Do not execute arbitrary repository code, shell commands, or user-provided scripts in the MVP.
- Treat model output and all user-supplied content as untrusted input.
- Do not log API keys, tokens, passwords, full secrets, or unnecessary personal data.
- Use deterministic fakes for core tests. Tests must not require paid API access or a network connection.
- If an implementation reveals a required architecture change, stop and propose the change before proceeding.

## Verification requirements

For each feature:
1. Run the narrow relevant tests.
2. Run the full test suite when practical.
3. Run lint/type checks available in the project.
4. Inspect the diff for unrelated edits, leaked secrets, unsafe execution paths, and misleading success states.
5. Confirm each acceptance criterion with evidence.
6. Update `progress-tracker.md` and any affected context file.
7. Report commands run and actual results. Never claim a test passed if it was not run.

## Feature freeze

When the user marks a feature complete or frozen:
- Do not edit, refactor, rename, or reinterpret it without explicit approval.
- If a later feature needs a change to frozen code, explain why and request permission.
- A passing test does not grant permission to expand scope.

## Missing or conflicting instructions

- If docs conflict, `project-overview.md` defines product scope, `architecture-context.md` defines system boundaries, and `security-context.md` controls safety-sensitive behaviour.
- `feature-registry.md` defines feature scope and acceptance criteria.
- `progress-tracker.md` reports actual implementation status, not intended status.
- Record unresolved conflicts in `progress-tracker.md` under Open Questions and ask the owner when the conflict blocks implementation.

## Before moving to the next feature

- The feature's acceptance criteria are met.
- Tests and checks have been run and their results recorded.
- Architecture and security invariants remain intact.
- Documentation reflects the actual implementation.
- The user has reviewed the result and approved the next feature.
