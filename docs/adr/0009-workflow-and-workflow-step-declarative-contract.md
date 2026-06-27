# ADR-0009: Workflow + Workflow Step — declarative interface contract

- **Status:** Accepted (Revision 2)
- **Revision:** 2 (clarifications only — execution-order, Content Director semantics, scope,
  non-goals; the decision and concept are unchanged)
- **Date:** 2026-06-27
- **Deciders:** Lead Architect / Domain Architect

## Context

`Workflow` is the **declaration** of a pipeline for a content type — which steps, in what order,
with which control points (`DOMAIN_MODEL.md` §2.3; `PROJECT.md` §18: "Workflow ≠ Orchestrator").
`Workflow Step` is one step within a Workflow: the binding "position in the pipeline → role
(Agent) + contract" (`DOMAIN_MODEL.md` §2.4). Workflow is a standalone root of the definitions
catalogue that **owns** its Steps (`DOMAIN_MODEL.md` §9.2); a Step has no identity or existence
outside its Workflow.

The execution core (Run / Task / Output / Artifact / Human Review / Schema) is complete and
frozen as a minimal baseline (`ARCHITECTURE_FREEZE.md`). This ADR is the **gate-opener** for the
declarative layer: it records the **interface contract** for Workflow + Workflow Step as a
**pure data model** layered *above* the existing execution core, plus the **minimal additive
expansion** of the Content Director that turns a Workflow into the existing Task sequence. It
introduces **no engine**: no scheduler, no DAG runtime, no state machine, no event-driven or
reactive execution. It mirrors ADR-0004…0008 (minimal faithful subset + explicit deferrals) and
is additive (`PROJECT.md` §4.11): Run / Task / Output / Schema and the execution flow are
**unchanged**. This ADR also **canonises the term "Workflow Step"** into `PROJECT.md` §18's
vocabulary via the ADR process (`DOMAIN_MODEL.md` Appendix A; `PROJECT.md` §17, §19). No code is
written here; implementation waits for `WORKFLOW_SPEC.md` → `WORKFLOW_ACCEPTANCE.md`.

## Decision

### 1. Placement & nature
Workflow symbols live in a new module `omemo_content_factory.domain.workflow`: `WorkflowId`,
`StepId`, `WorkflowStep`, `Workflow`, and the Workflow domain errors. The module depends on
**nothing** in `run`/`task`/`output`/`schema` (one-directional: the application layer may read a
Workflow; the domain execution core never imports it). Cross-entity references (`agent_ref`,
`schema_ref`) are **opaque `str`** (ADR-0003 §3). Workflow is a **pure data model**: it is not
executed, holds no execution logic, and does not know Run, Task or Output.

### 2. Workflow — aggregate root (immutable composition)
`Workflow` is the aggregate root of its Steps (`DOMAIN_MODEL.md` §9.2). It is an **immutable
value** (a frozen, slotted dataclass): it has no status and no transitions. Re-arranging steps is
not a mutation — it is a **new Workflow value** (satisfying "принятая версия неизменяема",
`DOMAIN_MODEL.md` §6, by total immutability). Steps exist **only** as part of a Workflow; there is
no standalone Step factory or independent Step lifecycle.

### 3. Workflow Step — child data of a Workflow
`WorkflowStep` is an **immutable** frozen dataclass with no identity outside its owning Workflow
(`DOMAIN_MODEL.md` §2.4). It carries the declaration of one step; it holds no execution state
(execution state lives on Task, which is created at runtime and is out of this module).

### 4. Attributes (minimal faithful subset)
Implemented now (the user's minimal brief, mapped to `DOMAIN_MODEL.md` §2.3/§2.4):

- **Workflow:** `workflow_id` (stable identity), `name`, `steps` (ordered, non-empty).
- **WorkflowStep:** `step_id` (unique within the Workflow), `task_type` (`str`), `agent_ref`
  (opaque `str` — the role; `DOMAIN_MODEL.md` §6 "ровно один Agent"), `schema_ref` (opaque `str`
  — the step's output contract; the Schema entity already exists, ADR-0008), `depends_on`
  (list of `step_id`s — declarative metadata, see §6).

### 5. Construction-time invariants (data integrity only)
Validated when a Workflow is constructed (a malformed declaration is a domain error, not a runtime
failure):

- **Non-empty.** A Workflow has **at least one** step (`DOMAIN_MODEL.md` §6).
- **Unique step ids.** `step_id`s are unique within the Workflow.
- **Referential `depends_on`.** Every id in a step's `depends_on` refers to a `step_id` that
  exists in the same Workflow.

These are **pure data checks**. No ordering, topological sort or cycle detection is performed (that
would be a DAG engine — forbidden); cycle/duplicate-dependency analysis is **deferred**.

### 6. Execution-order model — `depends_on` is descriptive, not executed
**Execution order is strictly defined by the list order of `Workflow.steps`.** `depends_on` is
**pure metadata only** and **MUST NOT** affect execution order, scheduling or runtime control flow.
In particular it MUST NOT be used:

- as a **DAG**;
- for **scheduling**;
- to **optimise or reorder** execution.

The Content Director executes steps in their **declared list order** (§8); it does **not** resolve
dependencies, reorder, parallelise or schedule by `depends_on`. Dependency-driven ordering, parallel
branches and DAG semantics are **deferred** (they are exactly the forbidden "engine").

### 7. Workflow model scope — pure declarative plan (v1 static model)
**Workflow is a pure declarative execution plan (v1 static model).** It has: **no runtime state**,
**no lifecycle** (`Draft/Active/Deprecated` excluded), **no versioning logic inside Workflow**,
**no scheduling semantics**, and **no execution-engine responsibilities**.

Workflow's documented lifecycle `Draft → Active → Deprecated`, its `version`, the `Content Type`
reference, **Approval Gates**, **terminal conditions**, the step's **input contract** and the
**is-checkpoint** flag (`DOMAIN_MODEL.md` §2.3/§2.4/§6) are **deferred** — kept as documented
vocabulary, not modelled now. Because Workflow is total-immutable data, no status machine is
introduced. `DOMAIN_MODEL.md` §10 defines **no** Workflow/Workflow Step domain events, and
Workflow is a catalogue definition (not a Run child) — so **no domain events** are introduced.

### 8. Integration — minimal Content Director expansion (no core change)
The Content Director gains **one thin, additive** capability: given a `Workflow`, it **expands** the
Steps, in declared order, into the **existing** `TaskRequest` sequence and calls the **existing**
`execute` pipeline unchanged. Each Step maps to a `TaskRequest` (`workflow_step_ref` = `step_id`,
`agent_ref` = step's `agent_ref`, plus the input/`artifact_kind` the existing API already takes).
Nothing in `execute`, `execute_task`, Run, Task, Output or Schema changes; the validated/legacy
Output paths and `schema_ref` usage are untouched. The Content Director does **not** become an
engine — it performs a one-shot translation, then runs the same imperative orchestration as today.

**Content Director semantics (clarified).** The Content Director is a **deterministic execution
scheduler** that maps `Workflow.steps → Task` sequence in **strict list order**. It:

- does **not** interpret `depends_on`;
- does **not** build a graph;
- does **not** perform order optimisation;
- only **unrolls the linear plan** into the existing Task sequence.

### 9. Errors
Co-located in `domain.workflow`: base `WorkflowDomainError` + `EmptyWorkflowError`,
`DuplicateStepIdError`, `UnknownDependencyError` (a `depends_on` id not present among steps).
Immutability is enforced structurally by the frozen dataclasses (a `FrozenInstanceError`), so no
dedicated immutable-attribute error is introduced (as with Output, ADR-0005 §8). The shared
`DomainError` base remains a separate follow-up (ADR-0005 §9), not done here.

### 10. Term canonisation
This ADR **canonises "Workflow Step"** as a domain term per `DOMAIN_MODEL.md` Appendix A and
`PROJECT.md` §17/§19. "Workflow" is already canonical (`PROJECT.md` §18). No edit to `PROJECT.md`
is made here; this ADR is the traceable canonisation record.

### 11. Architectural clarification, intent & correctness
**Workflow does not execute anything and does not influence runtime behaviour directly.** It is a
declarative overlay **external** to the execution core and is **resolved into Tasks only at the
Content Director level**; the Content Director remains the **single point of execution**.

**Architectural intent (confirmed, unchanged):**
- Run / Task / Output / Schema execution core remains **unchanged**.
- Workflow is an **external declarative overlay**, not part of the core.
- The freeze (`ARCHITECTURE_FREEZE.md`) applies to the **execution core only**, not to the design
  phase — this ADR is the design step.

**Criteria of correctness (this ADR is correct iff):**
- removing Workflow leaves the system working unchanged (the core never depends on it);
- the Content Director stays the **only** point of execution;
- there is **no** hidden DAG/engine semantics in Workflow.

## Non-goals (explicit — never introduced implicitly)
- no DAG engine;
- no scheduler;
- no reactive execution graph;
- no dependency-resolution engine;
- no workflow runtime system.

`depends_on` never triggers any of the above; it is inert metadata (§6).

## Deferred (need their own decision; not implemented)
- Workflow **lifecycle** (`Draft → Active → Deprecated`), **versioning** and a multi-version
  container; **Content Type** reference; **Approval Gates**; **terminal conditions**.
- Workflow Step **input contract** and **is-checkpoint** flag.
- Any **dependency-driven** behaviour: ordering by `depends_on`, parallel branches, cycle
  detection — i.e. a DAG/scheduler/engine of any kind.
- A runtime Workflow Engine, reactive/event-driven execution, retry/scheduler systems.
- A shared `DomainError`/`DomainEvent` base.

## Consequences

### Positive
- Adds the first **declarative layer** above the frozen execution core, faithfully to
  `DOMAIN_MODEL.md` §2.3/§2.4/§9.2, **without** an engine and **without** touching Run / Task /
  Output / Schema or the execution flow.
- Removing a Workflow leaves the system behaving **exactly** as before (the core never depends on
  it); VALID/INVALID logic and Schema's role as a contract are unchanged.
- Establishes the catalogue-definition pattern for the remaining definitions (Agent, Content Type).

### Negative / Trade-offs
- `Workflow` is a deliberately **partial** realisation of `DOMAIN_MODEL.md` §2.3/§2.4 (deferrals
  above), to be completed when lifecycle/versioning/Content Type/Approval Gates land.
- `depends_on` is captured but inert in this slice; honouring it requires a future ordering
  decision (its own ADR), explicitly out of scope to avoid an engine.

## Alternatives considered
- **A runtime Workflow Engine / DAG scheduler now** — rejected: forbidden by this stage's scope
  and `ARCHITECTURE_FREEZE.md`; Workflow is declaration, execution stays the existing core.
- **Give Workflow a status lifecycle (like Schema) now** — rejected: the brief is pure data with
  no state machine; total immutability already satisfies "accepted version is immutable".
- **Resolve `depends_on` for execution order** — rejected: that is DAG semantics (an engine);
  declared list order is the minimal faithful choice.
- **Make Workflow Step its own aggregate root** — rejected: contradicts `DOMAIN_MODEL.md` §9.2
  (Workflow owns its Steps; a Step has no identity outside its Workflow).
- **Expand a Workflow inside `execute`/`execute_task`** — rejected: would change existing
  signatures/behaviour; the translation belongs in a new thin Content Director method.

## References
- `DOMAIN_MODEL.md`: §2.3 (Workflow), §2.4 (Workflow Step), §5 (relationships), §6 (Workflow /
  Workflow Step invariants), §9.2 (Workflow owns Steps), §10 (no Workflow events), Appendix A
  (canonisation of "Workflow Step")
- `PROJECT.md`: §4.11 (additive extension), §17, §18 (Workflow canonical; Workflow ≠ Orchestrator),
  §19 (term consistency)
- `ARCHITECTURE.md`: §4 (Content Director executes Workflow), §5 (Workflow Engine vs declaration)
- `ARCHITECTURE_FREEZE.md` (freeze = gate on implementation; this ADR is the design step)
- `ADR-0003`…`ADR-0008` (the templates this mirrors)
- `ROADMAP.md` stage: 2 (data models and contracts) / 3 (Content Director)
