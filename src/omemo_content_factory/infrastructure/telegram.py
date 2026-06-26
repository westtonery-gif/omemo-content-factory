"""Telegram publishing infrastructure — delivers an approved Artifact to a Telegram chat.

Infrastructure layer (ARCHITECTURE.md §9): implements the application's ``Publisher`` port via the
Telegram Bot API. The domain and orchestrator know only the port; this is the single place that
touches the network. The bot token and chat id come from the environment (PROJECT.md §5, §6), not
the repository. It is invoked only **after** a human ``Approve`` (the orchestrator guarantees this).
"""

from __future__ import annotations

import httpx

from omemo_content_factory.application.publishing import PublishError

_TELEGRAM_API = "https://api.telegram.org"
_DEFAULT_TIMEOUT = 30.0


class TelegramPublisher:
    """A ``Publisher`` backed by the Telegram Bot API ``sendMessage`` method.

    The ``httpx`` client may be injected (otherwise one is created); any HTTP error is wrapped as
    the provider-agnostic ``PublishError`` so the orchestrator stays infrastructure-unaware.
    """

    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        base_url: str = _TELEGRAM_API,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._base_url = base_url
        self._client = httpx.Client(timeout=_DEFAULT_TIMEOUT) if client is None else client

    def publish(self, content: str) -> str:
        """Send ``content`` to the chat; return an opaque ``telegram:<chat>:<id>`` reference."""
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        try:
            response = self._client.post(url, json={"chat_id": self._chat_id, "text": content})
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise PublishError(str(exc)) from exc
        message_id = ""
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict):
                message_id = str(result.get("message_id", ""))
        return f"telegram:{self._chat_id}:{message_id}"
