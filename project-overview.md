# AgentTrax

## Overview

AgentTrax is a runtime verification and safety layer for AI agents that use tools. It sits between an agent and the tools it can call, evaluates proposed actions against explicit policies, records decisions, and verifies whether the intended result actually occurred.

**Product promise:** Let AI agents act within defined boundaries, and make their actions inspectable and verifiable.

AgentTrax is not a guarantee that an agent is safe, correct, or secure. It is a control and verification layer whose protections must be tested against a defined threat model.

## Problem

AI agents can select tools, generate arguments, and chain actions. A plausible model response does not prove that an action is safe or that a task succeeded. Applications need a consistent place to validate actions, enforce permissions, check outcomes, and retain an audit trail.

## Initial target users

- AI engineers prototyping tool-using agents.
- Small software teams adding agent workflows to internal tools.
- Developers who need a demonstrable policy and verification layer without building one from scratch.

The initial showcase uses a simulated order-management environment. No real customer data, payments, emails, or external destructive operations are involved.

## Core workflow

1. A user selects a demo scenario and starts an agent task.
2. The agent proposes a structured tool call.
3. AgentTrax validates the action and its arguments.
4. A policy decision is returned: `ALLOW`, `BLOCK`, or `REQUIRE_APPROVAL`.
5. Allowed actions run only against registered simulator tools.
6. An independent verifier checks the postconditions.
7. The event log records the proposal, decision, execution result, verification result, and reason.
8. The UI shows the full trace and whether the task's success criteria were actually met.

## Product principles

1. **Policy before execution:** every tool call passes through the policy gateway.
2. **Verify outcomes independently:** a model saying "done" is not evidence of completion.
3. **Fail closed:** invalid, unknown, or malformed actions do not execute.
4. **Least privilege:** agents receive only the tools and arguments required for the scenario.
5. **Human control:** sensitive actions can require explicit approval.
6. **Observable decisions:** explain why an action was allowed, blocked, or escalated.
7. **Honest claims:** report only checks that actually ran and results actually observed.
8. **Small, testable increments:** ship a narrow simulator-based MVP before adding external integrations.

## MVP scope

### In scope

- One simulated business environment with a small, explicit tool catalogue.
- Structured agent action proposals.
- Central policy gateway with allow, block, and approval-required outcomes.
- Input/schema validation and basic precondition checks.
- Simulated tool execution.
- Independent postcondition verification.
- Append-only in-memory or SQLite event trace, depending on the persistence feature approved.
- A focused dashboard showing task status, action decisions, execution results, and verification.
- Deterministic tests and a repeatable demo scenario.
- A mock agent for offline, repeatable demos; a real model adapter is optional and must not be required for core tests.

### Out of scope for the first showcase

- Connecting to production business systems.
- Executing arbitrary shell commands or arbitrary code.
- Autonomous financial transactions, sending real emails, or deleting real data.
- Claiming comprehensive prompt-injection protection.
- Multi-tenant production SaaS, billing, enterprise SSO, or complex RBAC.
- Training a foundation model.
- Multiple independent agents unless a tested need emerges.
- Broad claims of certification or regulatory compliance.

## Success criteria

The MVP is successful when:

1. Every proposed tool action reaches the policy gateway before execution.
2. Unknown tools and invalid arguments are rejected without execution.
3. A forbidden action is blocked and the reason is visible in the trace.
4. An approval-required action cannot execute before explicit approval.
5. A permitted simulator action executes and its outcome is independently checked.
6. The system distinguishes tool execution success from task success.
7. The trace contains enough information to reconstruct the decision path without storing secrets.
8. The demo can be reset and repeated with deterministic expected results.
9. Automated tests cover policy decisions, argument validation, execution boundaries, and verification.
10. Documentation clearly describes limitations and the threat model.

## Product language

Use: "policy enforcement", "action verification", "auditable execution trace", "simulated environment", and "tested controls".

Avoid unsupported claims such as: "makes any agent safe", "prevents all prompt injection", "guarantees correctness", or "fully secure".
