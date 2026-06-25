# ADR-0003: Run domain model interface contract

- **Status:** Proposed
- **Date:** 2026-06-25
- **Deciders:** Lead Architect / Domain Architect

## Context

The Run entity is fully specified at the **domain** level by the frozen documents
`DOMAIN_MODEL.md`, `RUN_SPEC.md` and `RUN_ACCEPTANCE.md`. By design, those documents
contain **no technical contract** (no module, type, method, error or event representation):
`RUN_SPEC.md` explicitly excludes "code, classes, types, DB, API and implementation detail".

`RUN_ACCEPTANCE.md` defines 42 executable acceptance scenarios that must become
`tests/test_run.py` (ROADMAP Stage 2). An executable test must bind to a **concrete
interface** for `Run`. That interface does not exist in any source of truth, so writing the
tests would otherwise require undocumented assumptions — which the project forbids.

This ADR records the **minimum technical interface contract** for the Run domain model so the
tests can be written deterministically and the model implemented against it. It **implements**
the frozen domain; it does **not** change the domain, architecture or scope. It covers **Run
only** — child entities (Task, Artifact, Evaluation, Human Review, Analytics Record) remain
out of scope (later stages).

## Decision

### 1. Placement (domain layer, no outward dependencies)

- Module: `omemo_content_factory.domain.run`.
- Public symbols defined there: `Run`, `RunStatus`, `Actor`, `ReworkPolicy`, the Run domain
  **event** types, and the Run domain **error** types. (Co-located for Stage 2 minimalism;
  may be refactored into shared `domain` modules by later stages, via their own ADR.)

### 2. States — `RunStatus`

Exactly the seven states of `RUN_SPEC.md` §4:
`CREATED, QUEUED, RUNNING, WAITING_QA, WAITING_HUMAN, COMPLETED, FAILED`.
Terminal states: `COMPLETED`, `FAILED`.

### 3. Identity and immutable input

- A Run is created via a factory `Run.create(run_id, content_brief_ref, workflow_version_ref,
  rework_policy=<default>)`, returning a Run in `CREATED` and emitting `RunCreated`.
- `run_id`, `content_brief_ref`, `workflow_version_ref` are **explicit** (deterministic, no
  randomness) and **read-only** after creation; any attempt to change them raises
  `ImmutableAttributeError`.
- Changing state or other attributes never changes identity (same `run_id` throughout).

### 4. Actor authorisation — `Actor`

- Minimal role identifier with at least `CONTENT_DIRECTOR` and one non-authorised value (e.g.
  `AGENT`). This is the representation of the **existing** rule "only Content Director changes
  status" (`RUN_SPEC.md` §5, inv. 3) — not new behaviour.

### 5. Transition API (single guarded operation)

`run.transition(to: RunStatus, by: Actor, reason: str | None = None)`:

- **Authorisation:** `by` must be `Actor.CONTENT_DIRECTOR`, else `UnauthorizedActorError`.
- **Allowed edges:** exactly those of `RUN_SPEC.md` §4. Any other edge, any transition out of a
  terminal state, and any state-skip raise `InvalidTransitionError`.
- **Approve semantics:** `COMPLETED` is reachable **only** from `WAITING_HUMAN`; that edge *is*
  the Approve. There is no alternative path to `COMPLETED` (enforces "publication only via
  Approve", `RUN_SPEC.md` §5 inv. 6).
- **Rework edges:** `WAITING_QA → RUNNING` and `WAITING_HUMAN → RUNNING` increment the rework
  counter; if the increment would exceed the policy bound, the operation raises
  `ReworkLimitExceededError` (the legal next step is `transition(FAILED)`).
- **Failure:** `FAILED` is reachable from any non-terminal state; `reason` is captured.
- **Events:** each successful transition emits exactly the corresponding event (see §7).

### 6. Rework policy — `ReworkPolicy`

- Value object carrying `max_rework_iterations`. Injected at creation (tests pass an explicit
  small value for determinism). **Default = 3** (configurable; the value is a policy, not a
  domain rule).
- `run.rework_count` is read-only.

### 7. Domain events

- `run.events` exposes a read-only, ordered sequence of the events emitted since creation.
- Event types: `RunCreated, RunQueued, RunStarted, RunCompleted, RunFailed`.
- Edge → event mapping:
  - create → `RunCreated`
  - `CREATED → QUEUED` → `RunQueued`
  - `QUEUED → RUNNING` → `RunStarted`
  - `WAITING_* → RUNNING` (rework re-entry) → **no** `RunStarted` (per `RUN_SPEC.md` §7 / `EV-03`)
  - `* → COMPLETED` → `RunCompleted`
  - `* → FAILED` → `RunFailed`
- No event is emitted for a rejected (invalid/unauthorised) transition.

### 8. Errors

Hierarchy rooted at `RunDomainError` (a domain error, distinct from technical failures):
`InvalidTransitionError`, `UnauthorizedActorError`, `ImmutableAttributeError`,
`ReworkLimitExceededError`, `AggregateBoundaryError`.

### 9. Aggregate children (scoped)

- Run owns **read-only** collections for its children and exposes through-root attachment that
  stamps the owning Run and raises `AggregateBoundaryError` for a child already owned by another
  Run.
- The **child entity types are out of scope** of this ADR. Therefore full aggregate-boundary
  verification (children cannot exist outside a Run) is **deferred** to when those entities
  exist (see Acceptance coverage).

### 10. Time

- Any timestamps are obtained via an injectable clock and are **not** part of the asserted test
  surface. Tests assert no wall-clock values (determinism; no `sleep`).

## Acceptance coverage impact (`RUN_ACCEPTANCE.md`)

**Realisable now (Run interface only):**
- Happy Path: `HP-01`, `HP-02`
- Rework: `RW-01`, `RW-02`, `RW-03`, `RW-04`
- Failure: `FL-01`…`FL-12`
- Invariants: `INV-01`…`INV-06`, `INV-08`
- Identity: `ID-01`…`ID-04`
- Events: `EV-01`…`EV-05`

**Partially realisable / deferred (require child entities — later stages):**
- `AGG-01`…`AGG-05` (children cannot exist outside Run) — **deferred**.
- `AGG-06` (changes only through root) — testable only at the attach-API surface; **deferred**
  until at least one child entity exists.
- `INV-07` (aggregate integrity) and `INV-09` (traceability via recorded children) —
  **partial** now (rework counter / events), full coverage deferred with child entities.

These deferrals are a direct, documented answer to "which scenarios cannot be realised without
the model", and do **not** change `RUN_ACCEPTANCE.md`.

## Consequences

### Positive

- `test_run.py` can be written deterministically and traceably (scenario ID → test), then
  `run.py` implemented to satisfy it — clean TDD within Stage 2.
- The state machine, identity, events, rework bound and error taxonomy are fixed in one place.
- No undocumented assumptions leak into code; the interface decision is recorded, per
  `PROJECT.md` §11/§17.

### Negative / Trade-offs

- Introduces named technical artefacts (module/types/errors/events) not present in the domain
  docs — acceptable and necessary for implementation; constrained to the minimum.
- Aggregate-boundary tests are deferred, leaving `AGG-*` temporarily uncovered.

## Alternatives considered

- **Write tests against an assumed interface, no ADR** — bakes architectural decisions into
  tests implicitly; violates `PROJECT.md` §11/§17 and the "no assumptions" instruction.
- **One method per transition** (`queue()`, `start()`, …) instead of a single guarded
  `transition()` — more intention-revealing but more surface and harder to test the full
  allowed/forbidden edge matrix (`INV-04`); rejected for minimalism.
- **Implement child entities now to cover `AGG-*`** — out of Stage scope; rejected.

## References

- `DOMAIN_MODEL.md`: §2.9, §6, §9.1, §10, §11, §12
- `RUN_SPEC.md`: §3, §4, §5, §6, §7, §8
- `RUN_ACCEPTANCE.md`: all scenario blocks
- `PROJECT.md` sections: 9 (structured outputs), 11 (ADR), 17 (hierarchy), 18 (entities)
- `ROADMAP.md` stage: 2 (data models and contracts)
