# AgentTrax AT-02: Core Contracts (Revision 4)

Status: **Approved for implementation. No AT-02 code has been written yet.**

Revision 4 tightens nested-data immutability, trace size and truncation
semantics, identifier validation, and uniqueness wording. It preserves
the resolved Revision 4 decisions and does not authorize implementation.

This revision keeps AT-02 limited to defining and validating contracts.
It does not implement the policy engine, executor, approval workflow,
simulator, verifier, or task-level aggregation.

One important distinction: a valid contract is not permission to execute
an action. Authorization, execution, approval, and verification remain
separate responsibilities.

## Changes from revision 2

  ---------------------------------------------------------------------
  Area                               Change
  ---------------------------------- ----------------------------------
  Limits                             Argument limits are named
                                     constants, retaining 64 KiB and
                                     depth 10.

  Proposal digest                    Covers `action_id`, `task_id`,
                                     `tool_name`, `arguments`, and
                                     `requested_by`. Excludes
                                     `created_at`. Canonicalization is
                                     versioned.

  Execution result                   New `NotExecutedReason` enum and
                                     `not_executed_reason` field,
                                     required only when `status` is
                                     `NOT_EXECUTED`.

  Verification result                New reason codes
                                     `NO_CHANGE_CONFIRMED` and
                                     `UNEXPECTED_STATE_CHANGE` with
                                     defined status pairings.

  Lifecycle check                    Now checks reason consistency,
                                     proposal digest integrity, and
                                     verification consistency. It does
                                     not force every approval-related
                                     non-execution into
                                     `APPROVAL_PENDING`.

  Tests                              Every new rule and edge case has a
                                     listed test (Section I).

  Nested data                        Contract-owned nested JSON data is
                                     recursively immutable after
                                     validation; canonicalization uses
                                     a plain JSON projection.

  Decisions                          All four open decisions are marked
                                     resolved, with rationale (Section
                                     5 and Section 6).

  Deferred requirement               Task-level aggregation must not
                                     count `NO_CHANGE_CONFIRMED` as
                                     goal completion. Recorded for the
                                     later verifier feature (Section
                                     3).
  ---------------------------------------------------------------------

## Changes from revision 3

-   Recursively immutable nested contract data, not only frozen
    top-level models and copied inputs. Canonical JSON serialization
    must preserve object/array semantics.
-   `TRACE_STRING_MAX_CHARS` now caps the final stored string including
    the truncation suffix.
-   Trace-details byte size is measured on the canonical JSON UTF-8
    encoding of the details object, after sanitization and truncation.
-   Added `PROPOSAL_DIGEST_HEX_LENGTH = 64` as a named constant.
-   All fields described as non-empty strings are clarified as
    non-blank: whitespace-only values are rejected without silently
    stripping valid input.
-   `action_id` and `event_id` uniqueness is explicitly assigned to the
    later lifecycle/trace-recording component; standalone contract
    models validate shape only.

## 1. Review of design choices

  -----------------------------------------------------------------------
  Design choice           Alignment with existing Decision
                          documents
  ----------------------- ----------------------- -----------------------
  Strict schema           Rejects unknown fields, Confirmed
  validation              invalid types, and
                          malformed input at
                          trust boundaries.

  Timezone-aware UTC      Fits the architecture's Confirmed
  timestamps              timestamp fields and
                          deterministic testing
                          requirements.

  Structured trace        Matches traceability    Confirmed
  details with sensitive  requirements while
  values redacted         preserving the rule
                          against logging secrets
                          or unnecessary personal
                          data.
  -----------------------------------------------------------------------

## 2. Contract specification

### A. Contract design rules

1.  **Strict validation:** reject unknown fields, type coercion, missing
    required fields, and invalid values. Models use `extra="forbid"` and
    `strict=True`.
2.  **Explicit types:** Pydantic models and Python enums for all
    structured contracts and status values.
3.  **UTC timestamps:** every contract timestamp must be timezone-aware.
    Naive datetimes and ISO strings without an offset are rejected.
    Aware non-UTC values are converted to UTC, and the stored value
    always has `tzinfo == timezone.utc`. Tests use fixed timestamps,
    never the current clock.
4.  **Safe trace data:** structured details, redacted per Section G,
    never containing secrets.
5.  **Separation of responsibilities:** proposals, policy decisions,
    execution results, verification results, and trace events are
    distinct types.
6.  **No implicit authorization:** parsing or validating a contract
    never authorizes execution.
7.  **Immutability:** all contracts are frozen, and all nested JSON
    containers owned by a contract are recursively immutable after
    validation. Construction must copy input before freezing it. A
    caller must not be able to mutate nested data through either the
    original input or a reference obtained from the contract. Preserve
    JSON semantics: input objects remain JSON objects and input arrays
    remain JSON arrays when canonicalized or serialized. The
    canonicalization helper must produce a plain JSON projection without
    changing values or their types. The proposal digest remains an
    integrity check, not a substitute for immutability.
8.  **Invariants live at two levels:** rules involving one contract are
    enforced by that model's validators. Rules that span contracts are
    enforced by a pure function, `check_lifecycle_consistency` (Section
    H).
9.  **Named constants:** every numeric limit and fixed format length in
    this specification is a named module-level constant, never an
    unexplained inline literal. This includes
    `PROPOSAL_DIGEST_HEX_LENGTH = 64` and
    `DIGEST_CANONICALIZATION_VERSION = 1`.

### B. JSON-compatible data and limits

A `JsonValue` is one of: `str`, `int`, `float`, `bool`, `None`, a list
of `JsonValue`, or a dict with `str` keys and `JsonValue` values.

-   Rejected: `NaN`, `Infinity`, tuples, sets, `bytes`, `datetime`,
    `Decimal`, non-string keys, and custom objects.
-   `bool` stays `bool` and is never coerced to or from `int`.

**Named limits for `arguments`, `result`, and `evidence`:**

  -----------------------------------------------------------------------
  Constant                Value                   Meaning
  ----------------------- ----------------------- -----------------------
  `MAX_ARGUMENT_BYTES`    `65536` (64 KiB)        Maximum size of the
                                                  canonical JSON
                                                  encoding, in UTF-8
                                                  bytes.

  `MAX_ARGUMENT_DEPTH`    `10`                    Maximum nesting depth.
                                                  The top-level object
                                                  counts as depth 1. A
                                                  list or dict nested
                                                  inside it adds one
                                                  level.
  -----------------------------------------------------------------------

-   Size is measured in bytes of the canonical JSON encoding defined in
    Section C, encoded as UTF-8, not in characters. This is the same
    serializer and options used by the proposal digest, applied to the
    trace `details` object itself. The size check runs after redaction
    and truncation.
-   A value exactly at a limit is accepted. A value one over the limit
    is rejected.
-   Later tool contracts may impose tighter per-tool limits. Nothing may
    loosen these without a specification change.

**Named limits for trace `details` (intentionally tighter):**

  Constant                    Value
  --------------------------- ----------------
  `TRACE_DETAILS_MAX_BYTES`   `8192` (8 KiB)
  `TRACE_DETAILS_MAX_DEPTH`   `5`
  `TRACE_STRING_MAX_CHARS`    `512`

### C. Contract 1: Action proposal

Represents an action requested by an agent. It does not indicate the
action is allowed or has been executed.

  -----------------------------------------------------------------------
  Field                  Type                     Requirement
  ---------------------- ------------------------ -----------------------
  `action_id`            Non-blank string         Required; uniqueness is
                                                  checked by the
                                                  lifecycle component,
                                                  not by this standalone
                                                  model

  `task_id`              Non-blank string         Required

  `tool_name`            Non-blank string         Required

  `arguments`            `dict[str, JsonValue]`   Required, bounded per
                                                  Section B

  `requested_by`         Non-blank string         Required

  `created_at`           UTC datetime             Required
  -----------------------------------------------------------------------

String validation rule: every field specified as a non-blank string must
contain at least one non-whitespace character. Leading or trailing
whitespace is not silently stripped; the original value is retained if
otherwise valid.

Rules:

-   Tool-specific argument validation stays with later tool contracts
    and the execution boundary.
-   `requested_by` is a free-text label, not proof of identity or
    authorization. A dedicated identity contract is a future decision.

**Proposal digest**

`compute_proposal_digest(proposal)` returns the lowercase hexadecimal
SHA-256 of the canonical JSON of exactly these five fields. Its output
length is `PROPOSAL_DIGEST_HEX_LENGTH` characters:

`action_id`, `task_id`, `tool_name`, `arguments`, `requested_by`

`created_at` is excluded. It is metadata, not an input to a policy
decision or to execution. Including it would give identical logical
proposals different digests on retry. Replay protection is the job of
`action_id` uniqueness, not the digest.

**Canonicalization, version 1** (`DIGEST_CANONICALIZATION_VERSION = 1`):

-   Keys sorted at every nesting level.
-   No insignificant whitespace (separators `,` and `:`).
-   UTF-8 encoding, with non-ASCII characters left unescaped.
-   `NaN` and `Infinity` rejected.
-   Integers and floats are distinct (`1` and `1.0` encode differently
    and therefore produce different digests).

The function is pure, offline, and deterministic. If canonicalization
ever changes, it must become version 2, and the policy decision contract
must then gain a field that records which version produced a stored
digest. AT-02 does not add that field now.

### D. Contract 2: Policy decision

Represents the policy engine's decision about a specific action.

  -------------------------------------------------------------------------------
  Field               Type                                     Requirement
  ------------------- ---------------------------------------- ------------------
  `action_id`         Non-blank string                         Required

  `proposal_digest`   `PROPOSAL_DIGEST_HEX_LENGTH`-character   Required, binds
                      lowercase hexadecimal string             the decision to
                                                               the exact proposal
                                                               content

  `decision`          Enum                                     Required

  `reason_code`       `PolicyReasonCode`                       Required

  `reason`            Non-blank string                         Required

  `policy_version`    Non-blank string                         Required
  -------------------------------------------------------------------------------

`decision` is exactly `ALLOW`, `BLOCK`, `REQUIRE_APPROVAL`.

**`PolicyReasonCode` members:** `ALLOWED_BY_POLICY`,
`BLOCKED_BY_POLICY`, `APPROVAL_REQUIRED`, `UNKNOWN_TOOL`,
`INVALID_ARGUMENTS`, `MALFORMED_DECISION`.

**Decision/reason consistency (enforced by a model validator):**

  ---------------------------------------------------------------------
  `decision`                         Allowed `reason_code` values
  ---------------------------------- ----------------------------------
  `ALLOW`                            `ALLOWED_BY_POLICY`

  `REQUIRE_APPROVAL`                 `APPROVAL_REQUIRED`

  `BLOCK`                            `BLOCKED_BY_POLICY`,
                                     `UNKNOWN_TOOL`,
                                     `INVALID_ARGUMENTS`,
                                     `MALFORMED_DECISION`
  ---------------------------------------------------------------------

Invariants:

-   `BLOCK` means the action must not execute.
-   `REQUIRE_APPROVAL` means the action must not execute until a valid
    approval is established by the later approval workflow.
-   `ALLOW` is a decision, not proof that execution succeeded.
-   The executor must independently confirm that `action_id` matches and
    that `proposal_digest` equals the digest of the exact proposal it is
    about to run. A mismatch is a contract violation.

### E. Contract 3: Execution result

Represents what happened when an action reached the execution boundary.

  ------------------------------------------------------------------------
  Field                   Type                     Requirement
  ----------------------- ------------------------ -----------------------
  `action_id`             Non-blank string         Required

  `status`                Enum                     Required

  `result`                `dict[str, JsonValue]`   Optional, safe output,
                          or `None`                bounded per Section B

  `error_code`            `ExecutionErrorCode` or  See table
                          `None`

  `not_executed_reason`   `NotExecutedReason` or   See table
                          `None`

  `completed_at`          UTC datetime             Required
  ------------------------------------------------------------------------

`status` is exactly `NOT_EXECUTED`, `SUCCEEDED`, `FAILED`.

**`ExecutionErrorCode` members:** `TOOL_ERROR`, `TIMEOUT`,
`INVALID_RESULT`, `INTERNAL_ERROR`.

**`NotExecutedReason` members:**

  ---------------------------------------------------------------------
  Member                             Meaning
  ---------------------------------- ----------------------------------
  `POLICY_BLOCKED`                   The policy decision was `BLOCK`.

  `APPROVAL_PENDING`                 Approval was required and has not
                                     yet been resolved.

  `APPROVAL_DENIED`                  Approval was required and was
                                     denied.

  `APPROVAL_EXPIRED`                 Approval was required and expired
                                     before use.

  `INTEGRITY_CHECK_FAILED`           The executor refused to run the
                                     action because an `action_id` or
                                     `proposal_digest` check failed.
  ---------------------------------------------------------------------

`NotExecutedReason` is a coarse category, not free text, so it cannot
carry sensitive data. The `APPROVAL_*` members exist so the lifecycle
can be described precisely. AT-02 does not implement approval behavior.

**Per-status field rules (enforced by a model validator):**

  `status`         `result`         `error_code`     `not_executed_reason`
  ---------------- ---------------- ---------------- -----------------------
  `NOT_EXECUTED`   must be `None`   must be `None`   **required**
  `SUCCEEDED`      optional         must be `None`   must be `None`
  `FAILED`         must be `None`   required         must be `None`

Notes:

-   `SUCCEEDED` means the tool completed, not that the outcome was
    verified.
-   `NOT_EXECUTED` is distinct from `FAILED`, which means execution
    began and failed.
-   `result` must not contain credentials, tokens, raw provider headers,
    or unnecessary personal data.

### F. Contract 4: Verification result

Represents the independent verifier's assessment of the action's
observed outcome.

  Field           Type                               Requirement
  --------------- ---------------------------------- -------------
  `action_id`     Non-blank string                   Required
  `status`        Enum                               Required
  `reason_code`   `VerificationReasonCode`           Required
  `reason`        Non-blank string                   Required
  `evidence`      `dict[str, JsonValue]` or `None`   See table
  `verified_at`   UTC datetime                       Required

`status` is exactly `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`,
`INCONCLUSIVE`.

**`VerificationReasonCode` members and status pairings (enforced by a
model validator):**

  -------------------------------------------------------------------------
  `status`              Allowed `reason_code` values  `evidence`
  --------------------- ----------------------------- ---------------------
  `VERIFIED_SUCCESS`    `OUTCOME_MATCHES_EXPECTED`,   required
                        `NO_CHANGE_CONFIRMED`

  `VERIFIED_FAILURE`    `OUTCOME_MISMATCH`,           required
                        `UNEXPECTED_STATE_CHANGE`

  `INCONCLUSIVE`        `EVIDENCE_MISSING`,           optional
                        `EVIDENCE_CONFLICTING`,
                        `VERIFIER_ERROR`
  -------------------------------------------------------------------------

Meaning of the two new codes:

-   `NO_CHANGE_CONFIRMED`: the verifier observed that state is
    unchanged, as expected for an action that never executed. It pairs
    only with `VERIFIED_SUCCESS`.
-   `UNEXPECTED_STATE_CHANGE`: the verifier observed a state change that
    should not exist, for example after an action that never executed.
    It pairs only with `VERIFIED_FAILURE`.

Invariants:

-   Verification is based on observed state or evidence, never an
    agent's claim.
-   Execution success does not imply verification success.
-   `INCONCLUSIVE` stays distinct from success and failure.
-   A task cannot be represented as verified successful unless the
    verifier reports `VERIFIED_SUCCESS`.
-   `NO_CHANGE_CONFIRMED` confirms that nothing changed. It does not
    mean the task's goal was achieved. See the deferred requirement in
    Section 3.
-   Evidence follows the same redaction and bounds rules as trace
    details.

Cross-contract rules for verification against execution status are
enforced by the lifecycle check (Section H).

### G. Contract 5: Trace event

Represents one structured event in the auditable action lifecycle.

  -----------------------------------------------------------------------
  Field                  Type                     Requirement
  ---------------------- ------------------------ -----------------------
  `event_id`             Non-blank string         Required; uniqueness is
                                                  checked by the
                                                  lifecycle component,
                                                  not by this standalone
                                                  model

  `task_id`              Non-blank string         Required

  `action_id`            Non-blank string or      Optional for task-level
                         `None`                   events

  `event_type`           `TraceEventType`         Required

  `sequence`             Positive integer         Required, orders events
                                                  within a task

  `timestamp`            UTC datetime             Required

  `details`              `dict[str, JsonValue]`   Required, redacted and
                                                  bounded
  -----------------------------------------------------------------------

**`TraceEventType` members:** `PROPOSAL_CREATED`, `POLICY_DECIDED`,
`APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_DENIED`,
`APPROVAL_EXPIRED`, `EXECUTION_STARTED`, `EXECUTION_SUCCEEDED`,
`EXECUTION_FAILED`, `EXECUTION_SKIPPED`, `VERIFICATION_COMPLETED`.

The approval events exist only so the lifecycle can be traced. The
approval payload shape is deferred to the approval feature.

**Redaction specification:**

1.  **Sanitizer:** a standalone pure function
    `sanitize_details(details) -> dict` does the redacting. Callers use
    it before constructing a `TraceEvent`.
2.  **Sensitive keys:** a key is sensitive if its normalized form
    (lowercased, with `-`, `_`, and spaces removed) contains any of:
    `password`, `passwd`, `secret`, `token`, `apikey`, `authorization`,
    `cookie`, `credential`, `privatekey`, `sessionid`. Matching is
    recursive through nested dicts and lists.
3.  **Replacement:** the value of a sensitive key becomes the string
    `"[REDACTED]"`.
4.  **Truncation:** `TRACE_STRING_MAX_CHARS` is the maximum length of
    the final stored string, including the suffix `"…[TRUNCATED]"`. When
    truncation is needed, retain only the prefix that fits alongside the
    entire suffix, then append the suffix. The final string must never
    exceed `TRACE_STRING_MAX_CHARS` characters. Strings at or below the
    limit are unchanged.
5.  **Size and depth measurement:** measure the `details` object itself
    using the canonical JSON encoding from Section C and UTF-8 byte
    length. Apply the trace size and depth checks after sanitization;
    the `TraceEvent` validator never sanitizes automatically.
6.  **Model-level enforcement:** the `TraceEvent` validator does **not**
    silently modify input. It rejects `details` that still contain a
    sensitive key with a value other than `"[REDACTED]"`, or that exceed
    `TRACE_DETAILS_MAX_DEPTH` or `TRACE_DETAILS_MAX_BYTES`. An
    unredacted secret therefore cannot be constructed into a trace
    event.
7.  **Known limit:** key-name matching does not detect secrets hidden
    inside free-text values. Value-pattern scanning is out of scope for
    AT-02 and should be recorded as a future decision.

Trace rules:

-   `sequence` establishes event order independently of timestamps.
-   Trace events record lifecycle evidence. They never authorize an
    action or establish verification success.

### H. Lifecycle consistency check

A pure function:

``` python
check_lifecycle_consistency(proposal, decision, result=None, verification=None)
```

It raises `ContractViolation` when any rule below fails. It performs no
I/O, no policy evaluation, no execution, and does not modify its inputs.
Arguments after `decision` are optional so the check can be applied at
each stage of the lifecycle.

**Identity and integrity**

The individual contract models validate identifier shape only. They do
not establish global uniqueness. The later lifecycle/trace recorder must
enforce `action_id` uniqueness within the agreed action/task scope and
`event_id` uniqueness within the trace store's scope before accepting
records. AT-02 defines no registry, database, or cross-process
uniqueness mechanism.

  ------------------------------------------------------------------------
  \#                                Rule
  --------------------------------- --------------------------------------
  H1                                `decision.action_id` must equal
                                    `proposal.action_id`.

  H2                                `decision.proposal_digest` must equal
                                    `compute_proposal_digest(proposal)`.

  H3                                If `result` is present,
                                    `result.action_id` must equal
                                    `proposal.action_id`.

  H4                                If `verification` is present,
                                    `verification.action_id` must equal
                                    `proposal.action_id`.
  ------------------------------------------------------------------------

**Decision and execution consistency**

If `result` is present, its `status` and `not_executed_reason` must be
permitted for `decision.decision` by this table. The check validates
that the reason is *permissible* for the decision. It does not force a
single reason, and it cannot establish whether an approval was in fact
denied or expired. That fact belongs to the later approval feature.

  ------------------------------------------------------------------------
  `decision.decision`    Allowed                Allowed
                         `result.status`        `not_executed_reason`
                                                (when `NOT_EXECUTED`)
  ---------------------- ---------------------- --------------------------
  `ALLOW`                `SUCCEEDED`, `FAILED`, `INTEGRITY_CHECK_FAILED`
                         `NOT_EXECUTED`         only

  `BLOCK`                `NOT_EXECUTED` only    `POLICY_BLOCKED`,
                                                `INTEGRITY_CHECK_FAILED`

  `REQUIRE_APPROVAL`     `NOT_EXECUTED` only    `APPROVAL_PENDING`,
                         (in AT-02)             `APPROVAL_DENIED`,
                                                `APPROVAL_EXPIRED`,
                                                `INTEGRITY_CHECK_FAILED`
  ------------------------------------------------------------------------

  ---------------------------------------------------------------------
  \#                                 Rule
  ---------------------------------- ----------------------------------
  H5                                 `result.status` must be allowed
                                     for the decision, per the table.

  H6                                 When `result.status` is
                                     `NOT_EXECUTED`,
                                     `not_executed_reason` must be
                                     allowed for the decision, per the
                                     table.
  ---------------------------------------------------------------------

Consequences worth stating explicitly:

-   After a `REQUIRE_APPROVAL` decision, `APPROVAL_PENDING`,
    `APPROVAL_DENIED`, and `APPROVAL_EXPIRED` are all valid. The checker
    must not require `APPROVAL_PENDING`.
-   `POLICY_BLOCKED` is valid only with `BLOCK`. `APPROVAL_*` reasons
    are valid only with `REQUIRE_APPROVAL`.
-   `REQUIRE_APPROVAL` with `SUCCEEDED` or `FAILED` is rejected in
    AT-02, because no approval contract exists yet to justify execution.
    The approval feature will extend this rule.

**Verification consistency**

  ---------------------------------------------------------------------
  \#                                 Rule
  ---------------------------------- ----------------------------------
  H7                                 If `verification` is present,
                                     `result` must also be present. An
                                     action with no execution record
                                     cannot be verified.

  H8                                 If `result.status` is
                                     `NOT_EXECUTED`, then
                                     `VERIFIED_SUCCESS` must use
                                     `NO_CHANGE_CONFIRMED`, and
                                     `VERIFIED_FAILURE` must use
                                     `UNEXPECTED_STATE_CHANGE`.
                                     `OUTCOME_MATCHES_EXPECTED` and
                                     `OUTCOME_MISMATCH` are rejected.

  H9                                 If `result.status` is `SUCCEEDED`
                                     or `FAILED`, then
                                     `NO_CHANGE_CONFIRMED` and
                                     `UNEXPECTED_STATE_CHANGE` are
                                     rejected. Those two codes describe
                                     only actions that never ran.

  H10                                `INCONCLUSIVE` with any of its
                                     three allowed reason codes is
                                     valid for any execution status.
  ---------------------------------------------------------------------

### I. Shared validation and testing requirements

All tests must be deterministic and run offline. Tests use fixed
timestamps and fixed identifiers, never the current clock.

**I1. Baseline (carried over)**

-   Valid instances of all five contracts.
-   Missing required fields, for every required field of every contract.
-   Unknown fields on every contract.
-   Invalid types and inappropriate coercion (string for int, int for
    bool, and so on).
-   Invalid enum values and invalid timestamps.
-   Whitespace-only values are rejected for every field specified as a
    non-blank string; valid strings are not silently stripped.
-   Trace ordering by `sequence` independent of `timestamp`.
-   Contract validity does not grant execution permission: constructing
    a valid `ALLOW`-style set of contracts triggers no execution path,
    and no contract exposes an execute method.

**I2. Timestamps and immutability**

-   Naive datetime rejected. ISO string without offset rejected.
-   Aware non-UTC datetime accepted and normalized to UTC, through both
    `model_validate` and `model_validate_json`.
-   Assigning to any field of a constructed contract raises.
-   Mutating the source dict after construction leaves the contract
    unchanged, including nested dicts and lists.
-   Mutating a nested dict or list through a contract field is
    impossible or rejected; nested structures cannot be changed through
    references returned by the contract.
-   The immutable internal representation serializes/canonicalizes back
    to the same JSON object/array structure and preserves scalar types.

**I3. JSON-compatible data and named limits (Section B)**

-   `NaN`, `Infinity`, tuples, sets, `bytes`, non-string keys, and
    custom objects are rejected.
-   `bool` is not coerced to or from `int`.
-   `MAX_ARGUMENT_BYTES` equals `65536` and `MAX_ARGUMENT_DEPTH` equals
    `10` (the values are pinned by a test).
-   Canonical size of exactly `MAX_ARGUMENT_BYTES` accepted. One byte
    over rejected.
-   Depth of exactly `MAX_ARGUMENT_DEPTH` accepted. Depth 11 rejected.
-   Depth counting through lists and through mixed list/dict nesting.
-   Size is measured in bytes, not characters: a payload of multi-byte
    characters that is under the limit in characters but over it in
    bytes is rejected.
-   The same limits apply to `arguments`, `result`, and `evidence`.
-   Trace limits: `TRACE_DETAILS_MAX_BYTES` and
    `TRACE_DETAILS_MAX_DEPTH` boundary cases, accepted at the limit and
    rejected one over.

**I4. Proposal digest (Sections C and D)**

-   Deterministic: the same proposal gives the same digest across
    repeated calls.
-   Insensitive to key order, at the top level of `arguments` and in
    nested dicts.
-   Changing any one of `action_id`, `task_id`, `tool_name`,
    `arguments`, or `requested_by` changes the digest (one parametrized
    case per field).
-   Changing `created_at` alone does **not** change the digest.
-   Changing a nested argument value, or adding or removing an argument
    key, changes the digest.
-   Pinned known-vector test: a fixed proposal produces a fixed expected
    hex string, which locks canonicalization version 1.
-   `DIGEST_CANONICALIZATION_VERSION` equals `1` and
    `PROPOSAL_DIGEST_HEX_LENGTH` equals `64`.
-   Non-ASCII argument values are encoded as raw UTF-8 and produce a
    stable digest.
-   `1` and `1.0` as argument values produce different digests.
-   Output is exactly `PROPOSAL_DIGEST_HEX_LENGTH` characters of
    lowercase hexadecimal.
-   `PolicyDecision.proposal_digest` rejects: uppercase hex, one
    character below `PROPOSAL_DIGEST_HEX_LENGTH`, one character above
    it, non-hex characters, whitespace, and an empty string.

**I5. Policy decision (Section D)**

-   Every valid `decision` / `reason_code` pairing is accepted.
-   Every invalid pairing is rejected (parametrized over the full cross
    product, with the allowed set defined once).
-   `decision` accepts exactly the three specified members.

**I6. Execution result and `NotExecutedReason` (Section E)**

-   `NOT_EXECUTED` without `not_executed_reason` rejected.
-   `NOT_EXECUTED` with each of the five reasons accepted.
-   `SUCCEEDED` with `not_executed_reason` set rejected.
-   `FAILED` with `not_executed_reason` set rejected.
-   `NOT_EXECUTED` with `result` set rejected. `NOT_EXECUTED` with
    `error_code` set rejected.
-   `SUCCEEDED` with `error_code` set rejected. `SUCCEEDED` with
    `result=None` accepted.
-   `FAILED` without `error_code` rejected. `FAILED` with `result` set
    rejected.
-   Invalid `not_executed_reason` value rejected, including free-text
    strings.
-   `NotExecutedReason` has exactly the five specified members.

**I7. Verification result (Section F)**

-   Every valid `status` / `reason_code` pairing accepted. Every invalid
    pairing rejected (full cross product).
-   `NO_CHANGE_CONFIRMED` rejected with `VERIFIED_FAILURE` and with
    `INCONCLUSIVE`.
-   `UNEXPECTED_STATE_CHANGE` rejected with `VERIFIED_SUCCESS` and with
    `INCONCLUSIVE`.
-   `VERIFIED_SUCCESS` and `VERIFIED_FAILURE` without `evidence`
    rejected. `INCONCLUSIVE` accepts `evidence=None`.
-   Execution `SUCCEEDED` does not produce or imply a `VERIFIED_SUCCESS`
    (no constructor or helper converts one to the other).

**I8. Trace event and redaction (Section G)**

-   Every `TraceEventType` member accepted. Unknown event type rejected.
-   `sequence` of `0` and negative values rejected.
-   Sensitive keys redacted by `sanitize_details`: nested dicts, dicts
    inside lists, uppercase and mixed case, and `-`, `_`, and space
    variants (for example `API-Key`, `api_key`, `Api Key`).
-   Non-sensitive keys and values pass through unchanged.
-   Strings over `TRACE_STRING_MAX_CHARS` truncated so the final string,
    suffix included, is at most `TRACE_STRING_MAX_CHARS` characters. A
    string exactly at the limit is unchanged.
-   `sanitize_details` does not mutate its input and is idempotent.
-   `TraceEvent` rejects `details` containing a sensitive key with an
    unredacted value, and accepts the same key with `"[REDACTED]"`.
-   Trace details byte-size tests measure the canonical JSON UTF-8
    encoding of the `details` object after sanitization/truncation.
-   Every truncated string's final length, including `…[TRUNCATED]`, is
    at most `TRACE_STRING_MAX_CHARS`.
-   Contract models do not claim to enforce global uniqueness for
    `action_id` or `event_id`; uniqueness enforcement is covered by the
    later lifecycle/trace component.
-   Documented known limit: a test confirms that a secret embedded in a
    free-text value under a non-sensitive key is *not* detected, so the
    limitation is visible and pinned.

**I9. Lifecycle consistency check (Section H)**

*Identity and integrity*

-   Fully consistent proposal, decision, result, and verification
    passes.
-   H1: mismatched `decision.action_id` raises.
-   H2: digest mismatch raises when `arguments` changes after the
    decision, when `requested_by` changes, when `tool_name` changes, and
    when `task_id` changes.
-   H2: a change to `created_at` alone does **not** raise.
-   H3 and H4: mismatched `action_id` on the result and on the
    verification each raise.
-   Decision-only call (no result, no verification) passes when H1 and
    H2 hold.

*Decision and execution consistency (exhaustive matrix)*

-   A parametrized test enumerates all three decisions against every
    result shape: `SUCCEEDED`, `FAILED`, and `NOT_EXECUTED` with each of
    the five reasons. The expected-allowed set is defined once, from the
    table in Section H, and every combination is asserted to pass or
    raise accordingly.
-   Explicit named cases:
    -   `REQUIRE_APPROVAL` with `NOT_EXECUTED` and `APPROVAL_PENDING`
        passes.
    -   `REQUIRE_APPROVAL` with `NOT_EXECUTED` and `APPROVAL_DENIED`
        passes.
    -   `REQUIRE_APPROVAL` with `NOT_EXECUTED` and `APPROVAL_EXPIRED`
        passes.
    -   `REQUIRE_APPROVAL` with `NOT_EXECUTED` and
        `INTEGRITY_CHECK_FAILED` passes.
    -   `REQUIRE_APPROVAL` with `NOT_EXECUTED` and `POLICY_BLOCKED`
        raises.
    -   `REQUIRE_APPROVAL` with `SUCCEEDED` raises. `REQUIRE_APPROVAL`
        with `FAILED` raises.
    -   `BLOCK` with `POLICY_BLOCKED` passes. `BLOCK` with
        `INTEGRITY_CHECK_FAILED` passes.
    -   `BLOCK` with any `APPROVAL_*` reason raises. `BLOCK` with
        `SUCCEEDED` or `FAILED` raises.
    -   `ALLOW` with `SUCCEEDED` passes. `ALLOW` with `FAILED` passes.
    -   `ALLOW` with `NOT_EXECUTED` and `INTEGRITY_CHECK_FAILED` passes.
    -   `ALLOW` with `NOT_EXECUTED` and `POLICY_BLOCKED`,
        `APPROVAL_PENDING`, `APPROVAL_DENIED`, or `APPROVAL_EXPIRED`
        raises.

*Verification consistency (exhaustive matrix)*

-   A parametrized test enumerates execution status (`NOT_EXECUTED`,
    `SUCCEEDED`, `FAILED`) against every valid verification `status` /
    `reason_code` pair, with the expected-allowed set defined once from
    Section H.
-   Explicit named cases:
    -   H7: verification supplied with `result=None` raises.
    -   H8: `NOT_EXECUTED` with `VERIFIED_SUCCESS` and
        `NO_CHANGE_CONFIRMED` passes.
    -   H8: `NOT_EXECUTED` with `VERIFIED_SUCCESS` and
        `OUTCOME_MATCHES_EXPECTED` raises.
    -   H8: `NOT_EXECUTED` with `VERIFIED_FAILURE` and
        `UNEXPECTED_STATE_CHANGE` passes.
    -   H8: `NOT_EXECUTED` with `VERIFIED_FAILURE` and
        `OUTCOME_MISMATCH` raises.
    -   H9: `SUCCEEDED` with `NO_CHANGE_CONFIRMED` raises. `FAILED` with
        `NO_CHANGE_CONFIRMED` raises.
    -   H9: `SUCCEEDED` with `UNEXPECTED_STATE_CHANGE` raises. `FAILED`
        with `UNEXPECTED_STATE_CHANGE` raises.
    -   H9: `SUCCEEDED` with `VERIFIED_SUCCESS` and
        `OUTCOME_MATCHES_EXPECTED` passes.
    -   H10: `INCONCLUSIVE` passes for all three execution statuses.

*Purity*

-   The check does not mutate its inputs (inputs compared before and
    after).
-   The check performs no I/O (runs with network and filesystem access
    patched to fail).
-   Violations raise `ContractViolation`, not a generic exception, and
    the message names the failing rule number.

## 3. Explicit exclusions and deferred requirements

AT-02 will not implement:

-   Policy evaluation logic.
-   Tool execution or allowlisting behavior.
-   Human approval issuance, approval-token structure, or approval-token
    validation.
-   The simulated order-management environment.
-   Independent verification logic.
-   **Task-level aggregation of verification results.**
-   Trace persistence or database storage.
-   Value-pattern secret scanning.
-   An identity contract for `requested_by`.
-   A digest canonicalization-version field on the policy decision
    (needed only if canonicalization changes).
-   API endpoints, UI, or real model integration.

These remain separate features in the existing `feature-registry.md`.

**Requirement recorded for the later verifier feature (not implemented
in AT-02):**

> Task-level aggregation must not count `NO_CHANGE_CONFIRMED` as goal
> completion. `NO_CHANGE_CONFIRMED` confirms that an action which never
> executed left state unchanged. It is not evidence that the task's
> intended outcome was achieved. A task may be reported as verified
> successful only when the verifier reports `VERIFIED_SUCCESS` with
> `OUTCOME_MATCHES_EXPECTED` for the actions that carry the task's goal.

## 4. Acceptance criteria

AT-02 can be marked complete when:

-   All five contracts and their enums are implemented with strict
    validation.
-   `NotExecutedReason`, the two new verification reason codes, and the
    named limit constants are implemented and pinned by tests.
-   The timestamp convention and trace-redaction requirements are
    enforced and tested.
-   `compute_proposal_digest`, `sanitize_details`, and
    `check_lifecycle_consistency` are implemented and tested, including
    every rule H1 to H10.
-   Valid examples parse successfully and invalid examples are rejected.
-   Every test group in Section I is present and passing.
-   `pytest` and Ruff pass.
-   The progress tracker and relevant documentation are updated with
    evidence.
-   The deferred verifier requirement in Section 3 is recorded in the
    tracker.

No later decision, including D-002, D-003, or D-004, will be marked
accepted as part of this work.

## 5. Resolved decisions

Each decision below is **resolved**. The identifiers `AT02-Q1` to
`AT02-Q4` are local to AT-02 and do not collide with D-002, D-003, or
D-004.

### AT02-Q1: Argument limits

-   **Question:** Are 64 KiB and depth 10 appropriate for action
    arguments?
-   **Decision:** Yes. Retain both, as named constants
    `MAX_ARGUMENT_BYTES = 65536` and `MAX_ARGUMENT_DEPTH = 10`.
-   **Rationale:**
    -   The simulated order-management environment produces small
        arguments, so the limits only need to stop abuse and runaway
        payloads.
    -   Size is measured on the same canonical JSON the digest uses, so
        the project has one definition of "size".
    -   Named constants let later tool contracts set tighter per-tool
        limits without loosening the global ones.
    -   Trace details keep tighter limits (8 KiB, depth 5) because they
        carry lifecycle metadata, not payloads.

### AT02-Q2: Reason for `NOT_EXECUTED`

-   **Question:** Should `NOT_EXECUTED` have its own reason field?
-   **Decision:** Yes. Add `NotExecutedReason` and a
    `not_executed_reason` field, required only when `status` is
    `NOT_EXECUTED` and forbidden otherwise.
-   **Rationale:**
    -   Locating the reason in the policy decision works for `BLOCK` and
        `REQUIRE_APPROVAL`, but fails for approval denial, approval
        expiry, and executor integrity refusals, none of which is a
        policy decision.
    -   Without its own reason, a `NOT_EXECUTED` record would be
        ambiguous in the audit trail exactly where clarity matters most.
    -   A coarse enum, not free text, cannot leak sensitive data.
    -   The lifecycle check validates that the reason is *permissible*
        for the decision and does not force a single reason. In
        particular, after `REQUIRE_APPROVAL`, `APPROVAL_PENDING`,
        `APPROVAL_DENIED`, and `APPROVAL_EXPIRED` are all valid.

### AT02-Q3: Verifying `NOT_EXECUTED` actions

-   **Question:** Can a `NOT_EXECUTED` action still be verified, for
    example by confirming that no state changed?
-   **Decision:** Yes, with guardrails: new reason codes
    `NO_CHANGE_CONFIRMED` (with `VERIFIED_SUCCESS`) and
    `UNEXPECTED_STATE_CHANGE` (with `VERIFIED_FAILURE`), enforced by
    rules H7 to H10. Task-level aggregation must not count
    `NO_CHANGE_CONFIRMED` as goal completion, recorded as a requirement
    for the later verifier feature.
-   **Rationale:**
    -   If a blocked or unapproved action leaves state changed anyway,
        an unsafe action has leaked through. Detecting that is a core
        purpose of an independent verifier.
    -   A bare `VERIFIED_SUCCESS` on an action that never ran could be
        misread as the task succeeding. Dedicated reason codes and the
        H8 rule keep the two meanings apart.
    -   The two new codes are restricted to actions that never ran (H9),
        so they cannot be confused with outcome verification of executed
        actions.

### AT02-Q4: Proposal digest fields

-   **Question:** Should the digest include `requested_by` and
    `created_at`, or only the four original fields?
-   **Decision:** Include `requested_by`. Exclude `created_at`. The
    digest covers `action_id`, `task_id`, `tool_name`, `arguments`, and
    `requested_by`.
-   **Rationale:**
    -   The digest should cover every field a policy decision or the
        executor could depend on. Policy may reasonably vary by
        requester, so a decision made for one requester must not validly
        attach to a proposal from another.
    -   `created_at` is metadata. Including it would give identical
        logical proposals different digests on retry, and replay is
        already handled by `action_id` uniqueness.
    -   Canonicalization is recorded as version 1 so a stored digest can
        always be traced to the rules that produced it.

## 6. Tracker entries

Paste-ready entries for the progress tracker:

``` markdown
## AT-02 decisions (resolved, revision 4)

- AT02-Q1 RESOLVED: Retain 64 KiB / depth 10 argument limits as named constants
  (MAX_ARGUMENT_BYTES, MAX_ARGUMENT_DEPTH). Size measured on canonical JSON bytes.
- AT02-Q2 RESOLVED: Add NotExecutedReason enum and not_executed_reason field,
  required only for NOT_EXECUTED. Lifecycle check validates permissible reasons per
  decision and does not force APPROVAL_PENDING after REQUIRE_APPROVAL.
- AT02-Q3 RESOLVED: NOT_EXECUTED actions may be verified. New codes
  NO_CHANGE_CONFIRMED (VERIFIED_SUCCESS) and UNEXPECTED_STATE_CHANGE
  (VERIFIED_FAILURE), enforced by lifecycle rules H7-H10.
- AT02-Q4 RESOLVED: Proposal digest covers action_id, task_id, tool_name, arguments,
  requested_by. Excludes created_at. Canonicalization version 1.

## Requirement deferred to the verifier feature

- Task-level aggregation must not count NO_CHANGE_CONFIRMED as goal completion.
  Not implemented in AT-02.

## AT-02 status

- Specification revision 3: awaiting approval. No code written.
```

## Approval

Please review the specification before we write any code.

-   [ ] Approve as written. Proceed to AT-02 implementation planning.
-   [ ] Request changes before implementation.

Comments or requested changes:
