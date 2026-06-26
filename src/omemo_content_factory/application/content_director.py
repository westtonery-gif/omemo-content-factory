"""ContentDirector — sequences the existing domain into whole workflows.

A deterministic coordinator over the public operations of the Run aggregate root. It offers two
flows, both of which only ever act **through the root** and add no domain concepts:

* ``execute`` — production to a self-contained, auto-completed Run (no external publication).
* ``produce_for_review`` + ``publish_if_approved`` — production to the Approval Gate, then, **only
  after an explicit human ``Approve``**, external delivery via an injected ``Publisher``
  (the human-in-the-loop invariant, PROJECT.md §1, §12).

Work is delegated to injected ``TaskExecutor`` ports (a deterministic fake in tests; a real model
in the demo) and an injected ``Publisher`` port (a fake in tests; Telegram in the demo). No
infrastructure, prompts or content decisions live here — only orchestration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from omemo_content_factory.application.publishing import Publisher, PublishError
from omemo_content_factory.application.task_execution import TaskExecutor, execute_task
from omemo_content_factory.domain.artifact import ArtifactId, ArtifactStatus
from omemo_content_factory.domain.human_review import ReviewId, ReviewStatus
from omemo_content_factory.domain.run import Actor, Run, RunStatus
from omemo_content_factory.domain.task import TaskStatus

_CD = Actor.CONTENT_DIRECTOR


@dataclass(frozen=True, slots=True)
class TaskRequest:
    """One task to run within a workflow: which step, which role, the input, the artifact kind.

    A plain application-level input describing a unit of work. It is **not** the domain
    ``Workflow Step`` entity (deliberately out of scope at this stage); it only carries the
    opaque references and input that ``Run.open_task`` already requires, plus the ``kind`` of
    Artifact the step's Output yields (``Run.create_artifact``; ADR-0006 §10).
    """

    workflow_step_ref: str
    agent_ref: str
    task_input: str
    artifact_kind: str = "draft"


class ContentDirector:
    """Sequences the existing domain operations into one workflow.

    The executor is the injected execution abstraction. It may be a **single** ``TaskExecutor``
    used for every step, or a **mapping** from ``agent_ref`` (role) to a ``TaskExecutor`` so each
    role runs with its own implementation/prompt — selecting which executor runs a step is
    orchestration (ARCHITECTURE.md §4: the Content Director "calls agents"). The executors
    themselves are unaware of one another; the role's prompt lives inside its executor, not here.
    """

    def __init__(self, executor: TaskExecutor | Mapping[str, TaskExecutor]) -> None:
        self._executor = executor

    def execute(self, run: Run, tasks: Sequence[TaskRequest]) -> None:
        """Orchestrate an **already-created** Run through its full lifecycle.

        Creating the Run is the caller's responsibility (e.g. an entry point), in line with
        ARCHITECTURE.md §3.4 where the Content Director receives a *created* Run; this method
        only orchestrates. The Run is expected to be freshly created (in ``CREATED``).

        Steps (all via the public aggregate API, never bypassing the root):
        ``QUEUED`` -> ``RUNNING`` -> for each request, the role's executor runs the Task
        (``execute_task``) and, when it produced an Output, an Artifact is created from it
        (provenance ``Task -> Output -> Artifact``). Structured data flows between steps: a Task's
        Output becomes the next Task's input (ARCHITECTURE.md §4), so the first step gets the
        brief (its ``task_input``) and each later step gets the previous Output. If every Task
        succeeded, the Run proceeds ``WAITING_QA`` -> ``WAITING_HUMAN`` -> ``COMPLETED``;
        otherwise it is routed to ``FAILED``. The Run is mutated in place through its own API.
        """
        self._produce(run, tasks)
        if self._all_tasks_succeeded(run):
            run.transition(RunStatus.WAITING_QA, by=_CD)
            run.transition(RunStatus.WAITING_HUMAN, by=_CD)
            run.transition(RunStatus.COMPLETED, by=_CD)
        else:
            run.transition(RunStatus.FAILED, by=_CD, reason="one or more tasks failed")

    def produce_for_review(self, run: Run, tasks: Sequence[TaskRequest]) -> ReviewId | None:
        """Run production up to the Approval Gate and open a Human Review on the final Artifact.

        For an approval-gated, externally-published workflow (e.g. Telegram): produce the
        artifacts, drive the Run to ``WAITING_HUMAN``, move the **final** Artifact to ``CANDIDATE``
        and open a ``PENDING`` Human Review on it. **Stops there** — it does not complete the Run
        and publishes nothing; that waits for an explicit human decision (PROJECT.md §12). Returns
        the review id, or ``None`` if production failed (Run routed to ``FAILED``).
        """
        artifact_ids = self._produce(run, tasks)
        if not self._all_tasks_succeeded(run) or not artifact_ids:
            run.transition(RunStatus.FAILED, by=_CD, reason="production did not yield an artifact")
            return None
        run.transition(RunStatus.WAITING_QA, by=_CD)
        run.transition(RunStatus.WAITING_HUMAN, by=_CD)
        final_artifact_id = artifact_ids[-1]
        run.transition_artifact(final_artifact_id, ArtifactStatus.CANDIDATE, by=_CD)
        return run.open_human_review(final_artifact_id, by=_CD)

    def publish_if_approved(
        self, run: Run, review_id: ReviewId, publisher: Publisher
    ) -> str | None:
        """Finalise the Run after the human decision (PROJECT.md §12).

        On ``Approve``: move the reviewed Artifact ``APPROVED -> PUBLISHED``, deliver it through
        the ``publisher`` (the only external action — and only here, after approval), complete the
        Run, and return the external reference. On any other decision, or if delivery fails, reject
        the Artifact and route the Run to ``FAILED`` (nothing is published). Returns the reference,
        or ``None`` when nothing was published.
        """
        review = run.human_review(review_id)
        artifact_id = review.artifact_ref
        if review.status is not ReviewStatus.APPROVED:
            run.transition_artifact(artifact_id, ArtifactStatus.REJECTED, by=_CD)
            run.transition(RunStatus.FAILED, by=_CD, reason="rejected at human review")
            return None
        run.transition_artifact(artifact_id, ArtifactStatus.APPROVED, by=_CD)
        try:
            reference = publisher.publish(run.artifact(artifact_id).content)
        except PublishError as exc:
            run.transition(RunStatus.FAILED, by=_CD, reason=f"publication failed: {exc}")
            return None
        run.transition_artifact(artifact_id, ArtifactStatus.PUBLISHED, by=_CD)
        run.transition(RunStatus.COMPLETED, by=_CD)
        return reference

    def _produce(self, run: Run, tasks: Sequence[TaskRequest]) -> list[ArtifactId]:
        """Drive ``QUEUED -> RUNNING`` and run each Task, chaining Outputs; return artifact ids.

        Shared by ``execute`` and ``produce_for_review``. Structured data flows between steps: a
        Task's Output becomes the next Task's input (ARCHITECTURE.md §4); the first step gets the
        brief (its ``task_input``), each later step the previous Output. Each produced Output yields
        one Artifact (provenance ``Task -> Output -> Artifact``).
        """
        run.transition(RunStatus.QUEUED, by=_CD)
        run.transition(RunStatus.RUNNING, by=_CD)
        chained_input: str | None = None
        artifact_ids: list[ArtifactId] = []
        for request in tasks:
            task_input = request.task_input if chained_input is None else chained_input
            task_id = execute_task(
                run,
                self._resolve(request.agent_ref),
                workflow_step_ref=request.workflow_step_ref,
                agent_ref=request.agent_ref,
                task_input=task_input,
            )
            output = run.task(task_id).output
            if output is not None:
                artifact_ids.append(
                    run.create_artifact(output.output_id, kind=request.artifact_kind, by=_CD)
                )
                chained_input = output.payload
        return artifact_ids

    def _resolve(self, agent_ref: str) -> TaskExecutor:
        """Pick the executor for a role: the per-role mapping entry, or the single executor."""
        executor = self._executor
        if isinstance(executor, Mapping):
            return executor[agent_ref]
        return executor

    @staticmethod
    def _all_tasks_succeeded(run: Run) -> bool:
        """Whether every Task owned by ``run`` reached ``SUCCEEDED`` (read-only via the root)."""
        return all(view.status is TaskStatus.SUCCEEDED for view in run.tasks)
