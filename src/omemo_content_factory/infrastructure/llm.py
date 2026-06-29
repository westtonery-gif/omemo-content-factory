"""LLM infrastructure — a real model behind the application's ``TaskExecutor`` port.

Layering (ARCHITECTURE.md §9, §15): this is infrastructure. It depends on the application layer
(``TaskExecutor`` / ``ExecutionResult``) and on an external SDK; the domain depends on **none**
of it. Provider independence (PROJECT.md §5) is kept by routing all model access through the
small :class:`LLMClient` port — the Anthropic implementation is the default, swappable one.

Structured output (`ADR-0014`): the port is **uniformly structured**. Given a *generation shape*
(the field names projected from the authoritative Schema by the Composition Root) it returns a
``name -> value`` mapping. The provider mechanism by which structure is elicited (here, forced
tool use) is hidden behind the port; ``fields`` is opaque to it (Variant B, `ADR-0014` §2) — it
knows nothing of Schema, requiredness, or any rule. Nothing here decides *what* content to
produce or whether it is valid; the executor turns a Task's input into model output and reports
the outcome, and ``Schema.validate`` (elsewhere) is the sole judge of structural correctness.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import anthropic
from anthropic.types import ContentBlock, MessageParam, ToolParam, ToolUseBlock

from omemo_content_factory.application.task_execution import ExecutionResult

_DEFAULT_MAX_TOKENS = 2048
_STRUCTURED_TOOL_NAME = "emit_fields"
_INPUT_PLACEHOLDER = "{input}"


class LLMError(Exception):
    """A provider-agnostic failure while calling a model (network, rate limit, API error)."""


class LLMClient(Protocol):
    """The provider-agnostic seam for one **structured** completion (PROJECT.md §5, §7; `ADR-0014`).

    Variant B (`ADR-0014` §2): ``fields`` is an **opaque** list of names; the client promises a
    ``name -> value`` mapping and ascribes no meaning to the names — it knows nothing of Schema,
    requiredness, or any rule, and guarantees neither completeness nor exclusivity of keys. A single
    explicit dependency, so executors are testable with a trivial fake and the provider is swappable
    without touching the application or domain.
    """

    def complete(self, *, system: str, user: str, fields: Sequence[str]) -> Mapping[str, str]: ...


def _extract_fields(blocks: Iterable[ContentBlock]) -> dict[str, str]:
    """Read the forced tool call's input as a ``name -> value`` mapping (first tool_use block).

    The client does not judge the result: a missing or empty mapping is returned as-is (Variant B);
    downstream ``Schema.validate`` decides VALID/INVALID.
    """
    for block in blocks:
        if isinstance(block, ToolUseBlock):
            raw = block.input
            if isinstance(raw, dict):
                return {str(name): str(value) for name, value in raw.items()}
    return {}


class AnthropicLLMClient:
    """An :class:`LLMClient` backed by the Anthropic SDK (PROJECT.md §5: default provider).

    Structured output is obtained via **forced tool use**: a single tool whose input schema is the
    requested ``fields``, with ``tool_choice`` pinned to it. The mechanism is hidden here; callers
    see only ``name -> value`` (`ADR-0014` §2, Variant B). The model is supplied by configuration
    (never hardcoded, PROJECT.md §5). Any SDK error is wrapped as :class:`LLMError`.
    """

    def __init__(
        self,
        *,
        model: str,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic() if client is None else client

    def complete(self, *, system: str, user: str, fields: Sequence[str]) -> Mapping[str, str]:
        """Run one structured completion, returning a value for each requested field."""
        tool: ToolParam = {
            "name": _STRUCTURED_TOOL_NAME,
            "description": "Return a value for each requested field.",
            "input_schema": {
                "type": "object",
                "properties": {name: {"type": "string"} for name in fields},
                "required": list(fields),
            },
        }
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "tool", "name": _STRUCTURED_TOOL_NAME},
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(str(exc)) from exc
        return _extract_fields(message.content)


def _render(user_template: str, task_input: str) -> str:
    """Deterministic template rendering (`ADR-0014` §7): place the Task input into the template.

    A pure, content-opaque, total substitution of the single ``{input}`` placeholder (an
    executor/Prompt convention; the syntax is **not** frozen by the ADR). The only dynamic input is
    ``task_input`` — no other data source, lookup, or branching — which keeps rendering out of
    orchestration. A template without the placeholder is valid (a constant prompt).
    """
    return user_template.replace(_INPUT_PLACEHOLDER, task_input)


def _serialize(fields: Mapping[str, str]) -> str:
    """Serialize ``payload_fields -> payload`` (`ADR-0014` §6, §7): deterministic and faithful.

    Keys are emitted in sorted order so the result is deterministic regardless of the mapping's
    iteration order (the ordering strategy is an implementation detail). The mapping is strictly
    one-directional: ``payload`` is a derived compatibility representation and no logic ever
    reconstructs ``payload_fields`` from it.
    """
    return json.dumps({name: fields[name] for name in sorted(fields)}, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class LLMTaskExecutor:
    """A :class:`TaskExecutor` that runs a Task's work on a real model (infra only; `ADR-0014`).

    Configured with an :class:`LLMClient`, the role's ``system_prompt`` and ``user_template``, the
    ``schema_ref`` of the Output it yields, and ``output_fields`` — the **generation shape**. Per
    `ADR-0014` §3 (Locus 2) the shape is a **mandatory construction invariant**: a structured
    executor cannot exist without a non-empty ``output_fields`` (a self-validating construction
    invariant — not policy, not a runtime guard). ``execute`` renders the user message, calls the
    structured port with the shape, and assembles the ``ExecutionResult``: it is
    **structure-transparent** (`ADR-0014` §8 I2) — it forwards ``payload_fields`` verbatim and
    deterministically serializes them into ``payload``, never inspecting, repairing, reordering, or
    pre-validating; ``Schema.validate`` is the sole judge. A model failure becomes a managed
    ``FAILED`` result (PROJECT.md §10), not an exception escaping into the orchestrator.
    """

    client: LLMClient
    system_prompt: str
    user_template: str
    schema_ref: str
    output_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.output_fields:
            raise ValueError(
                "LLMTaskExecutor requires a non-empty output_fields (generation shape)"
            )

    def execute(self, task_input: str) -> ExecutionResult:
        user = _render(self.user_template, task_input)
        try:
            fields = self.client.complete(
                system=self.system_prompt, user=user, fields=self.output_fields
            )
        except LLMError as exc:
            return ExecutionResult(succeeded=False, failure_reason=f"LLM execution failed: {exc}")
        return ExecutionResult(
            succeeded=True,
            output=_serialize(fields),
            schema_ref=self.schema_ref,
            payload_fields=fields,
        )
