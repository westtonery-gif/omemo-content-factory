"""Publishing port — the application's seam for delivering an approved Artifact outward.

A small, explicit, injected dependency (PROJECT.md §6), mirroring ``TaskExecutor``: it decouples
the orchestrator from *how/where* content is delivered. The domain knows nothing of it; a concrete
publisher (e.g. Telegram) lives in the infrastructure layer. Publication is an **external action**
and is only ever invoked **after** an explicit human ``Approve`` (PROJECT.md §1, §12).
"""

from __future__ import annotations

from typing import Protocol


class PublishError(Exception):
    """A provider-agnostic failure while delivering content to an external destination."""


class Publisher(Protocol):
    """Delivers a piece of approved content and returns an opaque external reference."""

    def publish(self, content: str) -> str: ...
