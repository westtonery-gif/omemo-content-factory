# ADR-0006: Artifact entity — Run↔Artifact interface contract

- **Status:** Accepted
- **Date:** 2026-06-26
- **Deciders:** Lead Architect / Domain Architect

## Context

`Artifact` is the **unit of produced content** of a Run (`DOMAIN_MODEL.md` §2.12): a child entity
of the `Run` aggregate root, owned **directly by Run** (§9.1), carrying provenance to the
`Output` it was produced from. It is **not** its own aggregate root and has no independent
existence. `ADR-0004`/`ADR-0005` are the templates this mirrors.

The domain fully **defines** Artifact, but most of its lifecycle depends on concepts that are
**out of scope** for this stage (Human Review, QA, versioning/rework). This ADR records the
**minimal faithful subset** to implement now and what is deferred and why. It is an additive,
Open/Closed extension (`PROJECT.md` §4.11): Run/Task/Output existing behaviour, signatures and
tests are unchanged; only new operations are added. It records only a **technical contract** and
does not change the domain model.

## Decision

### 1. Placement
Artifact symbols live in `omemo_content_factory.domain.artifact`: `ArtifactId`,
`ArtifactStatus`, `Artifact`, `ArtifactView`, the Artifact domain event(s) and errors. The module
depends on nothing in `run`/`task`/`output` (one-directional: `run` imports from it), so its
references (`run_id`, `output_ref`) are plain opaque `str` (ADR-0003 §3) — also avoiding cycles.
**Artifact is created only via `Run.create_artifact`** — no aggregate-driving factory elsewhere.

### 2. Representation — mutable status, immutable everything else
`Artifact` is modelled like Task (slotted class + guarded `__setattr__`): its identity,
`run_id`, `output_ref` (provenance), `kind`, `content` and `version` are **write-once
immutable**; only `status` changes (its own lifecycle). Because it is mutable, it is exposed as a
read-only **`ArtifactView`** snapshot — no mutable Artifact object leaves the aggregate.

### 3. Attributes (minimal faithful subset of `DOMAIN_MODEL.md` §2.12)
`artifact_id` (stable identity), `run_id` (owning Run), `output_ref` (provenance — the `Output`
it was produced from), `kind` (opaque `str`: structure/draft/edited/… — the classifier),
`content` (the produced content, copied from the Output's payload), `version` (within the Run;
**always `1`** while versioning is deferred), `status: ArtifactStatus`.

### 4. Lifecycle — `ArtifactStatus`
`ArtifactStatus = {DRAFT, CANDIDATE, APPROVED, REJECTED, SUPERSEDED, PUBLISHED}` (the documented
states, §2.12). An Artifact is **created in `DRAFT`**. The **only wired transition is
`DRAFT → CANDIDATE`** (the Content Director presenting it as a review candidate). The rest are
**deferred** because they depend on out-of-scope concepts: `APPROVED`/`REJECTED`/`PUBLISHED`
require **Human Review** (and publication); `SUPERSEDED` requires **versioning/rework**. Those
states remain as documented vocabulary; their edges are not allowed yet.

### 5. Origin — created only from an existing Output, 1:1
`create_artifact` accepts an `output_id` that must reference an **existing** recorded Output of
the Run (else `KeyError`, consistent with `transition_task`'s unknown-id handling), and that
Output must not already have produced an Artifact (**1:1**, else `DuplicateArtifactError`). The
new Artifact's `content` is taken from that Output's payload, and `output_ref` records the
provenance. (`DOMAIN_MODEL.md` allows an Output to produce *several* Artifacts; this slice
restricts to **1:1** per the current task — 1:N is deferred.)

### 6. Run's additive public API (the contract)
- `create_artifact(output_id, *, kind, by) -> ArtifactId` — creates a `DRAFT` Artifact from an
  existing Output through the root, emits `ArtifactCreated`, returns its id. Authorised actor
  only (reuses Run's `UnauthorizedActorError`).
- `transition_artifact(artifact_id, to, by) -> None` — single guarded mutation: actor
  authorisation + Artifact allowed-transitions table (`DRAFT → CANDIDATE`).
- read-only access: `artifacts` (sequence of `ArtifactView`) and `artifact(artifact_id) ->
  ArtifactView`. No mutable Artifact is exposed.

### 7. Task's additive surface
Task exposes a read-only `output` property (the owned Output, or `None`) so the root can read an
Output's payload when creating an Artifact from it. Task behaviour is otherwise **unchanged**.

### 8. Events
`ArtifactCreated` (`DOMAIN_MODEL.md` §10) is recorded in the Run's **existing single event log**;
the log's type is broadened additively to include `ArtifactEvent`. `DRAFT → CANDIDATE` emits no
event (no event is documented for it; cf. Task `SKIPPED`). `ArtifactApproved`/publication events
are deferred with Human Review.

### 9. Errors
Co-located in `domain.artifact`: base `ArtifactDomainError` + `InvalidArtifactTransitionError`,
`DuplicateArtifactError`, and `ImmutableArtifactAttributeError` (the guard, for parity with Task).
Authorisation reuses Run's `UnauthorizedActorError`. The shared `DomainError` base remains a
rule-of-three follow-up (see ADR-0005 §9), not done here.

### 10. Application wiring (no new domain coupling)
`execute_task` is **unchanged** (it stays Task → Output). `ContentDirector.execute` creates an
Artifact from each produced Output (via `Run.create_artifact`), with the `kind` taken from the
new optional `TaskRequest.artifact_kind` (default `"draft"`). Existing callers that produce no
Output (no `schema_ref`) create no Artifact, so existing behaviour and tests are unchanged.

## Deferred (depend on out-of-scope concepts; explicitly not implemented)
- Lifecycle beyond `DRAFT → CANDIDATE`: `APPROVED`/`REJECTED`/`PUBLISHED` (need **Human Review**),
  `SUPERSEDED` (needs **versioning/rework**).
- Output→Artifact **1:N** (an Output producing several Artifacts).
- Artifact `version` > 1 and the new-version mechanism.
- A shared `DomainError`/`DomainEvent` base — rule-of-three follow-up (separate ADR).

## Consequences
**Positive:** a successful Task now yields a real, traceable content unit with provenance
(`Task → Output → Artifact`); the root↔child contract extends cleanly again; Run/Task/Output
reference behaviour and tests stay green; immutable content/provenance, owned through root, no
infrastructure.
**Negative / Trade-offs:** Run's public API grows (additively); `Artifact` is a deliberately
partial realisation of `DOMAIN_MODEL.md` §2.12 (deferrals above), completed when Human
Review / QA / versioning land.

## Alternatives considered
- **Model the full Draft→Candidate→Approved→Published lifecycle now** — rejected: needs the
  excluded Human Review/QA and versioning; would be speculative machinery (`PROJECT.md` §4.11).
- **Create the Artifact inside `execute_task`** — rejected: would change an existing slice's
  signature/behaviour and couple it to Artifact; orchestration belongs in the Content Director.
- **Output→Artifact 1:N now** — rejected: out of this task's scope; 1:1 per instruction.
- **Make Artifact a separate Aggregate Root** — rejected: contradicts `DOMAIN_MODEL.md` §9.1.

## References
- `DOMAIN_MODEL.md`: §2.11 (Output), §2.12 (Artifact), §5, §6 (Artifact invariants), §7,
  §9.1 (Run owns Artifact), §10 (`ArtifactCreated`)
- `PROJECT.md`: §4.11, §9, §17, §18
- `ADR-0003`, `ADR-0004`, `ADR-0005` (the templates this mirrors)
- `ROADMAP.md` stage: 2 (data models and contracts)
