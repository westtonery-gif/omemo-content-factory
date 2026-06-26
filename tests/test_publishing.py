"""Tests for the approval-gated publishing flow and the Telegram adapter.

The orchestration (``produce_for_review`` + ``publish_if_approved``) is driven through the Run
aggregate root with a deterministic fake executor and a fake ``Publisher`` — proving that nothing
is published without an explicit human ``Approve`` (PROJECT.md §12). The ``TelegramPublisher``
adapter is tested offline via ``httpx.MockTransport`` (no network, no token). No real API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

from omemo_content_factory.application.content_director import ContentDirector, TaskRequest
from omemo_content_factory.application.publishing import PublishError
from omemo_content_factory.application.task_execution import ExecutionResult
from omemo_content_factory.domain.artifact import ArtifactStatus
from omemo_content_factory.domain.human_review import ReviewStatus
from omemo_content_factory.domain.run import Actor, Run, RunStatus
from omemo_content_factory.infrastructure.telegram import (
    TelegramPublisher,
    TelegramReviewGateway,
)

CD = Actor.CONTENT_DIRECTOR
REVIEWER = Actor.HUMAN_REVIEWER

TASKS = [
    TaskRequest("research", "researcher@v1", "brief", artifact_kind="notes"),
    TaskRequest("write", "writer@v1", "", artifact_kind="post"),
]


@dataclass(frozen=True, slots=True)
class OutputtingExecutor:
    """Deterministic executor that always succeeds with an output and a schema_ref."""

    def execute(self, task_input: str) -> ExecutionResult:
        return ExecutionResult(succeeded=True, output=f"post[{task_input}]", schema_ref="post@v1")


@dataclass
class RecordingPublisher:
    """Fake Publisher that records what it published and returns a reference."""

    published: list[str] = field(default_factory=list)

    def publish(self, content: str) -> str:
        self.published.append(content)
        return f"ref:{len(self.published)}"


@dataclass(frozen=True, slots=True)
class FailingPublisher:
    """Fake Publisher that always fails."""

    def publish(self, content: str) -> str:
        raise PublishError("network down")


def make_run() -> Run:
    return Run.create(
        run_id="run-pub-0001", content_brief_ref="brief", workflow_version_ref="telegram-post@v1"
    )


# --- Approval-gated orchestration --------------------------------------------------------


def test_produce_for_review_pauses_at_the_gate_with_a_candidate_and_pending_review() -> None:
    """Production stops at WAITING_HUMAN with the final Artifact CANDIDATE and a PENDING review."""
    run = make_run()
    director = ContentDirector(OutputtingExecutor())
    review_id = director.produce_for_review(run, TASKS)
    assert review_id is not None
    assert run.status is RunStatus.WAITING_HUMAN
    assert run.human_review(review_id).status is ReviewStatus.PENDING
    assert run.artifacts[-1].status is ArtifactStatus.CANDIDATE


def test_approve_publishes_the_final_artifact_and_completes_the_run() -> None:
    """An Approve publishes the reviewed Artifact exactly once and completes the Run."""
    run = make_run()
    director = ContentDirector(OutputtingExecutor())
    publisher = RecordingPublisher()
    review_id = director.produce_for_review(run, TASKS)
    assert review_id is not None
    run.submit_review(review_id, ReviewStatus.APPROVED, by=REVIEWER)
    final_content = run.artifacts[-1].content
    reference = director.publish_if_approved(run, review_id, publisher)
    assert publisher.published == [final_content]
    assert reference == "ref:1"
    assert run.status is RunStatus.COMPLETED
    assert run.artifacts[-1].status is ArtifactStatus.PUBLISHED


def test_reject_publishes_nothing_and_fails_the_run() -> None:
    """A Reject leaves nothing published and routes the Run to FAILED (PROJECT.md §12)."""
    run = make_run()
    director = ContentDirector(OutputtingExecutor())
    publisher = RecordingPublisher()
    review_id = director.produce_for_review(run, TASKS)
    assert review_id is not None
    run.submit_review(review_id, ReviewStatus.REJECTED, by=REVIEWER, reason="off-brand")
    reference = director.publish_if_approved(run, review_id, publisher)
    assert reference is None
    assert publisher.published == []
    assert run.status is RunStatus.FAILED
    assert run.artifacts[-1].status is ArtifactStatus.REJECTED


def test_publication_failure_fails_the_run() -> None:
    """If delivery fails after Approve, the Run is routed to FAILED (managed, PROJECT.md §10)."""
    run = make_run()
    director = ContentDirector(OutputtingExecutor())
    review_id = director.produce_for_review(run, TASKS)
    assert review_id is not None
    run.submit_review(review_id, ReviewStatus.APPROVED, by=REVIEWER)
    reference = director.publish_if_approved(run, review_id, FailingPublisher())
    assert reference is None
    assert run.status is RunStatus.FAILED


# --- Telegram adapter (offline) ----------------------------------------------------------


def test_telegram_publisher_posts_to_send_message_and_returns_a_reference() -> None:
    """The adapter POSTs chat_id + text to sendMessage and builds a reference from the response."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/botTOKEN/sendMessage"
        assert json.loads(request.content) == {"chat_id": "chat-1", "text": "hello"}
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 123}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TelegramPublisher(token="TOKEN", chat_id="chat-1", client=client)
    assert publisher.publish("hello") == "telegram:chat-1:123"


def test_telegram_publisher_wraps_http_errors_as_publish_error() -> None:
    """A transport/HTTP error becomes a provider-agnostic PublishError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TelegramPublisher(token="TOKEN", chat_id="chat-1", client=client)
    with pytest.raises(PublishError):
        publisher.publish("hello")


# --- Telegram approval gateway (offline) -------------------------------------------------


def _gateway_client(callback_data: str, reviewer_id: int) -> httpx.Client:
    """A MockTransport client: empty drain, then one callback tap from the reviewer."""
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/sendMessage"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        if path.endswith("/answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        if path.endswith("/getUpdates"):
            state["polls"] += 1
            if state["polls"] == 1:  # the initial drain
                return httpx.Response(200, json={"ok": True, "result": []})
            update = {
                "update_id": 7,
                "callback_query": {"id": "cb", "from": {"id": reviewer_id}, "data": callback_data},
            }
            return httpx.Response(200, json={"ok": True, "result": [update]})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_review_gateway_returns_true_when_the_reviewer_taps_approve() -> None:
    """An Approve tap from the configured reviewer yields True."""
    gateway = TelegramReviewGateway(
        token="T", reviewer_chat_id=999, client=_gateway_client("approve", 999)
    )
    assert gateway.request_approval("a post") is True


def test_review_gateway_returns_false_when_the_reviewer_taps_reject() -> None:
    """A Reject tap from the configured reviewer yields False."""
    gateway = TelegramReviewGateway(
        token="T", reviewer_chat_id=999, client=_gateway_client("reject", 999)
    )
    assert gateway.request_approval("a post") is False
