# Architecture Context

## Architecture goals

- Keep the policy gateway as the mandatory path for all agent tool actions.
- Separate agent proposal, policy decision, tool execution, and outcome verification.
- Keep the first version local-first and simulator-only.
- Make core behaviour deterministic and testable without a model provider.
- Keep provider integrations replaceable and optional.
- Prefer a modular monolith over distributed services.

## Proposed stack

| Layer | Technology | Role |
|---|---|---|
| Language | Python 3.12 | Backend, policy logic, orchestration, verification |
| API | FastAPI | Thin HTTP boundary for the UI and demo runner |
| Contracts | Pydantic | Validate request, action, decision, and result schemas |
| Tests | pytest | Unit and integration tests |
| Lint | Ruff | Linting and formatting |
| Initial persistence | In-memory first; SQLite only in an explicitly approved feature | Deterministic demo state and optional local trace persistence |
| Frontend | Decide after backend baseline; recommended Next.js + TypeScript if a polished dashboard is needed | Demo UI |
| Agent/model | Deterministic mock agent first; provider adapter later | Repeatable tests and optional natural-language planning |
| Tool environment | Python simulator with explicit registered tools | Safe, controlled execution |
| Version control | Git + GitHub | Change history and reproducibility |

Do not add a database ORM, queue, vector database, agent framework, container platform, or cloud service without an approved requirement.

## Logical components

1. **API layer**: validates inbound requests and delegates to application services.
2. **Scenario registry**: provides named demo scenarios, initial state, available tools, and success criteria.
3. **Agent adapter**: converts a scenario/task into a structured action proposal. Mock implementation is the baseline.
4. **Action contract**: canonical typed representation of a proposed tool call.
5. **Policy engine**: pure decision logic that returns `ALLOW`, `BLOCK`, or `REQUIRE_APPROVAL`, with reason codes.
6. **Approval service**: stores and resolves pending approvals. Approval is bound to the exact action payload and expires.
7. **Tool registry and executor**: executes only explicitly registered simulator tools after an allow decision.
8. **Verifier**: evaluates explicit postconditions against observed simulator state; does not trust the agent's narrative.
9. **Trace recorder**: records correlated events and outcomes while redacting secrets.
10. **Presentation layer**: renders task state, decisions, action details, verification, and trace.

## Request/action lifecycle

`Task Request -> Scenario Validation -> Agent Proposal -> Contract Validation -> Policy Decision -> (Block | Approval | Execute) -> Postcondition Verification -> Trace Finalization`

Important distinctions:
- A **proposal** is not an executed action.
- An **allowed** action is not proof of execution.
- A **successful tool call** is not proof that the user's task succeeded.
- A **verified task** requires the scenario's explicit success conditions to pass.

## System boundaries

- `app/api/`: thin HTTP routes only.
- `app/core/` or `agenttrax/policy/`: policy decisions and reason codes.
- `agenttrax/contracts/`: Pydantic models and shared enums.
- `agenttrax/scenarios/`: scenario definitions, tool registry, simulator state.
- `agenttrax/execution/`: gated tool executor and approval handling.
- `agenttrax/verification/`: postcondition checks and task-level verification.
- `agenttrax/tracing/`: event models, trace recording, redaction.
- `agenttrax/agents/`: mock agent and later provider adapters.
- `tests/`: unit and integration tests mirroring boundaries.
- `frontend/`: only if a separate UI is approved.
- `docs/`: project context files.

Exact package paths may be adjusted to match the repository's actual layout, but update this document before making structural changes.

## Core contracts

Every action proposal must include:
- `action_id`
- `task_id`
- `tool_name`
- `arguments`
- `requested_by` or agent identity
- `created_at` or deterministic test timestamp where appropriate

Every policy decision must include:
- `decision`: `ALLOW`, `BLOCK`, or `REQUIRE_APPROVAL`
- `reason_code`
- human-readable `reason`
- `action_id`
- policy version or identifier

Every execution result must distinguish:
- not executed
- executed successfully
- execution failed

Every verification result must distinguish:
- verified success
- verified failure
- inconclusive / unable to verify

Action-level verification and task-level verification are separate decisions:

- Action-level verification checks the expected transition against observed
  before/after simulator snapshots and reconciles the executor-reported
  result with the observed state.
- Task-level verification evaluates the scenario's explicit objective
  postconditions against the current observed simulator state.
- A successful tool invocation is not sufficient evidence of task success.
- `NO_CHANGE_CONFIRMED` may describe an unchanged state for a non-executed
  action, but it must never count as task-level goal completion.
- Missing evidence, conflicting evidence, and verifier errors must not
  produce verified success.

Use strict schemas and reject unknown fields where practical at trust boundaries.

## Invariants

1. All tool execution goes through the policy gateway.
2. No unknown tool can execute.
3. Invalid arguments fail before execution.
4. `BLOCK` never executes.
5. `REQUIRE_APPROVAL` never executes until a valid approval for the exact action is received.
6. Approval cannot be reused for a materially changed action payload.
7. The verifier evaluates observed state or explicit tool evidence, not model confidence alone.
8. Tool outputs are treated as untrusted data.
9. A trace cannot label a task verified unless the verifier reports success.
10. Core tests run offline with deterministic fakes.
11. No real-world side effects are allowed in the showcase MVP.
12. Secrets are never included in trace payloads.
13. Action-level `NO_CHANGE_CONFIRMED` is not task-level goal completion.
14. Task-level verified success requires the explicit scenario objective
    to be satisfied by observed state.
15. Missing, conflicting, or unverifiable evidence fails closed and cannot
    produce verified success.

## Error handling

- Return structured, predictable errors at API boundaries.
- Do not convert an exception into a success-shaped response.
- Record safe error codes and useful diagnostic context; omit secrets.
- Fail closed if policy evaluation, argument validation, approval verification, or required verification cannot complete.
- Make retries explicit and bounded. Do not automatically repeat non-idempotent actions.

## Growth path

Potential later extensions, each requiring a separate decision:
- Real model adapters.
- Persistent trace storage.
- Multi-user authentication and tenancy.
- External tool adapters with scoped credentials.
- Policy packs and versioned policies.
- Evaluation reports and benchmark comparisons.
- Deployment and billing.

These are not part of the initial implementation by default.
