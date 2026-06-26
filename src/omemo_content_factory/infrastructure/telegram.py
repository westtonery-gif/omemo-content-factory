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
_REVIEW_POLL_TIMEOUT = 50


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


class TelegramReviewGateway:
    """Collects a human approval decision over Telegram (the Approval Gate, PROJECT.md §12).

    DMs the reviewer the candidate content with inline **Approve** / **Reject** buttons and
    long-polls ``getUpdates`` until the reviewer taps one. Requires the reviewer's **numeric**
    chat id: a bot cannot DM a user by ``@username``, and the reviewer must have started the bot
    first. ``getUpdates`` must not be combined with a webhook on the same bot.

    This only *gathers* the human's decision (infrastructure); recording it as a Human Review and
    deciding what to publish stays in the domain/orchestrator.
    """

    def __init__(
        self,
        *,
        token: str,
        reviewer_chat_id: int,
        base_url: str = _TELEGRAM_API,
        client: httpx.Client | None = None,
        poll_timeout: int = _REVIEW_POLL_TIMEOUT,
    ) -> None:
        self._token = token
        self._reviewer_chat_id = reviewer_chat_id
        self._base_url = base_url
        self._poll_timeout = poll_timeout
        self._client = httpx.Client(timeout=poll_timeout + 10.0) if client is None else client

    def request_approval(self, content: str) -> bool:
        """Send the candidate to the reviewer and block until they tap Approve/Reject.

        Returns ``True`` for Approve, ``False`` for Reject. Loops until the reviewer responds.
        """
        offset = self._drain_offset()
        self._send_request(content)
        while True:
            for update in self._get_updates(offset, self._poll_timeout):
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                decision = self._decision_from(update)
                if decision is not None:
                    return decision

    def _url(self, method: str) -> str:
        return f"{self._base_url}/bot{self._token}/{method}"

    def _send_request(self, content: str) -> None:
        text = f"Approve this post for publishing?\n\n{content}"
        markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": "approve"},
                    {"text": "❌ Reject", "callback_data": "reject"},
                ]
            ]
        }
        response = self._client.post(
            self._url("sendMessage"),
            json={"chat_id": self._reviewer_chat_id, "text": text, "reply_markup": markup},
        )
        response.raise_for_status()

    def _drain_offset(self) -> int:
        """Skip updates from before this request (a quick, non-blocking poll)."""
        offset = 0
        for update in self._get_updates(0, 0):
            if isinstance(update, dict):
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = max(offset, update_id + 1)
        return offset

    def _get_updates(self, offset: int, timeout: int) -> list[object]:
        response = self._client.post(
            self._url("getUpdates"),
            json={"offset": offset, "timeout": timeout, "allowed_updates": ["callback_query"]},
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, list):
                return result
        return []

    def _decision_from(self, update: dict[str, object]) -> bool | None:
        """Extract the reviewer's Approve/Reject from a callback update, or ``None``."""
        callback = update.get("callback_query")
        if not isinstance(callback, dict):
            return None
        sender = callback.get("from")
        if not (isinstance(sender, dict) and sender.get("id") == self._reviewer_chat_id):
            return None
        callback_id = callback.get("id")
        if isinstance(callback_id, str):
            self._answer_callback(callback_id)
        return callback.get("data") == "approve"

    def _answer_callback(self, callback_id: str) -> None:
        """Acknowledge the tap so Telegram clears the button's loading state (best effort)."""
        self._client.post(self._url("answerCallbackQuery"), json={"callback_query_id": callback_id})
