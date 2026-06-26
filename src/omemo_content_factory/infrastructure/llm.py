"""LLM infrastructure — a real model behind the application's ``TaskExecutor`` port.

Layering (ARCHITECTURE.md §9, §15): this is infrastructure. It depends on the application layer
(``TaskExecutor`` / ``ExecutionResult``) and on an external SDK; the domain depends on **none**
of it. Provider independence (PROJECT.md §5) is kept by routing all model access through the
small :class:`LLMClient` port — the Anthropic implementation is the default, swappable one.

Nothing here makes any decision about *what* content to produce: the executor turns a Task's
input into model output and reports the outcome. The prompt that defines a role is supplied from
outside (configuration / the entry point), not embedded in the orchestrator.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import anthropic
from anthropic.types import ContentBlock, MessageParam, TextBlock

from omemo_content_factory.application.task_execution import ExecutionResult

_DEFAULT_MAX_TOKENS = 2048


class LLMError(Exception):
    """A provider-agnostic failure while calling a model (network, rate limit, API error)."""


class LLMClient(Protocol):
    """The provider-agnostic seam for one model completion (PROJECT.md §5, §7).

    A single explicit dependency, so executors are testable with a trivial fake and the provider
    is swappable without touching the application or domain.
    """

    def complete(self, *, system: str, user: str) -> str: ...


def _extract_text(blocks: Iterable[ContentBlock]) -> str:
    """Concatenate the text of the response's text blocks (ignoring any non-text blocks)."""
    return "".join(block.text for block in blocks if isinstance(block, TextBlock))


class AnthropicLLMClient:
    """An :class:`LLMClient` backed by the Anthropic SDK (PROJECT.md §5: default provider).

    The model is supplied by configuration. The SDK client may be injected (otherwise it is
    constructed from the environment, which is where the API key lives — PROJECT.md §6).
    Any SDK error is wrapped as :class:`LLMError` so callers stay provider-agnostic.
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

    def complete(self, *, system: str, user: str) -> str:
        """Run one completion and return the model's text."""
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(str(exc)) from exc
        return _extract_text(message.content)


@dataclass(frozen=True, slots=True)
class LLMTaskExecutor:
    """A :class:`TaskExecutor` that runs a Task's work on a real model (ADR-free; infra only).

    Configured with an :class:`LLMClient`, the role's ``system_prompt`` and the ``schema_ref``
    of the Output it yields. ``execute`` turns the Task input into model output and reports the
    outcome; a model failure becomes a managed ``FAILED`` result (PROJECT.md §10), not an
    exception escaping into the orchestrator. The domain remains unaware of any of this.
    """

    client: LLMClient
    system_prompt: str
    schema_ref: str

    def execute(self, task_input: str) -> ExecutionResult:
        try:
            text = self.client.complete(system=self.system_prompt, user=task_input)
        except LLMError as exc:
            return ExecutionResult(succeeded=False, failure_reason=f"LLM execution failed: {exc}")
        return ExecutionResult(succeeded=True, output=text, schema_ref=self.schema_ref)
