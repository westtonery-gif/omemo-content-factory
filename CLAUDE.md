# CLAUDE.md — OMEMO Content Factory

Industrial multi-agent content production system (carousels, AI-video, articles).
Built bottom-up with a strict **spec-before-code** process. The architecture documents are
the source of truth — code must never contradict them; on conflict, the docs win
(PROJECT.md §17).

## Documentation hierarchy (source of truth, in order)
1. `PROJECT.md` — goals & principles (highest authority)
2. `ARCHITECTURE.md` — how the system is structured
3. `ROADMAP.md` — implementation order (stages + milestones)
4. `DOMAIN_MODEL.md` — entities, aggregates, events, invariants
5. Per-aggregate specs: `<NAME>_SPEC.md`, `<NAME>_ACCEPTANCE.md` (e.g. `RUN_SPEC.md`)
6. `docs/adr/` — Architecture Decision Records (technical decisions)
7. Code in `src/`, tests in `tests/`

## Current state
- **Run aggregate is DONE — it is the reference implementation.**
  `src/omemo_content_factory/domain/run.py` + `tests/test_run.py`.
- **Task, Output, Artifact and Human Review are implemented** as child entities of the Run
  aggregate root (ADR-0004/0005/0006/0007), each via the proven ADR → spec/tests process.
  All gates green: ruff, ruff format, mypy --strict, pytest (168 passed, 1 skipped).
- Stage 1 foundation done (config, tooling, CI, pre-commit; ADR-0001/0002). Stage 2
  (domain models & contracts) is largely complete.
- ADR-0003 fixed the Run interface contract; ADR-0004…0007 extend Run additively for its
  children.

## Next task
The Run aggregate and its children (Task, Output, Artifact, Human Review) are in place. The
remaining domain work, deferred explicitly by the ADRs, follows the same ADR → spec/tests
process:
- the shared `DomainError` base (rule-of-three follow-up; ADR-0005 §9).
- the **Schema** entity and Output validation (`Pending → Valid/Invalid`; ADR-0005).
- the **Evaluation / QA** entity (`fail closed`; deferred by ADR-0005/0006/0007).
- Artifact versioning (`SUPERSEDED`) and the **Analytics Record** entity.
See `DOMAIN_MODEL.md` (entities) and §9 (aggregate roots).

## Conventions
- No code before its spec/acceptance/ADR exist. Significant decisions → an ADR.
- **Do NOT change Run's existing behaviour or signatures** (reference impl); extend it only
  *additively* and via an ADR, as ADR-0004…0007 did for its children. **Do NOT extract shared
  base classes prematurely** (rule of three). Extend by *adding* modules, not by modifying the
  core (PROJECT.md §4.11).
- Provider-agnostic: never hardcode a model; selection lives in config.
- An aggregate's public API is small: factory `create`, read-only properties, one guarded
  mutation method, domain events, domain errors. Immutable input via `__slots__` + guarded
  `__setattr__`. Single guarded `transition` + declarative allowed-transitions table.

## Quality gate (all green before commit; a working `.venv` with Python exists)
```
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pytest -q
```
