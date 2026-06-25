# Contributing

This project follows the engineering discipline defined in `PROJECT.md`
(sections 6 and 11) and `ROADMAP.md`. Please read those before contributing.

## Source of truth

`PROJECT.md` → `ARCHITECTURE.md` → `ROADMAP.md` → `ADR` → code. Code must not
contradict any level of the documentation. On conflict, the documentation wins
(PROJECT.md, section 17). Architectural changes require an
[ADR](docs/adr/README.md).

## Per-change workflow

Every change follows **Build → Test → Commit → Review**:

1. **Build** — implement the smallest coherent change for the current ROADMAP
   stage. Do not implement work that belongs to a later stage.
2. **Test** — add/keep tests; run the full local quality gate (below) green.
3. **Commit** — small, atomic [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` …).
4. **Review** — open a Pull Request. CI must be green before merge.

## Branching

- Trunk-based: `main` is always green and protected; no direct pushes.
- Work on short-lived feature branches and merge via reviewed PRs.

## Local quality gate

Run all of these before opening a PR (CI runs the same checks):

```bash
ruff format --check .   # formatting
ruff check .            # linting
mypy                    # static typing (strict)
pytest                  # tests
```

`ruff format .` (without `--check`) applies formatting locally.

## Scope discipline

Do not add agents, skills, tools, adapters, workflows, domain models,
integrations, APIs, databases or LLM code ahead of their ROADMAP stage. If a
change feels like "for the future", it belongs to a later stage.
