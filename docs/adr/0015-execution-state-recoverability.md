# ADR-0015: Execution-State Recoverability and the Admission of Restored Runs

- **Status:** Accepted (architectural contract; the realization *form* is deferred to the next level)
- **Date:** 2026-06-29
- **Deciders:** Lead Architect / Domain Architect

## Context

`ARCHITECTURE.md` §10 ("State Management — объект Run") requires that an execution's state be **observable and recoverable at any moment**, with **idempotent resume** («Run восстанавливается из сохранённого состояния без дублирования уже выполненной работы»), **traceability by default** («шаг без записи трассировки считается несделанным») and **no secrets/PII**. `PROJECT.md` §10 states the idempotent-resume requirement; `ROADMAP.md` Stage 6 requires that execution state «переживает перезапуск». These are accepted, higher-authority requirements not yet expressed as an architectural contract at the ADR level.

The domain core is in place: **Run** is the aggregate and «единица состояния и аудита» (`ADR-0003`; `ARCHITECTURE.md` §10), owning **Task / Output / Artifact / Human Review** (`ADR-0004…0007`) and the domain-event journal; evaluation-ownership is **Variant A**, with the Content Director the sole owner of transitions (`ADR-0013` §8; `ARCHITECTURE.md` §10).

`ADR-0003` fixed the Run interface as a single construction entry (`create`, → the initial lifecycle state) plus guarded transitions, designed for a **single in-process execution**. No accepted ADR sanctions a Run that comes to exist **already at a non-initial lifecycle state** — which is exactly what continuation across a process boundary requires. Reconstructing state by replaying events is out of scope (`ARCHITECTURE_FREEZE.md` §3, "No event sourcing").

The subject, boundary, ownership criterion and invariants of this capability were stabilised through prior analysis; this ADR records them and closes the **single** remaining undetermined point. It introduces no storage, repository, or preservation mechanism — that is the next level.

## Decision

### 1. Recognise the capability (a recognition, not an invention)
We recognise, as an explicit architectural capability, the **recoverability of execution state** required by `ARCHITECTURE.md` §10 / `PROJECT.md` §10 / `ROADMAP.md` Stage 6, with the single responsibility:

> **Preserve the truth of each execution independently of the process, such that it can at any moment be fully observed and correctly continued — without losing or duplicating already-completed work.**

This restates accepted requirements; it adds no new requirement.

### 2. Boundary (derived; not a new decision)
By the owned-truth vs required-dependency criterion (*produced by and authoritative to this execution, exclusive to it, lifecycle-coupled* = owned; *pre-existing, authored elsewhere, shared, independent lifecycle* = dependency):

- **IN — owned authoritative truth of one execution:** Run; Task; Output; Artifact; Human Review; the domain-event journal; and — when it exists — the QA verdict (`ARCHITECTURE.md` §10). The recorded *references* to the versions used (`workflow_version_ref`, `schema_ref`, `agent_ref`) are owned facts held inside these.
- **OUT — not owned truth:** the **definitions** Schema / Workflow / Agent / Prompt; ContentDirector runtime state; LLMClient; the Composition Root; the Analytics Record; the log-only observability layer; caches; the (deferred) feedback loop and experience/memory; application configuration.
- **Required dependencies — preconditions, not subject:** the durable availability of the **used versions** of Workflow / Schema / Agent / Prompt. The Content Director reads the Workflow to compute the next transition (`ARCHITECTURE.md` §10); continuing or validating not-yet-executed steps needs the used Agent/Prompt/Schema versions. The execution owns the *reference* to a version; it depends on the *availability* of that version.

### 3. New decision — admission of a restored Run (closes O2)
`ADR-0003` sanctions a Run only at its initial state (`create`) and its advance by guarded transitions; the capability requires a Run to exist again, in a new process, at its **preserved** (non-initial) lifecycle state. We decide:

> **The architecture admits a *restored Run*: a Run instance brought into existence directly at its preserved lifecycle state, with its preserved children and event journal. A restored Run is the *same* aggregate — same identity, same type, same invariants — as the Run whose truth was preserved; from that state it advances under the *unchanged* `ADR-0003` transition contract.**

This admission is **purely additive** to `ADR-0003`: it does not alter `create`, the guarded-transition table, or any existing signature or behaviour (`PROJECT.md` §4.11; the additive-extension pattern of `ADR-0004…0007`). A restored Run introduces **no new entity** — it is the Run aggregate, reached by a different means of coming-into-existence.

The **form** by which a restored Run is brought into existence — and the form in which the truth is preserved — is **deliberately not decided here**; it is the subject of the next level. This ADR fixes only that restored Runs are *legitimate and additive*.

## Rationale

- **Why a restored Run cannot reuse `create` + replayed transitions.** Re-applying the recorded transitions from the initial state would re-create children and re-emit events that are *already part of the preserved truth*, duplicating recorded work and trace — violating **completeness/traceability** (no double record) and **idempotent continuation** (no duplication). Hence restoration must establish the preserved state, not replay progress. This is a derivation from the invariants, not a free choice — it is *why* a distinct means of coming-into-existence is required.
- **Why this does not contradict `ADR-0003`.** A restored Run does not *transition* into its state, so it bypasses no guard; it re-establishes a state the original Run had already reached **legally** (the preserved truth was produced only through authorized transitions — `ARCHITECTURE.md` §10 / `ADR-0013`). After restoration, guarded transitions apply normally, and the frozen reference implementation's interface is untouched (additive).
- **Why definitions are OUT (dependency, not subject).** They pre-exist the execution, are authored elsewhere, are shared across executions and versioned on an independent lifecycle; the execution owns only its *reference* to a used version (the foreign-key relation). This mirrors `LLMTaskExecutor`'s dependency on `LLMClient` and the Composition Root's dependency on `Prompt`: dependency is not membership.
- **Why O1 and O3 are not open.** O1 (authority of the event journal) is determined: event sourcing is out (`ARCHITECTURE_FREEZE.md` §3), so state is authoritative on the entities and not reconstructed from events, while the traceability invariant makes the journal a mandatory authoritative trace — both facets authoritative, neither derived. O3 (concurrent continuation) is excluded: a single runtime entry and a single owner of transitions (`ADR-0013`; `ARCHITECTURE.md` §10) already constrain continuation to a single continuator; concurrency is a future extension, not a decision of this ADR.

## Invariants

Carried by the capability (restatements of accepted rules; sources cited):
- **I1 — Process-independence.** The truth of an execution outlives the process. *(ARCH §10; ROADMAP Stage 6.)*
- **I2 — Completeness / traceability.** Everything that happened is present in the truth; an unrecorded step counts as not done. *(ARCH §10.)*
- **I3 — Idempotent continuation.** Continuation from the preserved truth neither loses nor duplicates completed work. *(PROJECT §10; ARCH §10.)*
- **I4 — Observability.** The truth is readable at any moment. *(ARCH §10.)*
- **I5 — Authorized mutation only.** The truth changes only through the Run's authorized transitions (Content Director); no out-of-band mutation. *(ARCH §10; ADR-0013 §8.)*
- **I6 — No secrets/PII.** The preserved truth contains no secrets or personal data. *(ARCH §10.)*

Specific to restoration:
- **I7 — A restored Run preserves identity and legality.** It is the same aggregate (same `run_id`, type, invariants) as the Run whose truth was preserved; it is admitted only at a state the original reached through legal transitions, and thereafter advances under the unchanged `ADR-0003` contract. *(Derived from I2/I5 + `ADR-0003`.)*

## Consequences

### Positive
- Expresses the accepted recoverability requirements (`ARCH §10` / `PROJECT §10` / `ROADMAP` Stage 6) as a bounded architectural contract, closing the single open point (O2) without inventing new model elements.
- Additive: the frozen Run reference implementation (`ADR-0003`) — `create` and the guarded transitions — is unchanged; a restored Run reuses the same transition contract.
- The boundary (IN / OUT / required dependencies) gives a precise, criterion-based test of what this capability owns versus what it depends on.

### Negative / Trade-offs
- The architecture now recognises **two ways a Run comes into existence** (created-at-initial-state, and restored-at-preserved-state); reviews must honour that a restored Run is still the same aggregate and is admitted only at legal states (I7).
- The capability declares a **required dependency** — durable availability of the used definition-versions — whose guarantee belongs to a separate concern (reference-data availability); until that is in place, correct continuation is not end-to-end operable.
- The **realization form** (how the truth is preserved, and how a restored Run is brought into existence) is deliberately deferred; this ADR alone does not make the capability operational.

## Open Questions

None remain at this architectural level. O1 was removed as a false open question and O3 as already determined (see Rationale); O2 is closed by §3. The realization form is not an open architectural question of this decision — it is the explicit subject of the next level (a subsequent SPEC/ADR) and is intentionally out of scope here.

## References
- `PROJECT.md` §10 (idempotent resume), §4.11 (additive extension)
- `ARCHITECTURE.md` §9 (adapters), §10 (State Management — Run), §15 (repository / layers)
- `ROADMAP.md` Stage 6 (state survives restart)
- `ADR-0003` (Run interface contract — frozen `create` + guarded transitions)
- `ADR-0004` / `0005` / `0006` / `0007` (Task / Output / Artifact / Human Review; additive extension of Run)
- `ADR-0013` (Execution topology; single owner of transitions; Variant A)
- `ARCHITECTURE_FREEZE.md` §3 (event sourcing out of scope)
