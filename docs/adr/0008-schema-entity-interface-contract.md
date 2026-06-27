# ADR-0008: Schema entity — interface contract + Output validation path

- **Status:** Accepted
- **Date:** 2026-06-27
- **Deciders:** Lead Architect / Domain Architect

## Context

`Schema` is the **typed description of the data shape at an agent boundary** and the single
source of truth for generation, validation and contract documentation (`DOMAIN_MODEL.md` §2.8;
`PROJECT.md` §9 — "нет схемы — нет границы"). Unlike Task/Output/Artifact/Human Review, it is
**not** a child of the Run aggregate root: it is a **standalone aggregate root** of the
definitions catalogue (`DOMAIN_MODEL.md` §9.5), with independent identity and versioning,
referenced by other entities (it does not belong to any of them).

It is the next domain entity by `ROADMAP.md` Stage 2 ("Run, Artifact, Workflow … `Schema`-контракты
границ агентов") and by dependency order: Schema is the root of the definition dependency tree
(Workflow Step and Agent will reference it). It also **unblocks completing `Output`**: `ADR-0005`
deliberately deferred the Output validity-validation lifecycle `Pending → Valid/Invalid` and the
`INVALID` outcome "because it needs the Schema entity and a validation step" (`ADR-0005` §4, §10).

This ADR records an **interface-contract** decision (analogous to `ADR-0003`/`0004`/`0005`), the
**minimal faithful subset** to implement now and what is deferred and why. It is an **additive,
Open/Closed** extension (`PROJECT.md` §4.11): the existing behaviour, signatures and tests of
Run, Task, **Output**, Artifact and Human Review are unchanged; only a new module and new
operations are added. No infrastructure (no JSON-Schema/pydantic, no provider, no network). The
shared `DomainError` base is **explicitly out of scope** for this work (it stays a separate
technical-debt follow-up; `ADR-0005` §9).

`DOMAIN_MODEL.md` and `ARCHITECTURE.md` §11 state that the concrete fields of schemas are not
designed at the domain level; this ADR therefore decides only the **domain-level contract** of
the Schema entity, not a wire format.

## Decision

### 1. Placement & dependency direction
Schema symbols live in a new module `omemo_content_factory.domain.schema`: `SchemaId`,
`SchemaVersion` (a Value Object), `SchemaStatus`, `Schema`, `SchemaView`, the Schema validation
result, and Schema domain errors. The module depends on **nothing** in `run`/`task`/`output`
(one-directional: `run` may import from `schema`; `schema` imports only stdlib). This keeps the
dependency direction inward (`PROJECT.md` §7) and avoids any import cycle. References are opaque
`str` where they cross to other entities (`ADR-0003` §3).

### 2. Standalone aggregate root, constructed via its own factory
Schema is its **own** aggregate root (`DOMAIN_MODEL.md` §9.5), **not** a Run child. It is created
via a public factory `Schema.create(...)` (mirroring `Run.create`), **not** through Run. This is
the first definition-catalogue root in the codebase; the Run children pattern (created *through*
the root) does not apply to it.

### 3. Identity & version (Value Object)
- `SchemaId` is a stable, immutable opaque `str` identifier of the **logical contract** (it is the
  same across versions).
- `SchemaVersion` is a **Value Object** (`DOMAIN_MODEL.md` §11 — "v3 равно v3 всегда"): no
  identity, immutable, compared by value.
- A specific **(SchemaId, SchemaVersion)** pair identifies one immutable accepted version. An
  accepted version's content is **write-once immutable** (`DOMAIN_MODEL.md` §6 — "Принятые версии
  … неизменяемы"); a new revision is a **new version**, never an edit.
- *Owning multiple versions under one root* (a single Schema object holding all its versions) is
  the richer catalogue machinery; this slice models a Schema as one **versioned definition**
  (identified by id+version). The multi-version container is **deferred** (see Deferred), exactly
  as the rest of the catalogue (Workflow/Agent) is still deferred.

### 4. Lifecycle — `SchemaStatus`
`SchemaStatus = {DRAFT, ACTIVE, DEPRECATED}` (`DOMAIN_MODEL.md` §2.8). A Schema is created `DRAFT`.
Allowed transitions form the documented chain only:
`DRAFT → ACTIVE → DEPRECATED` (no other edges; terminal `DEPRECATED`). The transition is a single
guarded mutation over a **declarative allowed-transitions table** (the proven `Run.transition`
shape). Because only `status` changes, the entity is exposed as a read-only **`SchemaView`**
snapshot (mirroring Task/Artifact); identity, version and the contract descriptor are write-once
(`__slots__` + guarded `__setattr__`).

### 5. The contract descriptor (minimal faithful subset of §2.8)
Implemented now (domain-level, provider-agnostic): `schema_id`, `version`, a human-level
`description`, and a **set of required field names** (`DOMAIN_MODEL.md` §2.8 — "набор полей и их
семантика" + "правила обязательности"), plus `status`. The required-field set is the smallest
faithful realisation of an agent-boundary contract: it makes the boundary a **validatable
contract** rather than free text (`PROJECT.md` §9). Typed/nested fields, optional-field
declarations, semantic constraints and migration rules are **deferred** (they need a richer
representation and are not required to activate the Output lifecycle).

### 6. Validation — deterministic, infrastructure-free verdict
Schema exposes a pure, deterministic `validate(payload_fields) -> SchemaValidation`, where
`payload_fields` is a structured `Mapping[str, str]` (field name → value) and `SchemaValidation`
carries `is_valid: bool` and the list of missing required fields. Rule for this slice: **valid iff
every required field is present and non-empty**, else **invalid**. This is the system-side
validation of `PROJECT.md` §9; the *provider-native* structured-output half of the "double
protection" is **infrastructure and is deferred** (it belongs to the LLM Adapter / agent stage,
not the domain). Validation only runs against an **`ACTIVE`** Schema version (validating against a
`DRAFT`/`DEPRECATED` version is rejected with a domain error). A failed validation is a **normal
outcome (an invalid verdict), not an exception** (`PROJECT.md` §10 — "ошибка валидации —
управляемое событие").

### 7. How Output references Schema (no change to Output)
`Output.schema_ref` stays an **opaque `str`** that now denotes a specific **Schema version**
(e.g. `"<schema_id>@<version>"`); `Output`'s structure (frozen dataclass, `payload: str`,
`OutputStatus`) is **unchanged**, preserving the documented 1:1 "Output — Schema (версия)"
(`DOMAIN_MODEL.md` §5) and the §6 invariant "Output валидируется против ровно одной версии
Schema". The `schema_ref` representation is stable through the migration (see *Migration /
transitional state*).

### 8. Target contract — a single validated Output-creation path
Per `DOMAIN_MODEL.md` §6 ("Output **всегда** валидируется против ровно одной версии Schema") the
target contract exposes **one** Output-creation operation on the Run root — `record_output` — that
**always** validates the produced result against exactly one **`ACTIVE`** Schema version before
fixation. **An Output is never created without a verdict;** validation is an invariant of the
model, not an optional mode. (How the two methods of the current slice converge to this single path
is the *Migration* section below, not part of the target.)

- **`Pending` is the formation phase, not a stored state.** The verdict is computed by
  `Schema.validate` *before* the Output is fixed; the recorded `Output` is then constructed
  **directly** in its terminal `VALID` **or** `INVALID` state and is never mutated (it stays a
  frozen, immutable record — `ADR-0005` §2; `DOMAIN_MODEL.md` §6, §12 "новая попытка → новый
  Output"). `PENDING` is **retained in `OutputStatus` as documented domain vocabulary**
  (`DOMAIN_MODEL.md` §2.11) but is **never persisted** — symmetry with how `ADR-0005` §4 keeps
  `INVALID` as vocabulary. Birth-with-verdict rather than a stored intermediate is faithful because
  validation here is **synchronous and deterministic** (`PROJECT.md` §9 system-side check), so a
  `PENDING` phase is unobservable; it would become a real stored state only if validation became
  **asynchronous** — a future ADR.
- **An `INVALID` Output must not flow downstream** (`DOMAIN_MODEL.md` §6 — "невалидный Output не
  передаётся дальше"). At the **domain** level this is honoured by recording the verdict faithfully;
  the **orchestration** consequence (route the step to retry/error per `PROJECT.md` §10) is
  application-layer wiring, **out of this ADR's scope** (no change to `ContentDirector` here) and
  deferred to a later slice.

### 9. Events
No Schema lifecycle events are introduced: `DOMAIN_MODEL.md` §10 lists none for Schema, and
Schema is a catalogue root, not a Run child (it has no Run event log). For the Output path: a
`VALID` outcome emits the **existing** `OutputValidated` (`ADR-0005` §7). An `INVALID` outcome
emits **no dedicated event** at this stage — `DOMAIN_MODEL.md` §10 documents no such event, and
the project does not invent vocabulary (mirrors Task `SKIPPED` / Artifact `DRAFT→CANDIDATE`
emitting nothing). A documented invalid-output event is flagged as Deferred.

### 10. Actor authorisation
- The validated Output-recording path is **Run state**, so it reuses the existing
  `CONTENT_DIRECTOR` authorisation and `Run.UnauthorizedActorError` (`ADR-0003`, `ADR-0005` §5).
  **No new Actor is introduced.**
- Schema **catalogue lifecycle** (`create`, `DRAFT→ACTIVE→DEPRECATED`) is governed by PR/ADR/
  engineering process, not a runtime actor (`DOMAIN_MODEL.md` §2.8 — owner is the definitions
  catalogue). At this stage its transition is guarded by the **allowed-transitions table only**;
  a runtime catalogue-maintainer actor is **deferred** (introduce it with the wider catalogue:
  Workflow/Agent).

### 11. Errors
Co-located in `domain.schema`: base `SchemaDomainError` + `InvalidSchemaTransitionError`,
`ImmutableSchemaAttributeError` (the write-once guard, for parity with Task/Artifact), and
`SchemaNotActiveError` (validating against a non-`ACTIVE` version). Authorisation on the Output
path reuses Run's `UnauthorizedActorError`. The invalid *verdict* is **not** an error (it is a
normal `SchemaValidation` result). The shared `DomainError` base is **not** extracted here (out of
scope by explicit instruction; `ADR-0005` §9).

### 12. Time
No timestamps in the asserted surface (`ADR-0003` §10).

## Deferred (depend on out-of-scope concepts; explicitly not implemented)
- A single Schema **root owning multiple versions** (catalogue container); richer field types,
  optional fields, nested structures, semantic constraints and version **migration/compatibility**
  rules (`DOMAIN_MODEL.md` §2.8 optional attributes).
- The **provider-native** structured-output half of the "double protection" (`PROJECT.md` §9) —
  it is infrastructure (LLM Adapter), not domain.
- A documented **invalid-output domain event** and the **orchestration routing** of an `INVALID`
  Output to retry/error (`PROJECT.md` §10) — application-layer, separate slice.
- A runtime **catalogue-maintainer Actor** for definition lifecycle (arrives with Workflow/Agent).
- The shared `DomainError`/`DomainEvent` base — separate technical-debt follow-up, not this work.

## Migration / transitional state (not part of the target model)
The target (§8) is **one** validated `record_output`. Reaching it without breaking the current
slice is staged, so the *implementation* is additive now while the *contract* states the target:

- **This slice (additive).** The validating logic is introduced **alongside** the existing
  `record_output`, under a temporary name `record_validated_output(task_id, *, payload_fields,
  payload, schema, by)`, which runs `schema.validate(...)` on an `ACTIVE` Schema and records the
  Output `VALID`/`INVALID` (reusing the `CONTENT_DIRECTOR` authorisation and the 1:1 /
  Task-succeeded guards of `record_output`, `ADR-0005` §5). The existing `record_output`
  (always-`VALID`, opaque `schema_ref`) is **left unchanged**, so all current callers and tests
  behave identically — honouring the additivity constraint.
- **Convergence (later).** Once the application layer supplies a Schema for every Output (a later
  ROADMAP step — the orchestration of validation is deferred, §8 / Deferred), `record_output` is
  switched to the validated path and the temporary `record_validated_output` is removed. The
  **target method name is `record_output`**; `record_validated_output` is interim only.
- **Nature of the convergence step.** Replacing `record_output`'s behaviour is **non-additive**
  (it modifies existing behaviour). It is a **planned debt-paydown that executes the decision
  already made in this ADR**, not a new architectural decision — so it needs an implementation PR,
  **not** a fresh ADR. Until then the dual methods are an acknowledged transitional state, never a
  permanent part of the model.

## Consequences

### Positive
- Establishes the first **definitions-catalogue aggregate root** and the reusable contract for
  versioned definitions (template for Workflow/Agent/Skill/Content Type to follow).
- **Completes the deferred Output lifecycle** (`Pending → Valid/Invalid`) faithfully, activating
  the §6 invariant, while Run/Task/Output/Artifact/Human Review behaviour and tests stay green.
- Realises the `PROJECT.md` §9 system-side validation in the domain, provider-agnostically and
  without infrastructure; immutable versions, guarded lifecycle, inward dependencies.

### Negative / Trade-offs
- During the migration (see *Migration / transitional state*) Run temporarily exposes **two**
  Output-recording methods — the legacy always-`VALID` `record_output` and the interim validated
  `record_validated_output`. This is a transitional state, not the target API; convergence to the
  single validated `record_output` is a planned implementation step under this ADR.
- `Schema` is a deliberately **partial** realisation of `DOMAIN_MODEL.md` §2.8 (deferrals above),
  to be completed when the wider catalogue (Workflow/Agent) lands.

## Alternatives considered
- **Change `record_output` to validate *in this slice*** — rejected *for now*: it changes existing
  behaviour and could turn currently-`VALID` Outputs into `INVALID`, breaking existing
  Output/execution tests, violating this slice's additivity constraint. It is the **target**
  end-state, reached at convergence (see *Migration*), not avoided.
- **One `record_output` with a `validate=True/False` mode flag** — rejected: a flag that toggles
  semantics is a code smell and makes the §6 validation invariant optional-by-parameter; validation
  is a rule, not a mode.
- **Store `PENDING` and make `Output` mutable (transition it to a verdict)** — rejected: `Output`
  is immutable by construction (`ADR-0005` §2) and `DOMAIN_MODEL.md` §6/§12 treat a fixed Output as
  terminal/immutable (a new attempt yields a new Output). `PENDING` is kept as documented
  vocabulary (§8), but the formation phase is unobservable for synchronous validation, so a
  *stored* `PENDING` and a mutable Output are unnecessary and would break immutability.
- **Make Schema a child of Run** — rejected: contradicts `DOMAIN_MODEL.md` §9.5 (Schema is a
  standalone catalogue root, referenced not owned).
- **Implement a real typed/JSON-Schema validator now** — rejected: that is infrastructure and
  speculative machinery (`PROJECT.md` §4.11); the required-field check is the minimal faithful
  domain rule.
- **Bundle the shared `DomainError` extraction in** — rejected: explicitly out of scope; keep this
  change focused on one entity (`ADR-0005` §9).

## References
- `DOMAIN_MODEL.md`: §2.8 (Schema), §2.11 (Output), §5 (Output–Schema 1:1), §6 (Output/Schema
  invariants), §9.5 (Schema as standalone root), §10 (`OutputValidated`), §11 (Version VO)
- `PROJECT.md`: §9 (Structured Outputs / double protection), §10 (validation is a managed event),
  §4.11 (additive extension), §5 (provider independence), §17, §18 (Schema is canonical)
- `ARCHITECTURE.md`: §11 (data contracts; fields not designed at this level)
- `ADR-0003` (Run interface contract — opaque refs, actor, no timestamps), `ADR-0005` (Output;
  the deferred validation lifecycle this activates)
- `ROADMAP.md` stage: 2 (data models and contracts)
