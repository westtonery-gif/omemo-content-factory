"""Demonstration: the first real AI run on the existing architecture.

Runs one Workflow — Research -> Writer -> Editor — through the real ``ContentDirector`` and the
real Run/Task/Output/Artifact domain, with each role backed by a live Anthropic model behind the
application's ``TaskExecutor`` port. The domain knows nothing of the model; the LLM lives only in
the infrastructure layer.

It shows, for the run: the Run status, each Task's status, each Task's Output, the Artifacts (with
provenance ``Task -> Output -> Artifact``), the domain-event journal, and the final article.

Run with: ``python demo.py``. A real model call needs ``ANTHROPIC_API_KEY`` in the environment
(optionally ``OMEMO_LLM_MODEL`` to choose the model); without a key the demo explains how to set
it and exits cleanly. No QA, Human Review, publication or external integrations are involved.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from omemo_content_factory.application.content_director import ContentDirector, TaskRequest
from omemo_content_factory.application.task_execution import TaskExecutor
from omemo_content_factory.domain.artifact import ArtifactCreated, ArtifactEvent
from omemo_content_factory.domain.output import OutputEvent
from omemo_content_factory.domain.run import Run, RunEvent, RunFailed
from omemo_content_factory.domain.task import TaskEvent, TaskFailed
from omemo_content_factory.infrastructure.llm import AnthropicLLMClient, LLMTaskExecutor

DEFAULT_MODEL = "claude-sonnet-4-6"

BRIEF = (
    "Topic: the health benefits of magnesium for a general adult audience. "
    "Goal: a short, trustworthy, evidence-based article (~400-500 words) with a clear "
    "structure and a calm, non-alarmist tone."
)

RESEARCH_PROMPT = (
    "You are a meticulous health-content researcher for OMEMO Health. From the content brief, "
    "produce concise, evidence-based research notes: key facts, a suggested article structure, "
    "and any necessary medical caveats. Be accurate and non-alarmist. Do not fabricate studies "
    "or statistics."
)
WRITER_PROMPT = (
    "You are a health-content writer for OMEMO Health. From the research notes, write a clear, "
    "engaging article draft for a general audience, following the suggested structure. Keep every "
    "claim evidence-based and non-alarmist. Include a brief, general medical disclaimer."
)
EDITOR_PROMPT = (
    "You are a health-content editor for OMEMO Health. From the article draft, produce the final "
    "polished article: improve clarity, flow and accuracy, keep a calm non-alarmist tone, and "
    "keep a brief medical disclaimer. Return only the final article text."
)


def safe_print(text: str = "") -> None:
    """Print, replacing characters the console cannot encode (robust on any locale)."""
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(encoding, errors="replace").decode(encoding) + "\n")


def short(text: str, limit: int = 100) -> str:
    """One-line, length-bounded preview of a (possibly long) model output."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "..."


def describe_event(event: RunEvent | TaskEvent | OutputEvent | ArtifactEvent) -> str:
    """Render one domain event as a short human-readable line."""
    name = type(event).__name__
    if isinstance(event, ArtifactCreated):
        return f"{name}(artifact={event.artifact_id}, from_output={event.output_ref})"
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
    safe_print(f"Run: {run.run_id}")
    safe_print(f"  brief={run.content_brief_ref}, workflow={run.workflow_version_ref}")

    safe_print("  Tasks:")
    for view in run.tasks:
        detail = f"attempts={view.attempt_count}"
        if view.failure_reason is not None:
            detail += f", reason={view.failure_reason}"
        columns = f"{view.workflow_step_ref:<10} {view.agent_ref:<14} {view.status.value:<10}"
        safe_print(f"    - {columns} ({detail})")
        if view.output is not None:
            safe_print(f"        -> Output {view.output.output_id} [{view.output.status.value}]")
            safe_print(f"           preview: {short(view.output.payload)}")

    if run.artifacts:
        origin = {
            view.output.output_id: view.workflow_step_ref
            for view in run.tasks
            if view.output is not None
        }
        safe_print("  Artifacts (provenance Task -> Output -> Artifact):")
        for artifact in run.artifacts:
            step = origin.get(artifact.output_ref, "?")
            safe_print(
                f"    - {artifact.artifact_id} [{artifact.status.value}] kind={artifact.kind}"
            )
            safe_print(f"        from: task {step} -> output {artifact.output_ref}")

    safe_print("  Event journal:")
    for index, event in enumerate(run.events, start=1):
        safe_print(f"    {index:>2}. {describe_event(event)}")

    safe_print(f"  Final Run status: {run.status.value.upper()}")


def print_final_article(run: Run) -> None:
    """Print the final article — the last Task's Output."""
    final = run.tasks[-1].output if run.tasks else None
    safe_print("")
    safe_print("=" * 78)
    safe_print("FINAL ARTICLE")
    safe_print("=" * 78)
    if final is None:
        safe_print("(no final article — the run did not produce a final Output)")
        return
    safe_print(final.payload)


def main() -> None:
    """Run the Research -> Writer -> Editor workflow on a real model and print the result."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        safe_print("ANTHROPIC_API_KEY is not set, so no real model can be called.")
        safe_print("Set it and re-run, e.g.:")
        safe_print('  PowerShell:  $env:ANTHROPIC_API_KEY = "sk-ant-..."')
        safe_print("  bash:        export ANTHROPIC_API_KEY=sk-ant-...")
        safe_print(f"Optionally set OMEMO_LLM_MODEL (default: {DEFAULT_MODEL}).")
        return

    model = os.environ.get("OMEMO_LLM_MODEL", DEFAULT_MODEL)
    client = AnthropicLLMClient(model=model)
    executors: Mapping[str, TaskExecutor] = {
        "researcher@v1": LLMTaskExecutor(client, RESEARCH_PROMPT, "research-notes@v1"),
        "writer@v1": LLMTaskExecutor(client, WRITER_PROMPT, "article-draft@v1"),
        "editor@v1": LLMTaskExecutor(client, EDITOR_PROMPT, "final-article@v1"),
    }
    director = ContentDirector(executors)

    run = Run.create(
        run_id="run-magnesium-001",
        content_brief_ref="brief-magnesium",
        workflow_version_ref="health-article@v1",
    )
    tasks = [
        TaskRequest("research", "researcher@v1", BRIEF, artifact_kind="research-notes"),
        TaskRequest("write", "writer@v1", "", artifact_kind="article-draft"),
        TaskRequest("edit", "editor@v1", "", artifact_kind="final-article"),
    ]

    safe_print("=" * 78)
    safe_print(f"First real AI run - Research -> Writer -> Editor on model {model}")
    safe_print("=" * 78)
    director.execute(run, tasks)
    show_run(run)
    print_final_article(run)


if __name__ == "__main__":
    main()
