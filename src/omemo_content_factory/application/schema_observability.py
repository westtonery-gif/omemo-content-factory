"""Observability-only layer over the Schema wiring — a passive trace of validation decisions.

Records the **fact** of each ``Schema.validate`` outcome (VALID / INVALID), so that even an
INVALID result — which is gated out and never becomes an Output — leaves an observable trail. It
is **log-only**: it must not affect system behaviour, so dispatch is best-effort (any observer
error is swallowed) and the hook is opt-in (no observer ⇒ nothing happens).

It changes no domain entity and no execution flow: it reads a ``Schema`` snapshot and a
``SchemaValidation`` verdict that already exist, and emits a structured event. No raw payload
values are stored — only a hash signature — keeping secrets/PII out of the trace (PROJECT.md §6).
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from omemo_content_factory.domain.schema import Schema, SchemaValidation


@dataclass(frozen=True, slots=True)
class ValidationEvent:
    """One structured record of a Schema validation decision (log-only)."""

    schema_id: str
    schema_version: int
    is_valid: bool
    missing_fields: tuple[str, ...]
    timestamp: str
    payload_signature: str


class ValidationObserver(Protocol):
    """The hook a sink implements to receive validation events."""

    def on_validation_result(self, event: ValidationEvent) -> None: ...


class InMemoryValidationLog:
    """A minimal in-memory sink: appends events, exposes them read-only."""

    def __init__(self) -> None:
        self._events: list[ValidationEvent] = []

    def on_validation_result(self, event: ValidationEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> tuple[ValidationEvent, ...]:
        return tuple(self._events)


class FileValidationLog:
    """A minimal file sink: appends one JSON object per line (JSON Lines)."""

    def __init__(self, path: str) -> None:
        self._path = path

    def on_validation_result(self, event: ValidationEvent) -> None:
        line = json.dumps(dataclasses.asdict(event), ensure_ascii=False)
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _now() -> str:
    """Current UTC time as an ISO-8601 string (stdlib only)."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def _signature(payload_fields: Mapping[str, str]) -> str:
    """A stable SHA-256 signature of the payload fields — no raw values are kept."""
    canonical = json.dumps(dict(sorted(payload_fields.items())), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_event(
    schema: Schema, verdict: SchemaValidation, payload_fields: Mapping[str, str]
) -> ValidationEvent:
    """Assemble a :class:`ValidationEvent` from an existing Schema snapshot and a verdict."""
    view = schema.view
    return ValidationEvent(
        schema_id=view.schema_id,
        schema_version=view.version.value,
        is_valid=verdict.is_valid,
        missing_fields=verdict.missing_fields,
        timestamp=_now(),
        payload_signature=_signature(payload_fields),
    )


def record_validation(
    observer: ValidationObserver | None,
    schema: Schema,
    verdict: SchemaValidation,
    payload_fields: Mapping[str, str],
) -> None:
    """Best-effort dispatch of a validation event — never affects the caller's behaviour.

    No observer ⇒ no-op. Any error from the observer is swallowed: observation is log-only and
    MUST NOT change system behaviour.
    """
    if observer is None:
        return
    # Best-effort: observation is log-only and MUST NOT affect behaviour.
    with contextlib.suppress(Exception):
        observer.on_validation_result(build_event(schema, verdict, payload_fields))
