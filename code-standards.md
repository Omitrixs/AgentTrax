# Code Standards

## General

- Use small, single-purpose modules and functions.
- Fix root causes rather than adding workarounds.
- Keep policy decisions pure where possible.
- Separate policy evaluation from tool execution.
- Keep API routes thin; place business logic in application services.
- Avoid unnecessary abstractions and speculative generality.
- Do not introduce a dependency without explaining the need and obtaining approval.

## Python

- Target Python 3.12.
- Add type annotations to public functions and important internal contracts.
- Use Pydantic models for untrusted API input and structured action contracts.
- Prefer explicit enums and reason codes over magic strings.
- Use `pathlib` for paths and standard-library functionality where sufficient.
- Use `logging` rather than scattered debug prints in application code.
- Avoid broad `except Exception` unless at a deliberate system boundary with safe handling and logging.
- Do not use `eval`, `exec`, dynamic imports from user input, or arbitrary shell execution.
- Do not use `assert` for runtime security checks. Assertions are suitable for tests and internal invariants only.
- Keep functions deterministic when they represent policy or verification logic.

## Contracts and validation

- Validate all external input before business logic.
- Treat model-generated tool names and arguments as untrusted.
- Reject unknown tools, missing required fields, invalid types, and out-of-range values.
- Use explicit action and decision schemas.
- Avoid accepting a client-supplied status such as `verified=true` as evidence of verification.
- Do not trust IDs supplied by the client without checking they belong to the current task/session.

## Policy and execution

- Policy evaluation returns a decision; it does not execute tools.
- Tool executors must independently confirm that the policy decision permits execution.
- Unknown or malformed policy results fail closed.
- Keep the tool catalogue explicit and allowlisted.
- Require approval for actions designated sensitive by the scenario policy.
- Bind approval to the exact action hash/payload and relevant policy version.
- Prevent duplicate execution when a request is retried, where practical.
- No real external side effects in the MVP.

## Logging and privacy

- Never log secrets, bearer tokens, API keys, passwords, or raw credentials.
- Prefer identifiers, reason codes, and redacted argument summaries over full payloads.
- Do not collect personal data that the demo does not need.
- Keep logs useful but minimal.
- Do not expose stack traces or internal exception details to end users in production-shaped responses.

## Testing

- Test allowed, blocked, and approval-required paths.
- Test unknown tool, invalid arguments, malformed model output, and verifier failure.
- Test that blocked actions do not call the executor.
- Test that approval cannot authorize a changed payload.
- Test that task success is not inferred from a successful model response.
- Use deterministic fakes for model and tools.
- Keep tests independent of live API keys and external services.
- Add regression tests for every fixed bug.

## API design

- Use typed request and response models.
- Return consistent status codes and response structures.
- Validate request size and enumerated values.
- Keep handlers focused on HTTP concerns.
- Do not reveal secrets or internal stack traces in error responses.

## UI standards, if a frontend is added

- Use TypeScript strict mode.
- Avoid `any`; model API responses explicitly.
- Validate data received from APIs.
- Separate UI composition from business logic.
- Show the difference between proposed, blocked, awaiting approval, executed, and verified.
- Never display a green success state unless the corresponding verification result actually passed.
- Include loading, empty, error, and inconclusive states.

## Definition of done

A feature is done only when its acceptance criteria are met, tests and relevant checks have run, the diff is reviewed, documentation is updated, and the user has approved its completion.
