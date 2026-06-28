# ADR-0011: Agent + Prompt binding layer

- **Status:** Accepted (Revision 2 — corrective: Agent is a **pure descriptor**, not an
  execution-configuration layer; explicit mapping/description/execution separation)
- **Date:** 2026-06-28
- **Deciders:** Lead Architect / Domain Architect

## Context

`ADR-0010` fixed the **Agent boundary** (a pure, non-execution role descriptor; no orchestration;
`agent_ref` used only at execution-Task level; no influence on Workflow/Run/ContentDirector core).
This ADR defines the **binding contract**: how an opaque `agent_ref` connects to a role's
**Prompt**.

**Revision 2 — why.** The previous draft let an Agent *configure the TaskExecutor* (the Prompt was
"bound into" the executor). That gives Agent **execution-configuration semantics** and crosses the
`ADR-0010` boundary-only model. This revision narrows Agent to a **strict pure descriptor** and
fixes the three-layer separation. `Agent`/`Prompt` are canonical terms (`PROJECT.md` §18) defined in
`DOMAIN_MODEL.md` §2.5 / §2.7.

Overriding intent (unchanged):

> **Agent = execution-time mapping (description), NOT a system-intelligence or configuration layer.**

No change to `Run`/`Task`/`Output`/`Schema`; no extension of `Workflow`; no change to
`ContentDirector`.

## Decision

### 1. Agent — a pure descriptor (description only)
An `Agent` (identity `AgentId`) is an **immutable descriptor** that maps `agent_ref → Prompt`. That
is all it does. It is **queried, never acts**. It has:
- **no configuration semantics** (it does not configure or build any executor),
- **no executor/behaviour selection** (it does not choose which executor or behaviour runs),
- **no runtime execution influence** (it does not participate in execution, planning or ordering).

It carries the role's identity, its `agent_ref`, the reference to its **Prompt**, and the role's
output contract (`schema_ref`, opaque). Nothing else.

### 2. Prompt — immutable artifact (text only)
`Prompt` (identity `PromptId`, `PromptVersion` VO) is an **immutable execution artifact**: the
prompt **text** (System/User templates), its version, and the output `schema_ref` it conforms to
(`DOMAIN_MODEL.md` §2.7; `PROJECT.md` §15). It never mutates; a change is a **new version**. It
holds **no orchestration logic** and has **no influence on Workflow semantics**. An Agent references
its active Prompt (active binding **1:1**; conceptually **N:1** across versions — multi-version
catalogue deferred).

### 3. `agent_ref → Prompt` is a pure read lookup
Resolving `agent_ref` to its Prompt is a **pure, side-effect-free data lookup** over the Agent
descriptors. It is **not** performed in `Workflow` (pure declarative data), **not** during plan
**expansion** / **Run planning**, and **not** as new logic in `ContentDirector`. The Agent layer
**describes**; it does not execute, configure or route.

### 4. Three-layer separation (the boundary, made explicit)
```
   ContentDirector  → MAPPING only     (positional steps -> tasks; selects executor by agent_ref)
   Agent            → DESCRIPTION only  (agent_ref -> Prompt text; pure immutable data)
   TaskExecutor     → EXECUTION only    (runs a step's work; no Agent lookup, no Workflow/Step)
```
- **ContentDirector — mapping only.** Unchanged: positional `Workflow.steps → TaskRequest[]`
  (`ADR-0009`) and selecting an executor by `agent_ref` (`ARCHITECTURE.md` §4). It does **not**
  read Agents or Prompts.
- **Agent — description only.** A pure descriptor (§1); it does not configure executors or influence
  runtime.
- **TaskExecutor — execution only.** Unchanged `execute(task_input) -> ExecutionResult`. It does
  **not** receive `Workflow`/`WorkflowStep`, does **not** look up Agents, and contains **no**
  resolution/configuration logic. It runs work with whatever it was given.

### 5. Where Prompt text meets execution — out of Agent's scope (application wiring)
Because all three layers above are pure, **delivering a Prompt's text into the execution step is
NOT a responsibility of Agent, ContentDirector or TaskExecutor.** It is an **application-wiring /
composition-root** concern (the entry point that already assembles the per-role executor mapping).
ADR-0011 defines **only** the Agent descriptor and its read contract; the delivery mechanism is
**deferred** to that wiring and is intentionally **not** placed in any of the three layers. (This
keeps Agent strictly a descriptor and ContentDirector strictly a mapper.)

### 6. Placement — no core, Workflow or ContentDirector change
`Agent`/`Prompt` live in the domain (`domain.agent` / `domain.prompt`) as immutable descriptors;
cross-entity references (`schema_ref`) are opaque `str` (ADR-0003 §3). The Agent descriptor catalogue
(`agent_ref → Agent`) is read-only data. No new behaviour in `ContentDirector`, no execution
semantics in `Workflow`, no change to `Run`/`Task`/`Output`/`Schema`.

## Hard non-goals (this ADR MUST NOT)
- Give `Agent` any **configuration semantics**, **executor/behaviour selection**, or **runtime
  execution influence** (Revision 2 core correction).
- Turn `Agent` into an orchestrator; introduce conditional behaviour, branching or planning.
- Add resolution/binding/configuration logic to `ContentDirector`, or couple `Agent` to it.
- Make `TaskExecutor` look up Agents, or receive `Workflow`/`WorkflowStep`.
- Extend `Workflow`, or let `Agent`/`Prompt` affect Workflow execution order.
- Change `Run`/`Task`/`Output`/`Schema`.

## Correctness criteria (the contract is correct iff)
- **Agent removable** → `Workflow` + Run core keep working (executors are injected directly, as
  today's tests/demo do); the Agent layer is purely descriptive data.
- **Prompt replaceable** → the **structure** of execution is unchanged (only text/output differs).
- **`ContentDirector` unchanged** → mapping only; it never reads an Agent or Prompt.
- **`TaskExecutor` unchanged** → execution only; it never looks up an Agent and takes no Workflow.
- **Agent has no code path** that configures, selects or influences execution — it is pure data
  that is *read*, never *acts*.

## Deferred
- The **delivery mechanism** of Prompt text into execution (application-wiring / composition root).
- Multi-version Prompt **catalogue** (history/activation) — only the active 1:1 binding is modelled.
- `Skill` / `Tool` composition; model selection (external config, `PROJECT.md` §5); QA/Evaluation;
  Prompt Examples / Evaluation-Criteria mechanics. Shared `DomainError` base (rule-of-three).

## Consequences

### Positive
- Agent is strictly a **descriptor** — the "hidden behaviour/configuration engine inside the Agent
  layer" risk is structurally removed; `ADR-0010` boundary-only is honoured.
- The three responsibilities are crisp and non-overlapping (mapping / description / execution),
  preventing drift.

### Negative / Trade-offs
- ADR-0011's scope shrinks: it defines Agent/Prompt **as data only**; the prompt-text→execution
  delivery is deferred to wiring (a deliberate, named gap, §5) rather than decided here.
- `Agent`/`Prompt` are a deliberately partial realisation of `DOMAIN_MODEL.md` §2.5/§2.7 (deferrals
  above).

## Alternatives considered
- **Agent configures / builds the TaskExecutor** (previous draft) — rejected: gives Agent
  execution-configuration semantics, crossing the `ADR-0010` boundary; the cause of Revision 2.
- **TaskExecutor looks up the Agent** — rejected: gives the execution layer description/lookup
  responsibility; violates "execution only" (§4).
- **ContentDirector reads Agents/Prompts** — rejected: gives the mapper description logic; violates
  "mapping only" and the "CD unchanged" criterion.
- **Mutable Prompt / Agent picks its own next step** — rejected: violates immutability
  (`DOMAIN_MODEL.md` §6) and the deterministic-orchestrator invariant (`PROJECT.md` §4 п.2).

## References
- `PROJECT.md`: §4 п.2, §5, §8, §15 (Prompt architecture), §17, §18
- `ARCHITECTURE.md`: §4 (Content Director), §6 (Agent architecture)
- `DOMAIN_MODEL.md`: §2.5 (Agent), §2.7 (Prompt), §6 (immutability), §9.3 (Agent owns Prompt)
- `ADR-0010` (Agent boundary — non-execution), `ADR-0009` (Workflow), `ADR-0008` (Schema),
  `ADR-0003` (opaque refs)
- `ROADMAP.md` stage: 7 (first working Agent)
