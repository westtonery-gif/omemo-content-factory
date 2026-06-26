# ADR-0005: Output entity — Run/Task↔Output interface contract

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** Lead Architect / Domain Architect

## Context

`Output` is the **structured result of a single Task** (`DOMAIN_MODEL.md` §2.11): an immutable
child entity of the `Run` aggregate root, owned **through its Task** (§9.1), created when a Task
succeeds, **1:1** with that Task (§5). It is not its own aggregate root and does not exist on its
own. `ADR-0004` deferred it; this ADR defines its interface contract, mirroring ADR-0004 for Task.

The domain fully **defines** Output, but several of its obligatory attributes depend on concepts
that are **deliberately out of scope** (Schema, Evaluation/QA, Artifact). This ADR records the
**minimal faithful subset** to implement now and what is deferred and why. It is an additive,
Open/Closed extension (`PROJECT.md` §4.11): Run/Task existing behaviour, signatures and tests
are unchanged; only new operations are added.

## Decision

### 1. Placement
Output symbols live in `omemo_content_factory.domain.output`: `OutputId`, `OutputStatus`,
`Output`, the Output domain event(s), and the Output domain errors. The module depends on
nothing in `run`/`task` (one-directional: `task` and `run` import from `output`), so `task_id`
is represented as a plain opaque `str` (ADR-0003 §3) to avoid a cycle. **Output is created only
via `Run.record_output`** — there is no aggregate-driving factory elsewhere.

### 2. Representation — immutable record
`Output` is an **immutable** entity, modelled as a frozen, slotted dataclass (it has identity
via `output_id` but no lifecycle transitions after fixation, `DOMAIN_MODEL.md` §2.11
"Терминально и неизменяемо"). Because it is immutable, it is exposed **directly** (read-only);
no separate mutable object and no snapshot view are needed (contrast Task, which is mutable).

### 3. Attributes (minimal faithful subset of `DOMAIN_MODEL.md` §2.11)
Implemented now: `output_id` (stable identity), `task_id` (owning Task, opaque `str`),
`schema_ref` (opaque `str` — the contract the payload conforms to; the Schema entity is
deferred), `payload` (the produced structured content, `str`), `status: OutputStatus`.

### 4. Validity — `OutputStatus`
`OutputStatus = {VALID, INVALID}` (`DOMAIN_MODEL.md` §2.11 states `Valid`/`Invalid`). An Output
is **created `VALID`** — it is the recorded valid result of a successful Task. The transient
`Pending` state and the `INVALID` path are **deferred**: producing `INVALID` requires schema
validation, which depends on the deferred Schema entity. `INVALID` is kept as documented domain
vocabulary, reachable when validation exists; only `VALID` is produced at this stage.

### 5. Run's additive public API (the contract)
- `record_output(task_id, *, payload, schema_ref, by) -> OutputId` — creates a `VALID` Output for
  an owned Task, attaches it through the root, emits `OutputValidated`, returns its id. Guards:
  - **authorisation:** `by` must be the Content Director (reuses Run's `UnauthorizedActorError`);
  - **only after success:** the Task must be in `SUCCEEDED`, else `InvalidOutputStateError`
    (`DOMAIN_MODEL.md`: "создаётся при завершении Task"; the user's "только после успешного
    выполнения Task");
  - **1:1:** the Task must not already have an Output, else `DuplicateOutputError`.
- read-only access: the Output is reachable **only through the root**, via `TaskView.output`
  (`Output | None`). No new mutable surface is exposed.

### 6. Task's additive surface
Task gains an optional owned Output (`attach_output`, called only by Run) and its `TaskView`
carries `output: Output | None`. Task's transitions, attempt counting and existing behaviour are
**unchanged**; `transition_task` is **not** modified (so existing callers/tests are untouched).

### 7. Events
`OutputValidated` (`DOMAIN_MODEL.md` §10) is recorded in the Run's **existing single event log**;
the log's type is broadened additively to `RunEvent | TaskEvent | OutputEvent`. (We do not yet
validate against a Schema; the event names the Output being recorded as valid.)

### 8. Errors
Co-located in `domain.output`: base `OutputDomainError` + `InvalidOutputStateError`,
`DuplicateOutputError`. Authorisation reuses Run's `UnauthorizedActorError`. Immutability is
enforced structurally by the frozen dataclass (a `dataclasses.FrozenInstanceError`), so no
dedicated immutable-attribute error is introduced.

### 9. Rule of three — shared error base NOT extracted here
With Run + Task + Output there are now three domain-error hierarchies. ADR-0004 §8 said a shared
`DomainError` base "waits for the third". The third is here — but extracting it would touch the
Run reference implementation and Task. To keep this change focused on Output, the extraction is
**flagged as a separate follow-up** (its own ADR), not bundled in.

### 10. Application wiring (no new domain coupling)
`application.task_execution.ExecutionResult` gains an optional `schema_ref`; `execute_task`
records an Output (via `Run.record_output`) **only when** a successful result carries both
`output` and `schema_ref`. This keeps existing callers (which pass neither, or `output` alone)
behaving exactly as before — no Output is created for them.

## Deferred (depend on out-of-scope concepts; explicitly not implemented)
- Validity **validation** lifecycle `Pending → Valid/Invalid` and the `INVALID` outcome — needs
  the **Schema** entity and a validation step.
- QA-oriented metadata: confidence score, risk flags, decision rationale — need **Evaluation/QA**.
- Produced-`Artifact` list — needs the **Artifact** entity.
- A shared `DomainError` base — rule-of-three follow-up (separate ADR).

## Consequences
**Positive:** Task execution now yields a real, traceable domain result; the root↔child contract
established for Task extends cleanly to Output; Run/Task reference behaviour and tests stay green;
immutable, owned-through-root, no infrastructure.
**Negative / Trade-offs:** Run's public API grows (additively, by `record_output`); `Output` is a
deliberately partial realisation of `DOMAIN_MODEL.md` §2.11 (deferrals above), to be completed
when Schema/Evaluation/Artifact land.

## Alternatives considered
- **Fold Output creation into `transition_task(SUCCEEDED, …)`** — rejected: changes an existing
  signature and would break existing Task/execution tests; violates "do not change Run/Task".
- **Model the full `Pending → Valid/Invalid` validation lifecycle now** — rejected: requires the
  deferred Schema entity and a validator; would be speculative machinery (`PROJECT.md` §4.11 — no
  future abstractions).
- **Expose Output via an `OutputView` snapshot** — unnecessary: Output is immutable, so it is
  safe to expose directly.
- **Make Output a separate Aggregate Root** — rejected: contradicts `DOMAIN_MODEL.md` §9.1
  (Run owns Output through Task).

## References
- `DOMAIN_MODEL.md`: §2.10 (Task), §2.11 (Output), §5 (Task–Output 1:1), §6 (Output invariants),
  §9.1 (Run owns Output via Task), §10 (`OutputValidated`)
- `PROJECT.md`: §4.11 (additive extension), §9 (structured outputs), §17, §18
- `ADR-0003` (Run interface contract), `ADR-0004` (Task interface contract — the template)
- `ROADMAP.md` stage: 2 (data models and contracts)
