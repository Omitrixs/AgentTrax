# Decisions Log

Record material architectural or product decisions here. Do not silently change a decision that affects existing features.

## D-001: Simulator-first MVP
**Status:** Accepted

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
**Status:** Accepted

**Decision:** No shell, arbitrary Python execution, real filesystem mutation, network requests, or production account actions in the initial showcase.

**Reasoning:** The first objective is to demonstrate verifiable controls safely and repeatably.

## D-006: Initial development stack
**Status:** Accepted

**Decision:** Use Python 3.12, Pydantic, pytest, Ruff, and a Python virtual environment for the initial implementation.

**Reasoning:** This provides typed data contracts, automated tests, code-quality checks, and an isolated development environment.

**Consequences:** The initial setup and verification steps must use this stack.

## D-007: CLI-first interface
**Status:** Accepted

**Decision:** Begin with a command-line workflow. Defer the FastAPI decision until after the core logic is implemented.

**Reasoning:** This prioritizes validating the core control flow before adding an API layer.

**Consequences:** The initial implementation must be usable without a web server or dashboard.

## D-008: Flagship demo scenario
**Status:** Accepted

**Decision:** Use a simulated order-management workflow demonstrating blocked and permitted actions.

**Reasoning:** This gives the MVP a concrete scenario for demonstrating policy enforcement and verification.

**Consequences:** Scenario behavior and expected outcomes must be deterministic and testable.

## D-009: Initial trace storage
**Status:** Accepted

**Decision:** Begin with in-memory trace storage. Consider SQLite when the persistence feature is addressed.

**Reasoning:** In-memory storage keeps the initial implementation small and focused.

**Consequences:** Initial traces will not persist across application restarts.

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
