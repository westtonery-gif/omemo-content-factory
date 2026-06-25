"""Infrastructure configuration loaded from the environment.

Scope (ROADMAP Stage 1): this module loads *infrastructure-level* settings only
— the application environment and logging verbosity. It deliberately contains
**no** domain models (Run, Artifact, Schema, …) and **no** provider/adapter
configuration; those belong to later ROADMAP stages.

Configuration is read from the process environment so that secrets never live in
the repository (PROJECT.md, sections 5 and 6). ``load_config`` accepts an
explicit mapping to stay testable without mutating global state (dependency
injection — PROJECT.md, section 6).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

APP_ENV_VAR = "OMEMO_APP_ENV"
LOG_LEVEL_VAR = "OMEMO_LOG_LEVEL"


class AppEnv(str, Enum):
    """Application runtime environment."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


_VALID_LOG_LEVELS = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)

DEFAULT_APP_ENV = AppEnv.DEVELOPMENT
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable snapshot of infrastructure configuration."""

    app_env: AppEnv
    log_level: str

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running in the production environment."""
        return self.app_env is AppEnv.PRODUCTION


def _parse_app_env(raw: str | None) -> AppEnv:
    if not raw:
        return DEFAULT_APP_ENV
    normalized = raw.strip().lower()
    try:
        return AppEnv(normalized)
    except ValueError:
        valid = ", ".join(member.value for member in AppEnv)
        raise ValueError(
            f"Invalid {APP_ENV_VAR}={raw!r}; expected one of: {valid}."
        ) from None


def _parse_log_level(raw: str | None) -> str:
    if not raw:
        return DEFAULT_LOG_LEVEL
    normalized = raw.strip().upper()
    if normalized not in _VALID_LOG_LEVELS:
        valid = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ValueError(
            f"Invalid {LOG_LEVEL_VAR}={raw!r}; expected one of: {valid}."
        )
    return normalized


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Load configuration from ``environ`` (defaults to ``os.environ``)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    return Config(
        app_env=_parse_app_env(env.get(APP_ENV_VAR)),
        log_level=_parse_log_level(env.get(LOG_LEVEL_VAR)),
    )
