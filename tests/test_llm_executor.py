"""Offline tests for the LLM-backed TaskExecutor (``infrastructure.llm.LLMTaskExecutor``).

These bind only to the public contract (``execute`` -> ``ExecutionResult``) and inject a
deterministic fake ``LLMClient`` — no SDK, no network, no API key. The real ``AnthropicLLMClient``
is a thin adapter exercised by the demo, not unit-tested with mocks. End to end, the executor is
driven through the Run aggregate root; under the validated finalization (3D) it does not yet emit
structured ``payload_fields``, so the pipeline runs to COMPLETED without recording an Output (a
follow-up infra slice adds structured model output).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omemo_content_factory.application.content_director import ContentDirector, TaskRequest
from omemo_content_factory.domain.run import Run, RunStatus
from omemo_content_factory.domain.task import TaskStatus
from omemo_content_factory.infrastructure.llm import LLMError, LLMTaskExecutor


@dataclass(frozen=True, slots=True)
class EchoLLMClient:
    """Deterministic fake: returns the input prefixed by the system prompt's role tag."""

    tag: str

    def complete(self, *, system: str, user: str) -> str:
        return f"{self.tag}:{user}"


@dataclass
class RecordingLLMClient:
    """Fake that records the (system, user) it was called with and returns a fixed text."""

    reply: str
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


@dataclass(frozen=True, slots=True)
class FailingLLMClient:
    """Deterministic fake that always fails with an ``LLMError``."""

    def complete(self, *, system: str, user: str) -> str:
        raise LLMError("rate limited")


def test_successful_completion_becomes_a_valid_execution_result() -> None:
    """A model completion is wrapped as a successful ExecutionResult with output + schema_ref."""
    executor = LLMTaskExecutor(EchoLLMClient("writer"), "system prompt", "draft@v1")
    result = executor.execute("the brief")
    assert result.succeeded is True
    assert result.output == "writer:the brief"
    assert result.schema_ref == "draft@v1"


def test_executor_passes_its_system_prompt_and_input_to_the_client() -> None:
    """The role's system prompt and the Task input are forwarded to the model call."""
    client = RecordingLLMClient(reply="done")
    executor = LLMTaskExecutor(client, "you are a writer", "draft@v1")
    executor.execute("research notes")
    assert client.calls == [("you are a writer", "research notes")]


def test_model_failure_becomes_a_managed_failed_result() -> None:
    """An LLMError is converted to a FAILED ExecutionResult, not propagated (PROJECT.md §10)."""
    executor = LLMTaskExecutor(FailingLLMClient(), "system prompt", "draft@v1")
    result = executor.execute("the brief")
    assert result.succeeded is False
    assert result.output is None
    assert result.failure_reason is not None
    assert "rate limited" in result.failure_reason


def test_three_role_pipeline_runs_end_to_end_through_the_root() -> None:
    """Research -> Writer -> Editor with per-role LLM executors yields a COMPLETED Run.

    Under the validated finalization (3D, Variant A) the LLM executor does not yet emit structured
    ``payload_fields``, so no Output is recorded (structured model output is a follow-up infra
    slice). The pipeline still runs deterministically: every Task SUCCEEDED and the Run COMPLETED.
    """
    executors = {
        "researcher@v1": LLMTaskExecutor(EchoLLMClient("research"), "research", "notes@v1"),
        "writer@v1": LLMTaskExecutor(EchoLLMClient("write"), "write", "draft@v1"),
        "editor@v1": LLMTaskExecutor(EchoLLMClient("edit"), "edit", "final@v1"),
    }
    director = ContentDirector(executors)
    run = Run.create(
        run_id="run-llm", content_brief_ref="brief", workflow_version_ref="health-article@v1"
    )
    director.execute(
        run,
        [
            TaskRequest("step-research", "researcher@v1", "BRIEF", artifact_kind="notes"),
            TaskRequest("step-write", "writer@v1", "", artifact_kind="draft"),
            TaskRequest("step-edit", "editor@v1", "", artifact_kind="final"),
        ],
    )
    assert run.status is RunStatus.COMPLETED
    assert [view.status for view in run.tasks] == [TaskStatus.SUCCEEDED] * 3
    # Option A: no structured payload_fields from the LLM executor yet -> no validated Output,
    # hence no Artifact (structured output is a separate follow-up infra slice).
    assert all(view.output is None for view in run.tasks)
    assert len(run.artifacts) == 0
