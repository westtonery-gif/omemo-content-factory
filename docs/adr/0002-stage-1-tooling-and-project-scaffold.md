# ADR-0002: Stage 1 tooling and project scaffold

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Lead Architect
- **Revision:** 1 (2026-06-25)

> **Revision history**
> - **Rev. 0** — Initial Stage 1 tooling and scaffold decisions.
> - **Rev. 1** — Refines and makes explicit (without changing any already-accepted
>   decision or the Stage 1 scope): `pyproject.toml` as the single configuration
>   source, a stricter CI policy, README purpose, a Semantic Versioning policy,
>   pre-commit hooks as a first-level quality check, and a softened dependency
>   principle ("minimise" rather than "zero"). See the new policy sections below.

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
  `ruff check`, `mypy`, `pytest` on Python 3.11 and 3.12 (mandatory gate — see
  *Continuous Integration* below).
- **Pre-commit:** local `pre-commit` hooks as the first-level quality check
  (see *Pre-commit hooks* below).
- **Dependencies:** a minimise-don't-forbid runtime-dependency policy
  (see *Dependency policy* below).
- **Configuration:** read from the process environment via a small
  standard-library-only loader (`config.py`); no third-party settings library is
  pulled in at Stage 1, so the foundation has no third-party runtime dependency
  (see *Dependency policy* below). Secrets never live in the repository
  (`.env` is git-ignored; `.env.example` documents the pattern).

## Project Configuration

`pyproject.toml` is the **single, primary configuration file** of the project.

- Every tool that supports configuration via `pyproject.toml` MUST be configured
  there (today: Ruff, mypy, pytest, coverage, Hatchling).
- Standalone tool config files (`ruff.toml`, `mypy.ini`, `pytest.ini`,
  `setup.cfg`, etc.) MUST be avoided when `pyproject.toml` support exists.
- Exceptions are allowed only on genuine technical necessity (e.g. a tool with no
  `pyproject.toml` support) and MUST be recorded in their own ADR.

This keeps configuration discoverable in one place and prevents drift between
scattered files.

## Continuous Integration (CI)

CI is a **mandatory part of the engineering process**, not an optional aid.

- Passing CI is **required** for every change.
- Merging a Pull Request with **red CI is forbidden**.
- The **`main` branch is protected**; direct pushes are not allowed.
- All changes reach `main` **only through a reviewed Pull Request**.

CI is the authoritative quality gate (`PROJECT.md` sections 6 and 11); local
checks and pre-commit do not replace it.

## Versioning

The project uses **Semantic Versioning** — `MAJOR.MINOR.PATCH`.

- While the system is pre-stable, it stays on the **`0.x.y`** line (the public
  surface may change between minors). Stage 1 ships `0.1.0`.
- Every change to the architecture is accompanied by an **ADR**
  (`PROJECT.md` sections 11 and 17).
- The version remains single-sourced in `__about__.py` (see Decision above).

## README purpose

`README.md` is written **first and foremost for the project's developers**, not
as a marketing page. It MUST contain:

- a description of the project; a **Quick Start**; requirements; installation;
  how to run the tests; the documentation structure; and links to
  `PROJECT.md`, `ARCHITECTURE.md`, `ROADMAP.md` and the ADRs.

It MUST NOT drift into product marketing.

## Dependency policy

We **minimise** runtime dependencies rather than forbid them. The governing
principle replaces the earlier "zero dependencies" framing:

> **Runtime dependencies are introduced only when they solve a concrete
> architectural problem.** Minimising dependencies matters more than having none.

- Stage 1 happens to need no third-party runtime dependency — a consequence of
  its scope, not a permanent rule.
- Future libraries (e.g. **Pydantic**, the **Anthropic SDK**, **OpenAI SDK**,
  **Notion SDK**, **Google SDK**) can be added **without contradicting this ADR**,
  each justified and recorded in its own ADR at the relevant stage.

## Pre-commit hooks

We adopt **`pre-commit`** as the first level of quality control, to stop obvious
errors from entering the repository before a commit is created.

- Stage 1 hooks are sufficient with: **Ruff Format**, **Ruff Check**, **mypy**.
- Pre-commit is the **first** check, run on the developer's machine; it **does
  not replace CI**, which remains the authoritative gate (see *Continuous
  Integration* above).

## Consequences

### Positive

- Runtime dependencies are minimised (none required at Stage 1), keeping the
  maintenance surface small while leaving a clean path to add libraries via ADRs.
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

- `PROJECT.md` sections: 5 (provider-agnostic), 6 (code standards), 7 (structure),
  11 (version control / ADR / semantic versioning), 17 (documentation hierarchy)
- `ARCHITECTURE.md` section: 15 (repository architecture)
- `ROADMAP.md` stage: 1 (foundation, Milestone M0)
