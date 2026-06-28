"""Prompt domain model — an immutable execution-input artifact (a passive descriptor).

A versioned, immutable artifact (`DOMAIN_MODEL.md` §2.7; `ADR-0011`): System text + a User
template, a version, and an opaque ``schema_ref`` that **references** the authoritative Schema
(`ADR-0008`) the result conforms to. It is **passive data** — it carries text and a reference and
contains no
execution, orchestration or decision logic. The Schema (not the Prompt) is the contract authority;
the Prompt only points at it. Use/resolution happens via the composition root and execution
(`ADR-0012`, `ADR-0013`), never inside the Prompt. Only stdlib is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

PromptId: TypeAlias = str
"""Opaque, stable identifier of the logical Prompt (shared across its versions; `ADR-0011`)."""


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """A version of a Prompt — a Value Object compared by value (`DOMAIN_MODEL.md` §11)."""

    value: int


@dataclass(frozen=True, slots=True)
class Prompt:
    """The immutable Prompt artifact (`ADR-0011`, AGENT_SPEC §4).

    ``schema_ref`` is an opaque reference to the authoritative Schema (`ADR-0008`); the Prompt does
    not define or validate the contract.
    """

    prompt_id: PromptId
    version: PromptVersion
    system: str
    user_template: str
    schema_ref: str
