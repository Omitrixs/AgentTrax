# AT-10: FastAPI API Layer — Specification and Acceptance-Test Plan

## 1. Feature overview

**Feature ID:** AT-10
**Name:** API Layer
**Status:** Proposed
**Depends on:** AT-09 — End-to-end showcase scenario
**Target:** A thin FastAPI HTTP boundary for the AgentTrax simulator-only showcase.

### Purpose

Expose the existing AgentTrax runtime through a validated HTTP API so a future browser-based showcase can:

- Start a fresh scenario run.
- Retrieve the current run status.
- Inspect a pending approval.
- Approve or deny a pending action.
- Retrieve the run's auditable trace.
- Start a fresh run when the user wants to reset the demonstration.

The API must delegate to existing application and runtime components. It must not duplicate policy, execution, approval, or verification logic.

## 2. Scope

### Included

1. FastAPI application and application factory.
2. Validated Pydantic request and response contracts.
3. Scenario-run/session orchestration using existing runtime components.
4. In-memory run management.
5. Structured error responses.
6. HTTP integration tests using deterministic local components.
7. Local development instructions for starting the API.

### Excluded

- Browser UI or frontend implementation — AT-11.
- Real model-provider integration — AT-12.
- Database or persistent trace storage.
- Authentication, user accounts, or multi-tenancy.
- External tools, real order-management integrations, or real-world side effects.
- Cloud deployment, production hosting, or distributed services.
- New policy rules or changes to the existing approval and verification semantics.

## 3. Architectural requirements

### 3.1 Thin API boundary

The API layer is responsible for:

- Validating incoming requests.
- Resolving the requested run.
- Calling an application/session service.
- Mapping domain results and errors into HTTP responses.

Routes must not directly implement policy evaluation, execute simulator tools, manufacture approval evidence, or determine task verification.

### 3.2 Existing runtime remains authoritative

The existing components remain responsible for their current responsibilities:

- Scenario simulator: simulator state and registered tools.
- Policy engine: `ALLOW`, `BLOCK`, and `REQUIRE_APPROVAL`.
- Gated executor: validates policy/action linkage and controls execution.
- Approval service: approval lifecycle, exact-action binding, expiry, and replay protection.
- Independent verifier: action and task verification.
- Trace recorder: lifecycle events, correlation, ordering, and sanitization.

The API must not create an alternative execution path.

### 3.3 Interactive session orchestration

The API needs a session/application service that composes the existing runtime components for one scenario run.

A run should:

1. Create fresh simulator state and associated runtime services.
2. Execute the deterministic showcase workflow up to its first pending human approval.
3. Preserve the pending action and its approval evidence within that run.
4. Return control to the client while approval is pending.
5. Resume the workflow only after a valid approval decision.
6. Return the actual final task-verification result.

The existing CLI showcase must continue to work independently.

The implementation should reuse existing domain components rather than copy their behavior into the API.

### 3.4 In-memory isolation

Each run must have its own simulator state, approval state, verifier context, and trace recorder.

Run state is in-memory only and is lost when the API process stops.

The run manager must prevent one run from accessing or modifying another run's state. Concurrent access to the same run must not permit duplicate approval or execution.

### 3.5 Local-only boundary

The initial API is a local development/demo service.

- Bind to loopback by default.
- Do not claim production authentication or multi-user isolation.
- Do not expose simulator tools to arbitrary external systems.
- Do not introduce persistent storage or external service dependencies.

## 4. Proposed HTTP contract

Base path: `/api/v1`

### 4.1 Start a scenario run

`POST /api/v1/runs`

Request:

    {
      "scenario_id": "order_refund_support_v1"
    }

Behavior:

- Validate the scenario identifier.
- Create a fresh isolated run.
- Execute the deterministic workflow until it reaches a pending approval or a terminal state.
- Return the run identifier and actual current status.

The client must not submit arbitrary tool names, tool arguments, policy decisions, or execution results.

A new run is also the reset mechanism: the browser starts a new run and switches to its returned identifier. The previous run remains isolated and available until process shutdown.

### 4.2 Retrieve run status

`GET /api/v1/runs/{run_id}`

Return:

- Run identifier.
- Scenario identifier.
- Run status.
- Task-verification status, when available.
- Pending approval summary, when applicable.
- Safe timestamps or other useful run metadata.

The response must distinguish a pending approval from successful task completion.

### 4.3 Approve or deny a pending action

`POST /api/v1/runs/{run_id}/approvals/{action_id}`

Request:

    {
      "decision": "approve"
    }

Allowed decisions:

- `approve`
- `deny`

Behavior:

- Resolve the action from the server-side run state.
- Confirm that it is the currently pending action.
- Use the existing approval service.
- Preserve the existing exact-action digest and policy-version checks.
- Resume the workflow only after a valid approval decision.
- Return the actual updated run status and verification result, where available.

The client must never submit replacement action arguments or approval evidence.

A changed action payload must not inherit the original approval.

Duplicate, expired, mismatched, or otherwise invalid approval attempts must fail closed.

### 4.4 Retrieve trace

`GET /api/v1/runs/{run_id}/trace`

Return the run's recorded lifecycle events in sequence order.

The response must preserve:

- Event identifiers.
- Sequence numbers.
- Event types.
- Task/action correlation where applicable.
- Verification scope.
- Sanitized event details.

The endpoint must not expose secrets or unsanitized internal objects.

## 5. Run status semantics

The API should expose a small, documented set of run-level states.

Proposed states:

- `AWAITING_APPROVAL`: a valid human decision is required before the workflow can continue.
- `RUNNING`: the workflow is actively processing.
- `COMPLETED`: the workflow has reached a terminal state.
- `FAILED`: an execution or application failure prevented normal completion.
- `INCONCLUSIVE`: required verification could not establish a reliable outcome.

Task-verification status must remain a separate field. A completed run must not automatically mean a verified-success task.

The implementation must map these API states from actual domain outcomes. It must not manufacture a verified-success result.

## 6. Structured errors

All API errors must use a consistent response shape.

Proposed format:

    {
      "error": {
        "code": "RUN_NOT_FOUND",
        "message": "The requested run was not found.",
        "request_id": "..."
      }
    }

Expected HTTP mapping:

| Situation | HTTP status |
|---|---:|
| Invalid request body or unknown fields | 422 |
| Unsupported scenario | 404 |
| Unknown run or action | 404 |
| Approval not currently available or duplicate decision | 409 |
| Expired or mismatched approval | 409 |
| Unexpected internal failure | 500 |

Error responses must not contain:

- Python tracebacks.
- Internal filesystem paths.
- Secret values.
- Raw request payloads.
- Sensitive tool arguments.
- Unfiltered exception messages.

Validation errors must not echo sensitive submitted values.

## 7. Proposed package boundary

The implementation should follow the repository's existing `agenttrax` package conventions.

Proposed API package:

    agenttrax/
      api/
        __init__.py
        app.py
        routes.py
        schemas.py
        errors.py
        sessions.py

Proposed tests:

    tests/
      api/
        test_app.py
        test_runs.py
        test_approvals.py
        test_trace.py
        test_errors.py

These are proposed paths, not a requirement to create unnecessary files. Confirm the existing source layout and update architecture documentation before making structural changes.

## 8. Dependencies

- FastAPI for the HTTP application.
- Pydantic for request and response validation.
- An ASGI server such as Uvicorn for local execution.
- Existing pytest and Ruff tooling for validation.

Use compatible dependency versions and avoid adding unrelated infrastructure.

No database, ORM, queue, cloud service, or external tool integration is required.

## 9. Acceptance-test plan

### A. Application and contract tests

**AT10-01 — Application creation**
- Application factory creates a valid FastAPI application.
- Routes are registered under `/api/v1`.
- Importing the API does not start a server or execute the showcase.

**AT10-02 — Request validation**
- Valid scenario request is accepted.
- Missing required fields are rejected.
- Unknown fields are rejected.
- Invalid approval decisions are rejected.
- Arbitrary tool arguments or client-supplied execution results cannot be submitted.

**AT10-03 — Response validation**
- Run responses use the documented schema.
- Pending approval, terminal run status, and task verification are distinguishable.
- Trace responses preserve event sequence and correlation.

### B. Scenario-run tests

**AT10-04 — Start valid run**
- A supported scenario creates a fresh run.
- The run receives an identifier.
- The existing deterministic workflow is used.
- The run reaches the expected pending-approval point.

**AT10-05 — Unsupported scenario**
- An unsupported scenario returns a structured error.
- No simulator state or run is created.

**AT10-06 — Run isolation**
- Two runs have independent simulator state.
- Their approval services and traces are independent.
- An action from one run cannot be approved through another run.

**AT10-07 — Unknown run**
- Unknown run identifiers return a structured 404.
- No runtime component is invoked.

### C. Approval tests

**AT10-08 — Pending approval is not executed**
- The approval-required refund is not executed before human approval.
- The API reports the pending action accurately.

**AT10-09 — Valid approval**
- Approval is processed through the existing approval service.
- The exact pending action is executed through the existing gated executor.
- The workflow resumes.
- Action verification and task verification reflect actual verifier results.

**AT10-10 — Denied approval**
- Denial is processed through the existing approval service.
- The denied action is not executed.
- The run does not falsely report verified task success.

**AT10-11 — Wrong action**
- An action that is not pending cannot be approved.
- No tool execution occurs.

**AT10-12 — Duplicate approval**
- A second approval attempt cannot execute the action again.

**AT10-13 — Expired or mismatched approval**
- Expired or mismatched approval is rejected.
- The action remains unexecuted.
- The API returns a structured conflict response.

**AT10-14 — Approval cannot change action payload**
- Client input cannot replace the pending action's arguments.
- Approval remains bound to the original action digest and policy version.

### D. Policy and execution-boundary tests

**AT10-15 — Blocked action never executes**
- The showcase's blocked refund remains `NOT_EXECUTED`.
- No API route can invoke its simulator tool directly.

**AT10-16 — No execution bypass**
- API operations use the existing session/application service and gated executor.
- Tests verify that blocked and pending actions never reach tool execution.

**AT10-17 — Invalid action fails closed**
- Invalid or unknown actions cannot execute through an API request.

### E. Status and trace tests

**AT10-18 — Status reflects actual runtime state**
- Status changes correctly as the workflow advances.
- Task-verification status comes from the independent verifier.
- A successful tool result alone cannot produce verified task success.

**AT10-19 — Trace retrieval**
- Trace endpoint returns events in sequence order.
- Task/action correlation and verification scope are preserved.
- Trace contents match the actual runtime events.

**AT10-20 — Trace sanitization**
- Sensitive values remain redacted.
- API serialization does not bypass existing trace sanitization.

### F. Error and resilience tests

**AT10-21 — Structured validation errors**
- Invalid requests return the documented error format.

**AT10-22 — Internal errors**
- Unexpected exceptions return a safe 500 response.
- Tracebacks and internal exception details are not exposed.

**AT10-23 — Domain failures**
- Policy, approval, execution, and verification failures remain distinguishable.
- An exception cannot become a success-shaped response.

**AT10-24 — Concurrent approval protection**
- Concurrent attempts to approve the same pending action cannot cause duplicate execution.
- Run state and trace sequencing remain consistent.

### G. Integration and regression tests

**AT10-25 — Complete browser-oriented workflow**
- Start a run.
- Observe the blocked refund.
- Observe the pending approval-required refund.
- Approve the pending action.
- Retrieve the updated status.
- Retrieve the complete trace.
- Confirm final state and task-verification result match the existing showcase behavior.

**AT10-26 — Existing CLI regression**
- `python -m agenttrax.showcase` continues to pass.
- Existing CLI behavior and output semantics remain intact.

**AT10-27 — Offline deterministic tests**
- API tests require no credentials or external network access.
- Tests use isolated deterministic runtime dependencies.

## 10. Feature-level acceptance criteria

AT-10 is complete only when:

1. The FastAPI application starts locally.
2. Request and response models are validated.
3. The documented run, status, approval, and trace operations work.
4. A run can pause for human approval and resume safely.
5. All execution remains behind the existing policy gateway and gated executor.
6. Approval remains bound to the exact pending action.
7. Independent verification remains authoritative.
8. Errors are structured and do not disclose secrets or internal stack traces.
9. Runs remain isolated and in-memory.
10. All AT-10 acceptance tests pass.
11. Existing project tests, Ruff, and `git diff --check` pass.
12. The existing CLI showcase remains functional.
13. Documentation accurately describes the implemented API and its limitations.

## 11. Required validation

Run:

    python -m pytest -p no:cacheprovider -q
    python -m ruff check .
    git diff --check

Also run the existing CLI showcase:

    python -m agenttrax.showcase

Verify the API manually through its OpenAPI documentation and a local HTTP client.

## 12. Implementation boundary

This specification does not authorize implementation yet.

After approval:

1. Inspect the current repository structure and existing runtime composition.
2. Confirm the API package and session-service design against actual source code.
3. Create the AT-10 implementation branch from the synchronized `main`.
4. Implement the API and acceptance tests in small, reviewable steps.
5. Validate and review all changes before completion.

The untracked `AT-05-IMPLEMENTATION-BRIEF.md` must remain untouched.
