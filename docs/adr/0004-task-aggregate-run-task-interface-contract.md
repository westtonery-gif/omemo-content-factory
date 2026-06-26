# ADR-0004: Task aggregate — Run↔Task interface contract

- **Status:** Proposed
- **Date:** 2026-06-25
- **Deciders:** Lead Architect / Domain Architect

## Context

`Task` is a **child Entity of the `Run` aggregate root** (`DOMAIN_MODEL.md` §2.10, §9.1),
not its own root: a Task does not exist outside a Run and changes to it happen **only through
Run**. `ADR-0003` §9 deferred the root↔child interface; this ADR defines it, using Task as the
first child (the template for Artifact, Evaluation, Human Review, Analytics Record).

This is **not a new architecture** — the model "Task is a child of Run" is already accepted.
It is an **interface-contract** decision (analogous to ADR-0003 for Run) that additively
extends Run's public surface and activates previously-deferred invariants. Scope: Task only.

**Key consequence to accept:** managing a child through the root means **Run gains new public
methods**. This is an *additive* extension (Open/Closed, `PROJECT.md` §4.11): Run's existing
behaviour, signatures and tests are unchanged; only new operations are added. There is no
architecturally-correct alternative that leaves Run literally untouched without making Task a
root (forbidden).

## Decision

### 1. Placement
Task-specific symbols live in `omemo_content_factory.domain.task`: `TaskStatus`,
`TaskRetryPolicy`, Task domain events, Task domain errors, a read-only `TaskView`, and a
`TaskId`. Task is **constructed only via Run** — no public standalone factory.

### 2. States — `TaskStatus`
`PENDING, RUNNING, SUCCEEDED, FAILED, SKIPPED` (`DOMAIN_MODEL.md` §2.10).
Terminal: `SUCCEEDED, FAILED, SKIPPED`. **`Retrying` is modelled as an attempt counter inside
`RUNNING`, not a separate state** (mirrors Run's `rework_count`, ADR-0003 §6).

### 3. Identity & immutable input
`TaskId` is stable and immutable. Immutable input (set once, write-once): owning `run_id`,
`workflow_step_ref`, `agent_ref`, `task_input`. References are opaque `str` (ADR-0003 §3).

### 4. Run's additive public API (the contract)
- `open_task(workflow_step_ref, agent_ref, task_input, by) -> TaskId` — creates a Task in
  `PENDING` inside the Run, emits `TaskCreated`, returns its id. Authorised actor only.
- `transition_task(task_id, to, by, reason=None) -> None` — single guarded mutation: actor
  authorisation + Task allowed-transitions table + retry-policy bound.
- read-only access: `tasks` (sequence of `TaskView` snapshots) and/or `task(task_id) ->
  TaskView`. **No mutable Task object is exposed** (would bypass the root).

### 5. Allowed Task transitions (from `DOMAIN_MODEL.md` §2.10)
`PENDING → {RUNNING, SKIPPED}`; `RUNNING → {SUCCEEDED, FAILED, RUNNING}` where
`RUNNING → RUNNING` is a bounded **retry** (attempt counter +1). Terminal states have no
outgoing edges.

### 6. Retry policy — `TaskRetryPolicy`
Value Object with `max_attempts`. A retry that would exceed it is rejected with a domain error
(mirror `ReworkPolicy` / `ReworkLimitExceededError`). `attempt_count` is read-only via
`TaskView`. Policy supplied at `open_task` (or defaulted).

### 7. Events (recorded in the Run's existing `events` log)
`TaskCreated` (open), `TaskStarted` (first `PENDING → RUNNING`), `TaskCompleted`
(`→ SUCCEEDED`), `TaskFailed` (`→ FAILED`). A **retry re-entry to `RUNNING` emits no
`TaskStarted`** (mirrors Run's no-`RunStarted`-on-rework, ADR-0003 §7). `SKIPPED` emits no
dedicated event at this stage.

### 8. Errors
Task-specific hierarchy co-located in `domain.task` (e.g. base `TaskDomainError` +
`InvalidTaskTransitionError`, `UnauthorizedActorError` reuse-or-local,
`TaskRetryLimitExceededError`, `ImmutableTaskAttributeError`). **No shared `DomainError` base is
extracted yet** — Run + Task is two aggregates; extraction waits for the third (rule of three).

### 9. Invariants activated / extended
- **INV-07 (aggregate integrity)** — now **active**: every Task belongs to exactly one Run,
  is created/changed only through it; `Task.run_id` equals the owning Run's id.
- **INV-02/03/04/05/08/09** — extended to Task (immutable input; only Content Director;
  only allowed transitions; each Task terminates; bounded attempts; Task events traced in the
  Run log). New cross-entity rule: a Run should not complete with non-terminal Tasks.

### 10. Time
No timestamps in the asserted surface (ADR-0003 §10).

## Acceptance coverage impact
Implementing Task makes previously-deferred scenarios testable: full Task behavioural matrix;
`AGG-01` (Task cannot exist outside a Run) and the Task part of `INV-07`. Cross-aggregate
scenarios needing Output/Artifact/etc. stay deferred to their stages.

## Consequences
**Positive:** establishes the reusable root↔child contract once (template for all Run
children); Run's reference behaviour and tests stay green; provider-agnostic, immutable,
traceable, consistent with Run.
**Negative / Trade-offs:** Run's public API grows (additively); the root↔child pattern is now a
commitment to honour for the other four children.

## Alternatives considered
- **Task as its own Aggregate Root** — rejected: contradicts `DOMAIN_MODEL.md` §9.1 (Run owns
  Task) and the accepted model.
- **Leave Run literally untouched** — impossible without making Task a root or letting callers
  bypass the aggregate boundary; rejected.
- **Per-state methods on Run** (`start_task`, `complete_task`, …) — rejected for surface
  bloat; one guarded `transition_task` covers all (proven on `Run.transition`).
- **Extract a shared aggregate base / `DomainError` now** — rejected: rule of three.

## References
- `DOMAIN_MODEL.md`: §2.10 (Task), §6 (Task invariants), §9.1 (Run owns Task), §10 (events)
- `PROJECT.md`: §4.11 (additive extension), §9, §11, §17, §18
- `ADR-0003` (Run interface contract — the template this mirrors)
- `ROADMAP.md` stage: 2 (data models and contracts)
