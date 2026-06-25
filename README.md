# OMEMO Content Factory

Industrial multi-agent content production system for **OMEMO Health** — a
managed, reproducible, human-in-the-loop pipeline for producing content.

> **Status:** ROADMAP **Stage 1 — engineering foundation (Milestone M0)**.
> The repository currently contains the project scaffold, configuration and
> logging infrastructure, quality tooling and CI. No agents, skills, tools,
> adapters, workflows or domain logic exist yet — those arrive in later stages.

## Documentation (source of truth)

The architecture is governed by three charters, in strict order of authority:

| Document | Answers |
|----------|---------|
| [PROJECT.md](PROJECT.md) | **What** we are building and by which principles |
| [ARCHITECTURE.md](ARCHITECTURE.md) | **How** the system is structured |
| [ROADMAP.md](ROADMAP.md) | In **which order** we implement it |
| [docs/adr/](docs/adr/README.md) | **Why** each architectural decision was made |

Code must never contradict the documentation; on conflict, the documentation
wins (PROJECT.md, section 17).

## Requirements

- Python **3.11+**
- git

## Quickstart

Create a virtual environment and install the project with its dev tooling:

```bash
# bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

```powershell
# PowerShell (Windows)
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Configure the environment (optional — sensible defaults are used otherwise):

```bash
cp .env.example .env        # bash
Copy-Item .env.example .env # PowerShell
```

> At Stage 1 variables are read directly from the **process environment**
> (`OMEMO_APP_ENV`, `OMEMO_LOG_LEVEL`). A `.env` auto-loader is intentionally not
> part of Stage 1. Export the variables in your shell, or set them inline.

## Running the checks

The local quality gate mirrors CI exactly:

```bash
ruff format --check .   # formatting
ruff check .            # linting
mypy                    # static typing (strict)
pytest                  # tests
```

Use `ruff format .` to apply formatting, and `pytest --cov` for coverage.

## Running the smoke entrypoint

A Stage 1 entrypoint that proves the package installs, imports and reads
configuration (no business logic, no external calls):

```bash
python -m omemo_content_factory
```

It logs the version, the active environment and the log level.

## Project layout

```
omemo-content-factory/
├── PROJECT.md                  # Charter: goals & principles (source of truth)
├── ARCHITECTURE.md             # Charter: system design
├── ROADMAP.md                  # Charter: implementation order
├── README.md                   # This file
├── CONTRIBUTING.md             # Workflow, branching, quality gate
├── LICENSE                     # MIT
├── pyproject.toml              # Project metadata + tool config (ruff/mypy/pytest)
├── .env.example                # Documented environment variables
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml              # CI: format → lint → types → tests
├── docs/
│   └── adr/                    # Architecture Decision Records
├── src/
│   └── omemo_content_factory/  # The import package (src layout)
│       ├── __about__.py        # Version (single source of truth)
│       ├── __init__.py
│       ├── __main__.py         # `python -m omemo_content_factory`
│       ├── config.py           # Env-based infrastructure configuration
│       ├── log.py              # Logging configuration helper
│       └── py.typed            # PEP 561 typed marker
└── tests/                      # pytest suite
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every change follows
**Build → Test → Commit → Review**, and architectural changes require an
[ADR](docs/adr/README.md).

## License

[MIT](LICENSE) © 2026 OMEMO Health
