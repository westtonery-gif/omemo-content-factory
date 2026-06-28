"""Integration tests for the minimal task-execution slice (``application.task_execution``).

These tests verify the **integration** between ``execute_task`` and the Run/Task aggregates:
that the application slice opens a Task, drives it to a terminal outcome through the Run root,
propagates the executor's result, and produces one correctly-ordered domain-event log for the
whole flow. They intentionally do **not** re-test the Run or Task state machines, the Task
attempt counter, the completion guard or individual event semantics — those are covered by
``test_run.py`` and ``test_task.py``. A deterministic fake executor stands in for real work.
"""

from __future__ import annotations

from dataclasses import dataclass

from omemo_content_factory.application.task_execution import (
    ExecutionResult,
    TaskExecutor,
    execute_task,
)
from omemo_content_factory.domain.run import (
    Actor,
    Run,
    RunCompleted,
    RunCreated,
    RunEvent,
    RunQueued,
    RunStarted,
    RunStatus,
)
from omemo_content_factory.domain.task import (
    TaskCompleted,
    TaskCreated,
    TaskEvent,
    TaskStarted,
    TaskStatus,
)

RUN_ID = "run-exec-0001"
BRIEF_REF = "brief-0001"
WORKFLOW_REF = "workflow@v1"
STEP_REF = "step-1"
AGENT_REF = "writer@v1"
TASK_INPUT = "approved brief body"
CD = Actor.CONTENT_DIRECTOR

SUCCESS = ExecutionResult(succeeded=True, output="draft-v1")
FAILURE = ExecutionResult(succeeded=False, failure_reason="executor could not comply")


@dataclass(frozen=True, slots=True)
class StaticTaskExecutor:
    """Deterministic test double: returns a preconfigured result regardless of input."""

    result: ExecutionResult

    def execute(self, task_input: str) -> ExecutionResult:
        return self.result


def make_running_run() -> Run:
    """A Run driven to RUNNING, where Tasks are executed."""
    run = Run.create(
        run_id=RUN_ID,
        content_brief_ref=BRIEF_REF,
        workflow_version_ref=WORKFLOW_REF,
    )
    run.transition(RunStatus.QUEUED, by=CD)
    run.transition(RunStatus.RUNNING, by=CD)
    return run


def run_one_task(run: Run, executor: TaskExecutor) -> str:
    """Execute a single standard Task inside ``run`` via the application slice."""
    return execute_task(
        run,
        executor,
        workflow_step_ref=STEP_REF,
        agent_ref=AGENT_REF,
        task_input=TASK_INPUT,
    )


def test_successful_execution_drives_the_task_to_succeeded() -> None:
    """The slice opens a Task and drives it to SUCCEEDED, reachable only through the Run root."""
    run = make_running_run()
    task_id = run_one_task(run, StaticTaskExecutor(SUCCESS))
    assert run.task(task_id).status is TaskStatus.SUCCEEDED


def test_failed_execution_propagates_the_reason_to_the_task() -> None:
    """The slice routes a failed execution to a FAILED Task carrying the executor's reason."""
    run = make_running_run()
    task_id = run_one_task(run, StaticTaskExecutor(FAILURE))
    view = run.task(task_id)
    assert view.status is TaskStatus.FAILED
    assert view.failure_reason == "executor could not comply"


def test_full_slice_create_run_execute_task_complete_run() -> None:
    """Create Run -> open + execute Task -> complete Task -> complete Run (rules permitting)."""
    run = make_running_run()
    run_one_task(run, StaticTaskExecutor(SUCCESS))
    run.transition(RunStatus.WAITING_QA, by=CD)
    run.transition(RunStatus.WAITING_HUMAN, by=CD)
    run.transition(RunStatus.COMPLETED, by=CD)
    assert run.status is RunStatus.COMPLETED


# --- 3B: ExecutionResult.payload_fields (data-only; not consumed by execution yet) -------


def test_execution_result_payload_fields_defaults_to_none() -> None:
    assert ExecutionResult(succeeded=True, output="x").payload_fields is None


def test_execution_result_carries_payload_fields() -> None:
    result = ExecutionResult(
        succeeded=True, output="x", schema_ref="s@1", payload_fields={"facts": "a"}
    )
    assert result.payload_fields == {"facts": "a"}


def test_payload_fields_without_schema_record_no_output() -> None:
    """3D: Output is recorded only via the validated path (needs a Schema); fields alone -> none."""
    run = make_running_run()
    result = ExecutionResult(
        succeeded=True, output="draft", schema_ref="s@1", payload_fields={"facts": "a"}
    )
    task_id = run_one_task(run, StaticTaskExecutor(result))
    view = run.task(task_id)
    assert view.status is TaskStatus.SUCCEEDED
    assert view.output is None  # no schema supplied -> no validated Output (no always-VALID path)


def test_full_slice_records_run_and_task_events_in_one_ordered_log() -> None:
    """The whole flow is traced once, in order, in the Run's single event log."""
    run = make_running_run()
    run_one_task(run, StaticTaskExecutor(SUCCESS))
    run.transition(RunStatus.WAITING_QA, by=CD)
    run.transition(RunStatus.WAITING_HUMAN, by=CD)
    run.transition(RunStatus.COMPLETED, by=CD)
    expected: list[type[RunEvent | TaskEvent]] = [
        RunCreated,
        RunQueued,
        RunStarted,
        TaskCreated,
        TaskStarted,
        TaskCompleted,
        RunCompleted,
    ]
    assert [type(event) for event in run.events] == expected
