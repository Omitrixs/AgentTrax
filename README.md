
# AgentTrax

AgentTrax is an AI agent runtime verification and safety layer. It checks proposed tool calls against policies, gates sensitive actions behind human approval, executes only allowlisted tools, verifies postconditions independently, and records an auditable trace.

The initial MVP uses a simulated order-management environment. It does not perform real-world actions.

## Development Setup

### Requirements

- Python 3.12
- Git
- PowerShell on Windows, or a compatible terminal

### Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install development dependencies

```powershell
python -m pip install -r requirements-dev.txt
```

### Verify the setup

Run the smoke test:

```powershell
python -m pytest
```

Run lint checks:

```powershell
python -m ruff check .
```

The smoke test should pass, and Ruff should report that all checks passed.

## Project Documentation

These documents define the intended plan and engineering constraints:

- `project-overview.md`: product definition, MVP scope, and success criteria.
- `ai-workflow-rules.md`: rules for AI coding agents and feature-by-feature development.
- `architecture-context.md`: stack, boundaries, lifecycle, contracts, and invariants.
- `code-standards.md`: implementation, validation, testing, and logging standards.
- `ui-context.md`: interface purpose, screens, status semantics, and interaction rules.
- `progress-tracker.md`: actual implementation state, next step, and open questions.
- `security-context.md`: threat model and mandatory security boundaries.
- `feature-registry.md`: feature IDs, dependencies, and acceptance criteria.
- `decisions-log.md`: proposed and accepted architectural decisions.
- `evaluation-plan.md`: benchmark scenarios, metrics, and reporting rules.
- `api-contracts.md`: proposed HTTP interface contracts.
- `demo-plan.md`: short showcase narrative and readiness checklist.

## Development Principles

- The initial MVP is simulator-only. No real-world tool side effects.
- Every tool call must pass through the policy gateway.
- Unknown tools must be rejected.
- Invalid arguments must fail before execution.
- Blocked actions must never execute.
- Human approval must be tied to the exact action payload.
- Verification must use observed state, not model claims.
- Tests must be deterministic and runnable offline.
- Secrets must not be logged.

The documentation describes intended behavior. It does not prove that a feature has been implemented. Keep `progress-tracker.md` aligned with the actual repository and test results.
