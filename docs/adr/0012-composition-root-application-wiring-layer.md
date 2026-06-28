# ADR-0012: Composition Root (Application Wiring Layer)

- **Status:** Accepted (strict dumb wiring layer — deterministic construction only)
- **Date:** 2026-06-28
- **Deciders:** Lead Architect / Domain Architect

## Context

`ADR-0011` (Rev 2) keeps `Agent` a **pure descriptor** and `Prompt` an **immutable artifact**, and
deliberately leaves the **delivery of Prompt text into execution** out of the three pure layers
(ContentDirector = mapping, Agent = description, TaskExecutor = execution; `ADR-0011` §4–§5). That
delivery has to live **somewhere**. This ADR fixes that "somewhere" as an explicit, separate layer:
the **Composition Root (Application Wiring Layer)** — the assembly/entry-point layer that already
builds the per-role executor mapping today (e.g. the demo / entry point).

This is consistent with `PROJECT.md` §6 (dependencies passed explicitly — DI, no global state) and
§7 / `ARCHITECTURE.md` §15 (entry points and integration are the outermost layer). It introduces
**no domain entity** and changes **no code**; it names and constrains an existing application
responsibility so the system's layering stays drift-proof.

## Decision

We recognise a distinct **Composition Root (Application Wiring Layer)** as the outermost
application layer.

### 1. Responsibilities
- **`agent_ref → Prompt` resolution** — read the Agent descriptors (`ADR-0011` §3) to obtain a
  role's immutable Prompt.
- **Assemble the execution context** — construct executors injected with the resolved Prompt, and
  provide the per-role `agent_ref → TaskExecutor` mapping that `ContentDirector` selects from.
- **Wiring between layers** — compose the system: inject the executor mapping into
  `ContentDirector`, supply ports (LLM client, etc.) per `PROJECT.md` §6.

### 2. Constraints (what it is NOT) — a strict **dumb** wiring layer
- It is **not** `ContentDirector` (it performs no mapping of `Workflow.steps → Task` and no
  orchestration).
- It is **not** a `TaskExecutor` (it runs no Task work).
- It contains **no workflow logic**, **no execution logic**, and **no planning logic**.
- It **makes no decisions** and contains **no conditional logic**.
- It does **not optimise** the wiring.
- It does **not select** executors (selection by `agent_ref` at runtime stays `ContentDirector`'s).
- It does **not interpret** `agent_ref` (no per-`agent_ref` special-casing or branching) — the
  `agent_ref → Prompt` resolution is a **pure, uniform, deterministic lookup**, not interpretation.
- It is **external composition**, **not** a domain layer: it depends on the domain/application, the
  domain never depends on it (dependencies point inward, `PROJECT.md` §7).

### 2.1 Sole function — deterministic construction of the runtime graph
The Composition Root does exactly one thing: **deterministic construction of the runtime graph
(executors + wiring) from the static contracts (Agent / Prompt descriptors)**. Given the same static
contracts it always produces the same runtime graph — uniform, decision-free assembly. Building the
`agent_ref → TaskExecutor` mapping is **construction**, not **selection** (which executor *runs* a
step is decided later, by `ContentDirector`). *Rationale:* any decision, condition or optimisation
here would turn the Composition Root into a **hidden orchestration engine** — forbidden.

### 3. Relationship to the other layers (unchanged)
```
   Composition Root  → WIRING only       (agent_ref->Prompt resolution; build & inject executors)
   ContentDirector   → MAPPING only      (Workflow.steps->Task; selects executor by agent_ref)
   Agent             → DESCRIPTION only   (agent_ref->Prompt text; immutable data)
   TaskExecutor      → EXECUTION only     (runs a step; no Agent lookup, no Workflow/Step)
```
`ADR-0011` stays strictly **data-level**: Agent = descriptor only, Prompt = immutable artifact,
ContentDirector = mapping only, execution = TaskExecutor only. The Composition Root is where the
descriptor is *read* and executors are *assembled* — the one place allowed to connect Prompt text to
an executor, precisely so none of the three pure layers has to.

## Consequences

### Positive
- Closes the deferred gap of `ADR-0011` §5 without polluting any pure layer; layering stays crisp
  (wiring / mapping / description / execution).
- Matches the existing reality (the entry point already assembles the executor mapping), so it is a
  naming/constraint decision, not new machinery.

### Negative / Trade-offs
- One more named layer to honour in reviews; mitigated by the explicit constraints (§2).

## Alternatives considered
- **Put wiring in ContentDirector / TaskExecutor / Agent** — rejected: each would gain a foreign
  responsibility (configuration/lookup), breaking `ADR-0010`/`ADR-0011` purity.
- **Model the Composition Root as a domain layer** — rejected: it is outermost application
  composition; the domain must not depend on it (`PROJECT.md` §7).

## References
- `PROJECT.md`: §6 (explicit dependencies / DI), §7 (layers, entry points), §17
- `ARCHITECTURE.md`: §15 (repository / entry points), §3.3 (Python Agent Service entry points)
- `ADR-0011` (Agent + Prompt — data-level; deferred delivery), `ADR-0010` (Agent boundary),
  `ADR-0009` (Workflow)
- `ROADMAP.md` stage: 7 (first working Agent)
