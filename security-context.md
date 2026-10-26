# Security Context

## Purpose

This document defines the minimum security boundaries for the AgentTrax MVP. It is a scoped engineering checklist, not a security certification or proof that all threats are mitigated.

## Threat model

### Assets to protect

- Integrity of simulated or future tool actions.
- Policy rules and approval decisions.
- User credentials and provider API keys.
- Trace integrity and task state.
- Confidential user inputs and tool outputs.

### Trust boundaries

- User input to the application.
- Model output to action contracts.
- Action proposal to policy decision.
- Policy decision to tool execution.
- Tool output to verification logic.
- Approval request to approval resolution.
- API client to server state.
- Logs and trace storage.

### Main threats

- Model emits malformed or unexpected tool arguments.
- Prompt injection attempts to persuade the agent to bypass policy.
- Unknown tools are invoked.
- A blocked action executes due to a code path that bypasses the gateway.
- Approval is reused after the action payload changes.
- Tool output contains misleading instructions or untrusted text.
- Duplicate requests cause repeated actions.
- Sensitive information leaks into logs.
- A claimed success is accepted without independent evidence.
- A demo or future adapter accidentally performs real-world side effects.

## Required controls for the MVP

1. Explicit allowlist of registered tools.
2. Strict argument schemas and bounds.
3. Central policy evaluation before execution.
4. Executor-side validation of the decision and action identity.
5. Fail-closed behaviour on invalid or unavailable policy decisions.
6. Approval bound to the exact action payload; changed payload requires new approval.
7. Simulator-only tools with no network, filesystem mutation, shell, or external account access.
8. Independent postcondition verification.
9. Safe, redacted trace logging.
10. Deterministic tests proving blocked and unapproved actions do not execute.
11. No secrets committed to version control.
12. Model output and tool output treated as untrusted data.

## Approval semantics

- Approval is an explicit user action, not a model-generated string.
- Approval applies only to the exact pending action, including tool name and arguments.
- Expired, missing, duplicated, or mismatched approvals are rejected.
- Any material change to arguments or policy context invalidates the approval.
- In the MVP, approval must not grant permission to escape the simulator.

## Logging

Record:
- task and action IDs,
- tool name,
- policy decision and reason code,
- execution status,
- verification status,
- timestamps or deterministic test sequence,
- safe error category.

Do not record:
- API keys, passwords, bearer tokens, session cookies,
- full credentials or secrets embedded in arguments,
- unnecessary personal data,
- raw provider request headers.

## Explicit non-goals

The MVP does not claim:
- complete prevention of prompt injection,
- general-purpose sandboxing,
- protection against a compromised host or dependency,
- safety of arbitrary external tools,
- compliance with a particular regulation,
- suitability for production use without a separate security review.

## Security acceptance tests

- Unknown tool is blocked and never invoked.
- Invalid arguments are rejected before tool execution.
- Blocked action does not reach the tool executor.
- Approval-required action does not execute before approval.
- Approval for one payload cannot authorize a modified payload.
- Verifier errors result in `INCONCLUSIVE` or failure, never verified success.
- Logs contain no test secret planted in a sensitive field.
- No MVP tool can access the real network, run shell commands, or mutate real user files.
