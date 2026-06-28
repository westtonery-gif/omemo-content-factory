# ADR-0013: Execution Topology Contract

- **Status:** Accepted
- **Date:** 2026-06-28
- **Deciders:** Lead Architect / Domain Architect

## Context

Four layers are now formally separated — `Workflow` (`ADR-0009`), `ContentDirector` (`ADR-0009`),
`Composition Root` (`ADR-0012`), `TaskExecutor` (`ADR-0011`) — plus the immutable execution core
(`Run`/`Task`/`Output`/`Schema`, `ADR-0003`…`0008`) and the Agent/Prompt descriptors (`ADR-0010`,
`ADR-0011`). They are separated, but their **single end-to-end execution contract** is not yet
written down in one place. Before adding the Agent layer (`AGENT_SPEC`), this ADR fixes that:
**where planning ends, where wiring happens, where execution begins, and the single entry into the
runtime graph.**

This is a **consolidating** decision over already-accepted ADRs. It introduces **no new entity**,
changes **no code**, and contradicts none of them — it names the topology so the boundaries cannot
drift as behavioural layers are added.

## Decision

### 1. The topology (end to end)
```
 [BUILD TIME]   Composition Root  — WIRING (dumb, deterministic construction; ADR-0012)
   static contracts (Agent/Prompt descriptors, executors, ports)
        ──►  builds  agent_ref → TaskExecutor  map  and  a wired ContentDirector
                         │
 [ENTRY]        Single runtime entry point
   create Run(brief)  +  choose Workflow  ──►  ContentDirector.execute_workflow(run, workflow, brief)
                         │
 [PLANNING]     ContentDirector — MAPPING (deterministic; ADR-0009)
   Workflow.steps  ──►  TaskRequest[]   (strict list order; depends_on inert)
                         │  then drives the Run lifecycle, per step:
 [SELECTION]    ContentDirector — selects TaskExecutor by agent_ref (deterministic; from the map)
                         │
 [EXECUTION]    TaskExecutor.execute(task_input) → ExecutionResult   (the execution boundary)
                         │
 [STATE]        Run / Task / Output (+ Schema validation)            (immutable execution core)
```

### 2. Where planning ends
**Planning** is declarative + deterministic and belongs to `Workflow` (the declared plan, data) and
`ContentDirector` (positional `Workflow.steps → TaskRequest[]`, list order, `depends_on` inert).
Planning **ends** the moment a `TaskRequest` is handed into execution — i.e. when `ContentDirector`
invokes the selected `TaskExecutor`. Nothing after that line plans; nothing before it executes.

### 3. Where wiring happens
**Wiring** is the `Composition Root` (`ADR-0012`): a **build-time**, dumb, deterministic
construction of the runtime graph (resolve `agent_ref → Prompt`, build executors, inject ports,
construct the wired `ContentDirector`). It happens **before any Run**, makes **no decisions**, and
does **not** plan or execute. Wiring **constructs** the graph; planning **traverses** it.

### 4. Where the execution boundary begins
**Execution** is `TaskExecutor.execute(task_input) -> ExecutionResult` — the **only** place a step's
work runs. It is the boundary at which **non-determinism is allowed** (the model lives here); it
receives only the Task input, never `Workflow`/`WorkflowStep`, never an Agent lookup (`ADR-0011`).
Beyond it, the immutable core records state and `Schema` decides validity (`ADR-0008`).

### 5. The single entry into the runtime graph
After the Composition Root has wired the `ContentDirector`, the runtime graph is entered through
**exactly one** call: `ContentDirector.execute_workflow(run, workflow, *, brief)`, where the entry
point has created the `Run` (`Run.create`) and chosen the `Workflow`. There is **one** runtime
entry; no layer bypasses the `Run` aggregate root, and no second path drives execution.

### 6. Determinism contract
Everything **except the inside of `TaskExecutor`** is deterministic: Workflow data, Composition Root
construction, ContentDirector mapping/selection, and the domain core. **Non-determinism is contained
strictly inside `TaskExecutor`** (`PROJECT.md` §4 п.2 — deterministic orchestrator, non-deterministic
agents). Same static contracts + same Workflow + same inputs ⇒ same topology and same routing.

### 7. Layer invariants (the contract)
- **Direction of dependencies points inward:** Composition Root → Application → Domain; the domain
  depends on none of them (`PROJECT.md` §7).
- **Each layer does one thing:** wiring (construct) · planning/mapping (traverse) · execution (run)
  · state (record). No layer performs another's role.
- **Descriptors are read only at wiring:** `Agent`/`Prompt` are read by the Composition Root only;
  `ContentDirector` and `TaskExecutor` never read them at runtime.
- **One entry, one root:** a single runtime entry (`execute_workflow`); all state changes go through
  the `Run` aggregate root.
- **Determinism boundary = `TaskExecutor`** (§6).

### 8. Execution Authority Model (Variant A — Run-owned state machine)
The topology (§1–§7) says *what runs where*; this section says **who owns the lifecycle state machine
and who triggers it**. The decided model is **Variant A: the state machine is owned by `Run`.** This
matches the existing implementation (`ADR-0003`) and avoids the hybrid where the machine would be
hidden inside `ContentDirector`.

- **`Run` owns the state machine.** The allowed-transitions table, the transition mechanism (the
  status mutation), the guards (valid edge **and** actor authorisation), the emitted events and the
  invariants all live **inside `Run`** (the aggregate root; `DOMAIN_MODEL.md` §6, §9.1). `Run` is the
  sole authority on *what transition is valid and what performs it*. An invalid request is **rejected
  by `Run`** regardless of the caller.
- **`ContentDirector` is the trigger / orchestrator — it does NOT own the state machine.** It owns
  only the **orchestration policy**: *which* valid transition to request and *when* (e.g. after the
  Task sequence runs, request `RUNNING → WAITING_QA`; on failure, request `→ FAILED`). It
  **requests** transitions through the `Run` API; it cannot define, widen or bypass them. There is
  **no state machine in `ContentDirector`** — only sequencing policy.
- **Authorisation is a Run-enforced rule, not CD ownership.** "Only `Actor.CONTENT_DIRECTOR` may
  change `Run` state" (`DOMAIN_MODEL.md` §6) is a guard **enforced by `Run`**: it accepts transition
  requests **only** from that actor. It names the single *permitted requester*; it does **not** move
  the machine into `ContentDirector`.
- **Initiation & single entry.** Creation (`Run.create → CREATED`) is the entry point's act;
  **execution initiation** is `ContentDirector` *requesting* the first lifecycle transition. The
  lifecycle is triggered through `ContentDirector` **only** (runtime entry `execute_workflow`, §5;
  `execute` is the same trigger authority). **Birth ≠ execution.**
- **Prohibition on alternative execution entry paths.** No component other than `ContentDirector`
  may **trigger** a `Run`'s lifecycle (no external transition requests to run the pipeline, no
  bypass, no parallel "runner"). `Run` structurally rejects non-`CONTENT_DIRECTOR` requests; review
  enforces that the entry point only *creates* the `Run` and *invokes* `ContentDirector`.

> Authority summary (Variant A): **state-machine owner = `Run`** (table, guard, mutation, events,
> invariants); **trigger/orchestrator = `ContentDirector`** (requests valid transitions; owns only
> the sequencing policy, never the machine); **creation = entry point**; **no alternative trigger
> path**. `ContentDirector` holds *policy*, `Run` holds the *machine* — no hybrid, no hidden state
> machine in the orchestrator.

## Non-goals
- No code change, no new entity, no new runtime engine. This ADR **describes and constrains** the
  existing topology; it does not add machinery.
- Does not introduce scheduling, branching, DAG or retry anywhere (forbidden by `ADR-0009`/`0010`).

## Consequences

### Positive
- One authoritative boundary model: planning / wiring / execution / state are unambiguous before the
  first behavioural layer (Agent) is specified.
- Makes future drift detectable — any new code that crosses a line (e.g. wiring that decides,
  executor that plans) is visibly a violation.

### Negative / Trade-offs
- A consolidating document to keep in sync with `ADR-0009`…`0012` (they remain the per-layer source;
  this one is the synthesis).

## Alternatives considered
- **Leave the topology implicit across four ADRs** — rejected: the single end-to-end contract is
  exactly what prevents drift as behavioural layers arrive.
- **Fold the topology into `AGENT_SPEC`** — rejected: topology is system-wide, not Agent-specific;
  it must precede and bound the Agent work.
- **Put it in `ARCHITECTURE.md`** — rejected: that charter is frozen (v1.0); consolidation of
  accepted decisions is the role of an ADR (`PROJECT.md` §17).
- **Variant B — CD-owned state machine (Run as an immutable container)** — rejected (§8): it would
  move the state machine into the application layer and make `Run` anemic, contradicting `ADR-0003`,
  `DOMAIN_MODEL.md` §9.1 and the "do not change Run" reference-impl rule (`ARCHITECTURE_FREEZE.md`).

## References
- `PROJECT.md`: §4 п.2 (determinism), §6 (DI), §7 (layers / entry points), §17
- `ARCHITECTURE.md`: §3.3 (entry points), §4 (Content Director), §15 (repository / layering)
- `ADR-0009` (Workflow / mapping), `ADR-0010` (Agent boundary), `ADR-0011` (Agent + Prompt — data),
  `ADR-0012` (Composition Root — dumb wiring), `ADR-0003`…`0008` (execution core), `ARCHITECTURE_FREEZE.md`
- `ROADMAP.md` stage: 7 (first working Agent)
