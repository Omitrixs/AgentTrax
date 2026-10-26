# UI Context

## Purpose

The UI is an operator console for inspecting agent actions and verifying outcomes. It should make the policy decision and evidence understandable within a short live demonstration.

## Visual direction

- Dark technical workspace.
- Clear hierarchy, restrained accent colours, compact data density, and readable event traces.
- Use a consistent design system rather than one-off styles.
- If using Tailwind and shadcn/ui, use design tokens and avoid modifying generated foundation components.
- Keep motion subtle and never use animation to imply progress that has not occurred.

## Primary screens

### 1. Demo workspace

- Product header and short explanation.
- Scenario selector.
- Start / reset demo controls.
- Current task objective and explicit success criteria.
- Status summary: running, blocked, awaiting approval, completed, failed, or inconclusive.

### 2. Execution timeline

For each proposed action, display:
- Sequence number and timestamp.
- Tool name and concise argument summary.
- Policy decision badge and reason.
- Whether execution occurred.
- Execution result.
- Verification result.

### 3. Action detail panel

- Full validated action arguments, with sensitive fields redacted.
- Applicable policy and reason code.
- Approval state when relevant.
- Execution evidence.
- Postcondition result.
- Correlation IDs for tracing.

### 4. Policy explanation

- Explain why the action was allowed, blocked, or held for approval.
- Show the rule that matched.
- Avoid implying the policy engine understands all possible risks.

### 5. Task result

Show separate fields for:
- Agent's reported completion.
- Tool execution status.
- Independent verification status.
- Final task status.
- Known limitations or inconclusive checks.

## Status semantics

- `PROPOSED`: action has been suggested but not evaluated.
- `BLOCKED`: action was rejected and did not execute.
- `AWAITING_APPROVAL`: action has not executed and needs approval.
- `ALLOWED`: policy permits execution, but execution may not have occurred yet.
- `EXECUTED`: tool ran; task outcome may still be unverified.
- `VERIFIED`: the relevant postcondition check passed.
- `FAILED`: a defined action or task step failed.
- `INCONCLUSIVE`: available evidence cannot establish success or failure.

Do not collapse these states into a generic green "Success" label.

## Interaction rules

- Destructive or sensitive demo actions must be clearly labelled.
- Approval must identify the exact action and arguments being approved.
- If the action changes after approval, require a new approval.
- The user must be able to inspect the trace without opening developer tools.
- Provide clear reset behaviour for repeatable demos.
- Include accessible contrast, keyboard navigation, and descriptive labels.

## Initial scope

The first backend and deterministic CLI/API demo may precede a full frontend. Do not block core policy engineering on visual polish. Build only the UI needed to demonstrate the currently completed backend features.
