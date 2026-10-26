# Showcase Demo Plan

## Objective

Show, in under five minutes, that AgentTrax is more than an LLM wrapper: it places enforceable controls around tool use and independently verifies outcomes.

## Demo narrative

**Problem:** A tool-using agent can propose actions that are malformed, disallowed, or incorrectly reported as successful.

**Solution:** AgentTrax evaluates the proposed action, enforces the policy decision, executes only permitted simulator tools, and verifies the resulting state.

## Recommended scenario

Use a simulated customer-support order workflow with synthetic records only.

Example tool catalogue:
- `get_order`: read a synthetic order.
- `add_case_note`: add a note to the simulated case.
- `issue_refund`: simulator-only financial state change, approval-required or policy-limited.
- `close_case`: closes a simulated case only when required evidence exists.

Never connect these tools to a real retailer, payment processor, customer database, or email account in the MVP.

## Suggested five-minute sequence

1. Show the task and the scenario's success criteria.
2. Run a valid read action and show the policy decision.
3. Have the agent propose an invalid or disallowed action and show that the tool was not invoked.
4. Show an approval-required action paused before execution.
5. Approve the exact pending action and show the simulator result.
6. Show the independent verifier checking the final state.
7. Open the trace and explain each event.
8. Show the fixed evaluation suite and report actual results.
9. State the current limitations honestly.

## What to say

"AgentTrax does not make a language model inherently trustworthy. It adds a defined control point around the actions the agent can take, then verifies whether the expected result occurred. This demo proves those controls in a simulator. Production integrations would require separate threat modelling, permission design, and security testing."

## Demo readiness checklist

- [ ] Clean setup works.
- [ ] Scenario reset works.
- [ ] Demo is deterministic or nondeterminism is clearly controlled.
- [ ] A blocked action never executes.
- [ ] Approval is required where expected.
- [ ] Modified approval payload is rejected.
- [ ] Verification is based on simulator state.
- [ ] Trace is readable and redacted.
- [ ] Test results are actual and reproducible.
- [ ] No API key or secret is visible.
- [ ] Limitations are documented.
