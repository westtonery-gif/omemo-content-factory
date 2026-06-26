"""Minimal ContentDirector — prove the existing domain runs a whole workflow.

A small, deterministic coordinator that sequences the **already existing** public operations
of the Run aggregate and the ``execute_task`` slice into one end-to-end workflow. It exists to
demonstrate that Run + Task + ``execute_task`` already function as a single system.

It is intentionally **not**: an intelligent agent, a production orchestrator, or the future
Content Director / Workflow Engine of ARCHITECTURE.md §4-5. It adds no new domain concepts,
introduces no infrastructure (no LLM, network, adapters, queues), never bypasses the Run
aggregate root, and changes nothing in Run or Task.

The work itself is delegated to an injected :class:`TaskExecutor` (a deterministic fake in
tests and in the demo). The produced output is not persisted: the domain ``Output`` entity is
deliberately out of scope at this stage, so a Task's domain-visible result is its status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from omemo_content_factory.application.task_execution import TaskExecutor, execute_task
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
        run.transition(RunStatus.QUEUED, by=_CD)
        run.transition(RunStatus.RUNNING, by=_CD)
        chained_input: str | None = None
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
                run.create_artifact(output.output_id, kind=request.artifact_kind, by=_CD)
                chained_input = output.payload
        if self._all_tasks_succeeded(run):
            run.transition(RunStatus.WAITING_QA, by=_CD)
            run.transition(RunStatus.WAITING_HUMAN, by=_CD)
            run.transition(RunStatus.COMPLETED, by=_CD)
        else:
            run.transition(RunStatus.FAILED, by=_CD, reason="one or more tasks failed")

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
