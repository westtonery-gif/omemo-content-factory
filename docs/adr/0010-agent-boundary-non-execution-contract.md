# ADR-0010: Agent boundary definition — non-execution role contract

- **Status:** Accepted
- **Date:** 2026-06-28
- **Deciders:** Lead Architect / Domain Architect

## Context

The next layer to build is **Agent** (`DOMAIN_MODEL.md` §2.5; `PROJECT.md` §8, §18;
`ARCHITECTURE.md` §6). It is the **first behavioural layer** of the system — the first place where
a role's prompt and behaviour live — and therefore the first concept that could **bleed into the
responsibilities** already held by `ContentDirector` (orchestration) and by the execution core
(`Run`/`Task`/`Output`/`Schema`).

Before the **binding contract** (how `agent_ref` resolves to a real execution role — deferred to
ADR-0011), this ADR fixes the **boundary**: what an Agent **is** and, crucially, what it **is
not**. It is a *constraining* decision, not an implementation, and introduces **no new entity** —
Agent is already a canonical term (`PROJECT.md` §18) defined in `DOMAIN_MODEL.md` §2.5. It records
a boundary so that the later Agent layer cannot drift into an orchestrator/engine.

This preserves the established invariants: the deterministic orchestrator / non-deterministic agent
split (`PROJECT.md` §4 п.2), the declarative Workflow layer (`ADR-0009`), and the stable minimal
architecture baseline (`ARCHITECTURE_FREEZE.md`). The freeze gates **implementation**, not design;
this ADR is design only.

## Decision

We define the **Agent boundary** as a *non-execution role contract*. The following hold for the
Agent layer in this architecture:

### 1. Agent is a pure execution-role descriptor
An Agent **describes a role** — its prompt and behaviour (`Agent = prompt + behavior definition`),
its narrow responsibility, and its typed output contract (a `schema_ref`). It is **not** an engine
and **not** an orchestrator. (`PROJECT.md` §8; `DOMAIN_MODEL.md` §2.5; `ARCHITECTURE.md` §6.)

### 2. Agent contains no orchestration / planning / scheduling logic
An Agent does **not**: decide what runs next, sequence steps, schedule, branch the pipeline, retry
across steps, or resolve dependencies. All control flow stays in the deterministic orchestrator
(`ContentDirector`), exactly as today (`PROJECT.md` §4 п.2; `ADR-0009`). The Agent reasons only
**within its own single step**.

### 3. Agent does not influence Workflow execution order
The execution order is **strictly** `Workflow.steps` list order (`ADR-0009` §6). An Agent — and the
choice of which Agent runs a step — **does not** reorder, skip, add or remove steps, and does not
read or act on `depends_on`. Workflow remains a declarative layer; Agents do not give it runtime
semantics.

### 4. `agent_ref` resolves only at the execution-Task level
The opaque `agent_ref` (carried by `WorkflowStep` and by `TaskRequest`) is resolved to a concrete
execution role **only when a Task is executed** — i.e. inside the existing execution path
(`ContentDirector` resolving an executor by `agent_ref`, `Task` running it). It is **not** resolved
by Workflow (which stays pure data) and **not** during plan expansion (which stays a positional
mapping, `ADR-0009` §8). Resolution is a runtime, per-Task concern.

### 5. Agent does not bypass or alter the execution core
An Agent never mutates `Run`/`Task`/`Output`/`Schema` directly and never bypasses the Run aggregate
root. Its result enters the system **only** through the existing execution path (the `TaskExecutor`
port → `Task` → `Output`), and validity is decided **only** by `Schema` (`ADR-0008`). The Agent
produces a result; it does not record domain state.

### 6. Placement relative to existing components (unchanged responsibilities)
- **ContentDirector** remains the **only** orchestrator/adapter over the execution core; it gains
  no engine behaviour from the Agent layer.
- **Workflow** remains declarative; Agents add no execution semantics to it.
- **Execution core** (`Run`/`Task`/`Output`/`Schema`) remains unchanged and isolated.
- The Agent layer connects to execution **behind the existing `TaskExecutor` port** — the concrete
  binding (Agent/Prompt → executor for an `agent_ref`) is the subject of **ADR-0011**, not here.

## Deferred (not decided here)
- The **Agent + Prompt interface contract** and `agent_ref` binding mechanics — **ADR-0011**
  (`AGENT_SPEC` / `AGENT_ACCEPTANCE` follow).
- Prompt versioning mechanics; Skill / Tool composition; model selection (external config,
  `PROJECT.md` §5); QA/Evaluation. All out of scope for this boundary.

## Consequences

### Positive
- Fixes the behavioural boundary **before** the first behavioural layer exists, preventing drift of
  Agent into orchestration/engine territory.
- Keeps the deterministic-orchestrator / declarative-Workflow / immutable-core invariants intact and
  explicit for the upcoming work.
- Makes ADR-0011 a **bounded** contract decision rather than an open-ended one.

### Negative / Trade-offs
- Adds one intermediate ADR (numbering: this boundary is ADR-0010; the binding layer becomes
  ADR-0011) — accepted for clarity and drift prevention.
- The boundary is **documentary**; it is enforced by review and by ADR-0011's contract/tests, not by
  a runtime guard (consistent with how prior boundaries are kept).

## Alternatives considered
- **Fold the boundary into the binding ADR (single ADR)** — rejected: the first behavioural layer
  warrants an explicit, focused non-execution contract before its interface is designed; mixing the
  two invites scope creep into orchestration.
- **Let Agent own some orchestration (e.g. choose next step / retry)** — rejected: violates
  `PROJECT.md` §4 п.2 and `ADR-0009`; control flow belongs to the deterministic orchestrator.
- **Resolve `agent_ref` at the Workflow level** — rejected: Workflow is pure declarative data
  (`ADR-0009`); resolution is a runtime, per-Task concern (decision §4).

## References
- `PROJECT.md`: §4 п.2 (deterministic orchestrator / non-deterministic agents), §8 (agent
  principles), §5 (model selection external), §17, §18 (Agent definition)
- `ARCHITECTURE.md`: §4 (Content Director), §6 (Agent architecture)
- `DOMAIN_MODEL.md`: §2.5 (Agent), §2.7 (Prompt)
- `ADR-0009` (Workflow declarative layer — execution order, expansion), `ARCHITECTURE_FREEZE.md`
- `ROADMAP.md` stage: 7 (first working Agent — this boundary precedes it)
