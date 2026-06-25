"""Logging configuration helper (infrastructure, ROADMAP Stage 1).

A thin wrapper over the standard library so the rest of the system has a single,
testable place to configure logging. No domain logic lives here.
"""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Configure root logging at the given standard level name.

    ``level`` is a standard logging level name (e.g. ``"INFO"``). An unknown
    name raises :class:`ValueError`. The call is idempotent: it reconfigures the
    root logger on every invocation (``force=True``).
    """
    mapping = logging.getLevelNamesMapping()
    if level not in mapping:
        raise ValueError(f"Unknown logging level: {level!r}")
    logging.basicConfig(level=mapping[level], format=_LOG_FORMAT, force=True)
