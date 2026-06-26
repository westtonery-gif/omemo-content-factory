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
  `src/omemo_content_factory/domain/run.py` + `tests/test_run.py` (74 passed, 1 skipped).
  All gates green: ruff, ruff format, mypy --strict, pytest.
- Stage 1 foundation done (config, tooling, CI, pre-commit; ADR-0001/0002).
- ADR-0003 fixed the Run interface contract.

## Next task
Implement the **Task** aggregate. Task is a **child Entity of the Run aggregate root —
NOT its own root**; changes go through Run. Proven per-aggregate process:
1. **ADR-0004** — Run↔Task interface contract (`open_task` / `transition_task` / read-only
   access; Task retry policy; activates INV-07).
2. `TASK_SPEC.md` → `TASK_ACCEPTANCE.md`
3. Implementation → behavioural tests.
See `DOMAIN_MODEL.md` §2.10 (Task) and §9 (aggregate roots).

## Conventions
- No code before its spec/acceptance/ADR exist. Significant decisions → an ADR.
- **Do NOT change Run** (reference impl). **Do NOT extract shared base classes prematurely**
  (rule of three). Extend by *adding* modules, not by modifying the core (PROJECT.md §4.11).
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
