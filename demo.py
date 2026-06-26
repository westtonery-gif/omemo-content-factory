"""Demonstration: an auto-run Telegram-post pipeline with a human approval gate.

One Workflow — Research -> Writer -> Editor — runs **automatically** on a real Anthropic model
to produce a short Telegram post, then **stops at the Approval Gate**. Production is automated;
**publication is not**: the post is delivered to Telegram only after you explicitly approve it
(PROJECT.md §1, §12). The domain knows nothing of the model or Telegram — both live in the
infrastructure layer behind the ``TaskExecutor`` and ``Publisher`` ports.

It shows: the Run/Task statuses, each Task's Output, the Artifacts (provenance
``Task -> Output -> Artifact``), the candidate post, your decision, and the final Run status.

Run with: ``python demo.py``. Needs ``ANTHROPIC_API_KEY``, ``TELEGRAM_BOT_TOKEN`` and
``TELEGRAM_CHAT_ID`` in the environment (optionally ``OMEMO_LLM_MODEL``); without them the demo
explains what to set and exits. Approval is read from the terminal — a non-interactive run
declines (fail-closed), so nothing is published by accident.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from omemo_content_factory.application.content_director import ContentDirector, TaskRequest
from omemo_content_factory.application.task_execution import TaskExecutor
from omemo_content_factory.domain.artifact import ArtifactCreated, ArtifactEvent
from omemo_content_factory.domain.human_review import (
    HumanReviewEvent,
    HumanReviewRejected,
    ReviewStatus,
)
from omemo_content_factory.domain.output import OutputEvent
from omemo_content_factory.domain.run import Actor, Run, RunEvent, RunFailed
from omemo_content_factory.domain.task import TaskEvent, TaskFailed
from omemo_content_factory.infrastructure.llm import AnthropicLLMClient, LLMTaskExecutor
from omemo_content_factory.infrastructure.telegram import TelegramPublisher

DEFAULT_MODEL = "claude-sonnet-4-6"
REQUIRED_ENV = ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

BRIEF = (
    "Topic: simple, evidence-based tips for better sleep. Audience: general adults. "
    "Format: a short, friendly Telegram post."
)

RESEARCH_PROMPT = (
    "You are a health-content researcher for OMEMO Health. From the brief, list the key "
    "evidence-based points and one caveat suitable for a SHORT social post. Be accurate and "
    "non-alarmist; do not fabricate studies or statistics."
)
WRITER_PROMPT = (
    "You are a social-media writer for OMEMO Health. From the research notes, write a SHORT, "
    "friendly Telegram post (about 3-5 sentences) for a general audience. Keep it evidence-based, "
    "non-alarmist and in plain language."
)
EDITOR_PROMPT = (
    "You are an editor for OMEMO Health. Polish the draft into the final Telegram post: concise, "
    "warm and non-alarmist, ending with a one-line general disclaimer. Return only the post text."
)


def safe_print(text: str = "") -> None:
    """Print, replacing characters the console cannot encode (robust on any locale)."""
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(encoding, errors="replace").decode(encoding) + "\n")


def short(text: str, limit: int = 100) -> str:
    """One-line, length-bounded preview of a (possibly long) model output."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "..."


def describe_event(
    event: RunEvent | TaskEvent | OutputEvent | ArtifactEvent | HumanReviewEvent,
) -> str:
    """Render one domain event as a short human-readable line."""
    name = type(event).__name__
    if isinstance(event, ArtifactCreated):
        return f"{name}(artifact={event.artifact_id}, from_output={event.output_ref})"
    if isinstance(event, ArtifactEvent):
        return f"{name}(artifact={event.artifact_id})"
    if isinstance(event, HumanReviewRejected):
        return f"{name}(review={event.review_id}, reason={event.reason})"
    if isinstance(event, HumanReviewEvent):
        return f"{name}(review={event.review_id})"
    if isinstance(event, OutputEvent):
        return f"{name}(task={event.task_id}, output={event.output_id})"
    if isinstance(event, TaskFailed):
        return f"{name}(task={event.task_id}, reason={event.reason})"
    if isinstance(event, TaskEvent):
        return f"{name}(task={event.task_id})"
    if isinstance(event, RunFailed):
        return f"{name}(reason={event.reason})"
    return name


def show_run(run: Run) -> None:
    """Print the Task results, Artifacts (with provenance), event journal and final status."""
    safe_print(f"Run: {run.run_id}  ({run.content_brief_ref}, {run.workflow_version_ref})")

    safe_print("  Tasks:")
    for view in run.tasks:
        detail = f"attempts={view.attempt_count}"
        if view.failure_reason is not None:
            detail += f", reason={view.failure_reason}"
        columns = f"{view.workflow_step_ref:<10} {view.agent_ref:<14} {view.status.value:<10}"
        safe_print(f"    - {columns} ({detail})")
        if view.output is not None:
            safe_print(f"        -> Output {view.output.output_id}: {short(view.output.payload)}")

    if run.artifacts:
        safe_print("  Artifacts (provenance Task -> Output -> Artifact):")
        for artifact in run.artifacts:
            safe_print(
                f"    - {artifact.artifact_id} [{artifact.status.value}]"
                f" kind={artifact.kind} from_output={artifact.output_ref}"
            )

    safe_print("  Event journal:")
    for index, event in enumerate(run.events, start=1):
        safe_print(f"    {index:>2}. {describe_event(event)}")

    safe_print(f"  Final Run status: {run.status.value.upper()}")


def ask_approval() -> bool:
    """Read the human's decision from the terminal; a non-interactive run declines (fail-closed)."""
    try:
        answer = input("Approve and publish this post to Telegram? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer == "y"


def main() -> None:
    """Auto-produce a Telegram post, pause for human approval, and publish only if approved."""
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        safe_print("Cannot run the real Telegram pipeline; missing environment variables:")
        for name in missing:
            safe_print(f"  - {name}")
        safe_print("Set them and re-run, e.g. (PowerShell):")
        safe_print('  $env:ANTHROPIC_API_KEY = "sk-ant-..."')
        safe_print('  $env:TELEGRAM_BOT_TOKEN = "123456:ABC..."')
        safe_print('  $env:TELEGRAM_CHAT_ID = "@your_channel_or_chat_id"')
        safe_print(f"Optional: OMEMO_LLM_MODEL (default {DEFAULT_MODEL}).")
        return

    model = os.environ.get("OMEMO_LLM_MODEL", DEFAULT_MODEL)
    llm = AnthropicLLMClient(model=model)
    executors: Mapping[str, TaskExecutor] = {
        "researcher@v1": LLMTaskExecutor(llm, RESEARCH_PROMPT, "research-notes@v1"),
        "writer@v1": LLMTaskExecutor(llm, WRITER_PROMPT, "post-draft@v1"),
        "editor@v1": LLMTaskExecutor(llm, EDITOR_PROMPT, "final-post@v1"),
    }
    director = ContentDirector(executors)
    publisher = TelegramPublisher(
        token=os.environ["TELEGRAM_BOT_TOKEN"], chat_id=os.environ["TELEGRAM_CHAT_ID"]
    )

    run = Run.create(
        run_id="run-telegram-001",
        content_brief_ref="brief-sleep",
        workflow_version_ref="telegram-post@v1",
    )
    tasks = [
        TaskRequest("research", "researcher@v1", BRIEF, artifact_kind="research-notes"),
        TaskRequest("write", "writer@v1", "", artifact_kind="post-draft"),
        TaskRequest("edit", "editor@v1", "", artifact_kind="final-post"),
    ]

    safe_print("=" * 78)
    safe_print(
        f"Auto-run: Research -> Writer -> Editor on {model} (publication needs your approval)"
    )
    safe_print("=" * 78)
    review_id = director.produce_for_review(run, tasks)
    if review_id is None:
        safe_print("Production failed before reaching the Approval Gate.")
        show_run(run)
        return

    candidate = run.artifact(run.human_review(review_id).artifact_ref)
    safe_print("")
    safe_print("CANDIDATE POST (awaiting your approval):")
    safe_print("-" * 78)
    safe_print(candidate.content)
    safe_print("-" * 78)

    if ask_approval():
        run.submit_review(review_id, ReviewStatus.APPROVED, by=Actor.HUMAN_REVIEWER)
        reference = director.publish_if_approved(run, review_id, publisher)
        safe_print(f"Approved -> published to Telegram: {reference}")
    else:
        run.submit_review(
            review_id, ReviewStatus.REJECTED, by=Actor.HUMAN_REVIEWER, reason="declined by reviewer"
        )
        director.publish_if_approved(run, review_id, publisher)
        safe_print("Declined -> nothing was published.")

    safe_print("")
    show_run(run)


if __name__ == "__main__":
    main()
