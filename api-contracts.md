# API Contracts

## Status

Proposed contracts for the optional FastAPI layer. Confirm against implementation before treating them as stable. Core policy logic should not depend on HTTP.

## Design rules

- Use typed request and response schemas.
- Validate all input before state changes.
- Use predictable error shapes.
- Do not accept a client-supplied `verified` or final task status as truth.
- Every mutating operation must check task/action identity and current state.
- Never return secrets or raw internal stack traces.

## Candidate endpoints

### `GET /health`
Returns service readiness only. It must not expose secrets or environment values.

### `GET /scenarios`
Lists available demo scenarios and short descriptions.

### `POST /runs`
Starts a named scenario.

Request fields:
- `scenario_id`: required known scenario identifier.
- `agent_mode`: `mock` by default; provider modes only after they are implemented.
- Optional bounded scenario parameters, if explicitly supported.

Response fields:
- `run_id`
- `scenario_id`
- `status`

### `GET /runs/{run_id}`
Returns current run state and verified task outcome if available.

### `GET /runs/{run_id}/trace`
Returns ordered, redacted trace events for the run.

### `POST /runs/{run_id}/actions/{action_id}/approve`
Approves the exact pending action if approval is required and the action is still valid.

The server must load the stored action rather than trusting a replacement action payload from the client. Approval must fail if the action has changed, expired, already executed, or no longer matches the policy context.

### `POST /runs/{run_id}/reset`
Resets only the isolated simulator run. It must not perform external side effects.

## Error response shape

A consistent error response may contain:
- `error_code`
- `message`
- `request_id`

Do not include stack traces, tokens, or sensitive arguments.

## Contract status rules

- A route is not complete merely because it returns HTTP 200.
- Tests must verify authorization/state constraints as applicable.
- A run status is derived from backend state and verification results.
- API contracts must be updated alongside implementation changes.
