# Decisions Log

Record material architectural or product decisions here. Do not silently change a decision that affects existing features.

## D-001: Simulator-first MVP
**Status:** Proposed, awaiting owner approval

**Decision:** The first showcase uses a deterministic simulated environment rather than real external tools.

**Reasoning:** This allows repeatable demonstrations of policy enforcement and verification without risking real data or requiring external credentials.

**Consequences:** The showcase proves the control flow in a simulator, not production security for arbitrary tools.

## D-002: Mock agent before real model integration
**Status:** Proposed, awaiting owner approval

**Decision:** Core tests and the first end-to-end workflow use a deterministic mock agent. A real model adapter is optional and comes later.

**Reasoning:** Policy and execution correctness should not depend on model availability, nondeterminism, or API spend.

**Consequences:** The first demo can prove the safety and verification architecture but may not yet demonstrate live LLM reasoning.

## D-003: Modular monolith
**Status:** Proposed, awaiting owner approval

**Decision:** Use one Python application with clear modules rather than microservices or a distributed agent framework.

**Reasoning:** The project needs a working, inspectable system quickly. Distributed infrastructure would add complexity before it adds value.

## D-004: Separate policy, execution, and verification
**Status:** Proposed, awaiting owner approval

**Decision:** Policy decides whether an action may execute; the executor performs only approved actions; the verifier independently checks outcomes.

**Reasoning:** These are different responsibilities and must not be collapsed into one model response.

## D-005: No arbitrary execution in MVP
**Status:** Proposed, awaiting owner approval

**Decision:** No shell, arbitrary Python execution, real filesystem mutation, network requests, or production account actions in the initial showcase.

**Reasoning:** The first objective is to demonstrate verifiable controls safely and repeatably.

## Decision template

### D-NNN: Short title
- **Status:** Proposed / Accepted / Superseded
- **Date:**
- **Context:**
- **Decision:**
- **Alternatives considered:**
- **Reasoning:**
- **Consequences:**
- **Related features:**
