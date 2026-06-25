# ADR-0002: Stage 1 tooling and project scaffold

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Lead Architect

## Context

`ROADMAP.md` Stage 1 (Milestone M0) requires a reproducible engineering
foundation: project setup, configuration, formatting, linting, static typing,
test environment and CI. We must pick concrete tools. Per `PROJECT.md` (when
several options exist, choose the simplest, most maintainable one) and
`ARCHITECTURE.md` section 15 (layered, dependencies pointing inward, prompts /
config / code separated, adapters as the only edge to the outside world).

This ADR records the tooling and scaffold decisions for Stage 1 only. It does
**not** introduce any domain logic, models, agents, skills, tools, adapters,
workflows or integrations — those are later stages.

## Decision

We will adopt the following for Stage 1:

- **Language / runtime:** Python, `requires-python >= 3.11` (modern, supported;
  enables `getLevelNamesMapping`, `dataclass(slots=True)`).
- **Repository layout:** `src/` layout with the import package
  `omemo_content_factory`; tests in `tests/`; documentation in `docs/`
  (ADRs in `docs/adr/`). This mirrors the layered principles of
  `ARCHITECTURE.md` section 15 without yet creating the inner layers.
- **Build backend / packaging:** Hatchling, with the version sourced
  dynamically from `__about__.py` (single source of truth).
- **Formatter + linter:** Ruff (one tool for both), line length 100.
- **Static typing:** mypy in `strict` mode; the package ships `py.typed`.
- **Tests:** pytest.
- **CI:** GitHub Actions running, in order, `ruff format --check`,
  `ruff check`, `mypy`, `pytest` on Python 3.11 and 3.12.
- **Configuration:** read from the process environment via a small
  standard-library-only loader (`config.py`); no third-party settings library is
  pulled in at Stage 1, keeping the foundation dependency-free. Secrets never
  live in the repository (`.env` is git-ignored; `.env.example` documents the
  pattern).

## Consequences

### Positive

- Zero runtime dependencies at Stage 1; minimal surface to maintain.
- A single, fast quality gate (`Build → Test → Commit → Review`) from day one.
- `src/` layout prevents accidental imports of an uninstalled package and keeps
  future layering clean.
- Provider/adapter choices are deferred to their stages, honouring
  provider-agnosticism (`PROJECT.md` section 5).

### Negative / Trade-offs

- A standard-library config loader is less feature-rich than a settings library;
  acceptable now and revisitable via a future ADR when adapters arrive.
- `src/` layout requires an editable install (`pip install -e .`) to run tests.

## Alternatives considered

- **Flat (non-`src`) layout** — simpler at first but error-prone for imports and
  packaging; rejected for an industrial, multi-year project.
- **Separate Black + Flake8/isort** instead of Ruff — more tools and config to
  maintain; Ruff covers both faster.
- **`pydantic-settings` for configuration** — convenient, but pulls a dependency
  associated with Stage 2 data models; deferred to keep Stage 1 minimal.
- **A heavier task runner (tox/nox/Make)** — unnecessary at Stage 1; raw
  commands plus CI are simpler and cross-platform (Windows-friendly).

## References

- `PROJECT.md` sections: 5 (provider-agnostic), 6 (code standards), 7 (structure)
- `ARCHITECTURE.md` section: 15 (repository architecture)
- `ROADMAP.md` stage: 1 (foundation, Milestone M0)
