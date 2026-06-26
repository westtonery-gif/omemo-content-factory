"""Behavioural tests for the Task child entity of the Run aggregate.

Every test exercises a single business rule of Task and references the corresponding
`TASK_ACCEPTANCE.md` scenario(s) in its docstring. Tests drive Task **only through the Run
aggregate's public contract** (``open_task`` / ``transition_task`` / read-only ``tasks`` /
``task`` and the ``TaskStatus`` / ``TaskRetryPolicy`` / ``TaskView`` / event / error types):
there is no public Task factory and no mutable Task object, exactly as ADR-0004 §4 requires.
No Enum/dataclass behaviour is tested; no mocks, monkeypatch, sleep or randomness are used.

The expected transition table is encoded here from TASK_SPEC.md §4 (the source of truth),
independently of the implementation's private tables.
"""

from __future__ import annotations

import pytest

from omemo_content_factory.domain.run import (
    Actor,
    InvalidTransitionError,
    Run,
    RunStatus,
    UnauthorizedActorError,
)
from omemo_content_factory.domain.task import (
    InvalidTaskTransitionError,
    TaskCompleted,
    TaskCreated,
    TaskEvent,
    TaskFailed,
    TaskRetryLimitExceededError,
    TaskRetryPolicy,
    TaskStarted,
    TaskStatus,
)

RUN_ID = "run-0001"
BRIEF_REF = "brief-0001"
WORKFLOW_REF = "workflow@v1"
STEP_REF = "step-1"
AGENT_REF = "writer@v1"
TASK_INPUT = "task-input-0001"
CD = Actor.CONTENT_DIRECTOR

# Allowed Task transitions per TASK_SPEC.md §4 — the test suite's own expectation.
_ALLOWED_BY_SPEC: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.SKIPPED},
    TaskStatus.RUNNING: {TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED},
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.SKIPPED: set(),
}

_FORBIDDEN_TRANSITIONS: list[tuple[TaskStatus, TaskStatus]] = [
    (source, target)
    for source in TaskStatus
    for target in TaskStatus
    if target not in _ALLOWED_BY_SPEC[source]
]

_TERMINAL_STATES: list[TaskStatus] = [
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.SKIPPED,
]

# Shortest sequence of Task transitions that drives a fresh (PENDING) Task into each state.
_PATH_TO: dict[TaskStatus, tuple[TaskStatus, ...]] = {
    TaskStatus.PENDING: (),
    TaskStatus.RUNNING: (TaskStatus.RUNNING,),
    TaskStatus.SUCCEEDED: (TaskStatus.RUNNING, TaskStatus.SUCCEEDED),
    TaskStatus.FAILED: (TaskStatus.RUNNING, TaskStatus.FAILED),
    TaskStatus.SKIPPED: (TaskStatus.SKIPPED,),
}


def make_run() -> Run:
    """Create a fresh Run from the standard sample input."""
    return Run.create(
        run_id=RUN_ID,
        content_brief_ref=BRIEF_REF,
        workflow_version_ref=WORKFLOW_REF,
    )


def open_task(run: Run, retry_policy: TaskRetryPolicy | None = None) -> str:
    """Open a Task on ``run`` from the standard sample input; return its id."""
    return run.open_task(
        workflow_step_ref=STEP_REF,
        agent_ref=AGENT_REF,
        task_input=TASK_INPUT,
        by=CD,
        retry_policy=retry_policy,
    )


def task_in(state: TaskStatus, retry_policy: TaskRetryPolicy | None = None) -> tuple[Run, str]:
    """Return a fresh Run plus the id of a Task driven to ``state`` along the canonical path."""
    run = make_run()
    task_id = open_task(run, retry_policy)
    for status in _PATH_TO[state]:
        run.transition_task(task_id, status, by=CD)
    return run, task_id


def drive_run_to_waiting_human(run: Run) -> None:
    """Drive ``run`` along the canonical path up to the human Approval Gate."""
    for status in (
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING_QA,
        RunStatus.WAITING_HUMAN,
    ):
        run.transition(status, by=CD)


# --- Happy path --------------------------------------------------------------------------


def test_open_task_creates_a_pending_task() -> None:
    """THP-01: opening a Task yields a PENDING Task with zero attempts, owned by the Run."""
    run = make_run()
    task_id = open_task(run)
    view = run.task(task_id)
    assert view.task_id == task_id
    assert view.run_id == RUN_ID
    assert view.status is TaskStatus.PENDING
    assert view.attempt_count == 0


def test_first_start_enters_running_and_counts_one_attempt() -> None:
    """THP-02: PENDING -> RUNNING is the first attempt."""
    run = make_run()
    task_id = open_task(run)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    view = run.task(task_id)
    assert view.status is TaskStatus.RUNNING
    assert view.attempt_count == 1


def test_running_to_succeeded_is_terminal() -> None:
    """THP-03: RUNNING -> SUCCEEDED reaches a terminal state."""
    run, task_id = task_in(TaskStatus.RUNNING)
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    assert run.task(task_id).status is TaskStatus.SUCCEEDED


def test_pending_to_skipped_is_terminal_without_event() -> None:
    """THP-04 / TEV-05: PENDING -> SKIPPED is terminal and emits no dedicated event."""
    run = make_run()
    task_id = open_task(run)
    before = list(run.events)
    run.transition_task(task_id, TaskStatus.SKIPPED, by=CD)
    assert run.task(task_id).status is TaskStatus.SKIPPED
    assert list(run.events) == before


# --- Retry -------------------------------------------------------------------------------


def test_retry_increments_attempt_and_emits_no_event() -> None:
    """TRW-01 / TEV-02: a RUNNING -> RUNNING retry counts an attempt but emits no event."""
    run, task_id = task_in(TaskStatus.RUNNING)
    before = list(run.events)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    view = run.task(task_id)
    assert view.status is TaskStatus.RUNNING
    assert view.attempt_count == 2
    assert list(run.events) == before


def test_retry_beyond_attempt_limit_is_rejected() -> None:
    """TRW-02 / TINV-06: a retry that would exceed the policy bound is rejected."""
    run = make_run()
    task_id = open_task(run, TaskRetryPolicy(max_attempts=2))
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # attempt 1 (first start)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # attempt 2 (retry) — allowed
    assert run.task(task_id).attempt_count == 2
    with pytest.raises(TaskRetryLimitExceededError):
        run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # attempt 3 — exceeds
    view = run.task(task_id)
    assert view.status is TaskStatus.RUNNING
    assert view.attempt_count == 2


def test_task_can_succeed_after_a_retry() -> None:
    """TRW-03: after a retry the Task can still succeed, keeping its attempt count."""
    run = make_run()
    task_id = open_task(run, TaskRetryPolicy(max_attempts=3))
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # retry
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    view = run.task(task_id)
    assert view.status is TaskStatus.SUCCEEDED
    assert view.attempt_count == 2


# --- Forbidden transitions & failures ----------------------------------------------------


@pytest.mark.parametrize(("source", "target"), _FORBIDDEN_TRANSITIONS)
def test_forbidden_task_transitions_are_rejected(source: TaskStatus, target: TaskStatus) -> None:
    """TFL-01 / TINV-04 / TINV-05: only spec edges are allowed.

    Covers forbidden edges, the skip-from-RUNNING case and any transition out of a terminal.
    """
    run, task_id = task_in(source)
    with pytest.raises(InvalidTaskTransitionError):
        run.transition_task(task_id, target, by=CD)
    assert run.task(task_id).status is source


@pytest.mark.parametrize("terminal", _TERMINAL_STATES)
def test_terminal_task_rejects_further_transitions(terminal: TaskStatus) -> None:
    """TINV-05: a terminal Task has no outgoing transitions."""
    run, task_id = task_in(terminal)
    for target in TaskStatus:
        with pytest.raises(InvalidTaskTransitionError):
            run.transition_task(task_id, target, by=CD)
    assert run.task(task_id).status is terminal


def test_running_to_failed_records_reason_and_emits_event() -> None:
    """TFL-02 / TEV-04: RUNNING -> FAILED records the reason and emits TaskFailed."""
    run, task_id = task_in(TaskStatus.RUNNING)
    run.transition_task(task_id, TaskStatus.FAILED, by=CD, reason="provider unavailable")
    view = run.task(task_id)
    assert view.status is TaskStatus.FAILED
    assert view.failure_reason == "provider unavailable"
    last = run.events[-1]
    assert isinstance(last, TaskFailed)
    assert last.reason == "provider unavailable"


def test_only_content_director_can_transition_a_task() -> None:
    """TFL-03 / TINV-03: a non-Content-Director actor cannot change Task status."""
    run = make_run()
    task_id = open_task(run)
    with pytest.raises(UnauthorizedActorError):
        run.transition_task(task_id, TaskStatus.RUNNING, by=Actor.AGENT)
    assert run.task(task_id).status is TaskStatus.PENDING


def test_only_content_director_can_open_a_task() -> None:
    """TFL-04 / TINV-03: a non-Content-Director actor cannot open a Task."""
    run = make_run()
    with pytest.raises(UnauthorizedActorError):
        run.open_task(
            workflow_step_ref=STEP_REF,
            agent_ref=AGENT_REF,
            task_input=TASK_INPUT,
            by=Actor.AGENT,
        )
    assert len(run.tasks) == 0


# --- Invariants --------------------------------------------------------------------------


def test_task_exposes_exactly_one_status() -> None:
    """TINV-01: a Task has exactly one current status, replaced atomically on transition."""
    run = make_run()
    task_id = open_task(run)
    assert run.task(task_id).status is TaskStatus.PENDING
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    assert run.task(task_id).status is TaskStatus.RUNNING


def test_task_input_and_identity_are_stable_across_lifecycle() -> None:
    """TID-01 / TID-02 / TINV-02: identifier and fixed input survive every change unchanged."""
    run = make_run()
    task_id = open_task(run)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # retry
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    view = run.task(task_id)
    assert view.task_id == task_id
    assert view.run_id == RUN_ID
    assert view.workflow_step_ref == STEP_REF
    assert view.agent_ref == AGENT_REF
    assert view.task_input == TASK_INPUT


# --- Aggregate boundary & identity -------------------------------------------------------


def test_task_is_owned_by_its_run() -> None:
    """TAGG-01 / TINV-07: a Task opened through a Run is owned by exactly that Run."""
    run = make_run()
    task_id = open_task(run)
    assert run.task(task_id).run_id == run.run_id


def test_tasks_of_distinct_runs_are_isolated() -> None:
    """TAGG-02: Tasks opened in different Runs belong only to their own Run."""
    run_a = make_run()
    run_b = Run.create(
        run_id="run-0002",
        content_brief_ref=BRIEF_REF,
        workflow_version_ref=WORKFLOW_REF,
    )
    a_id = open_task(run_a)
    b_id = open_task(run_b)
    assert a_id != b_id
    assert [view.task_id for view in run_a.tasks] == [a_id]
    assert [view.task_id for view in run_b.tasks] == [b_id]
    assert run_a.task(a_id).run_id == run_a.run_id
    assert run_b.task(b_id).run_id == run_b.run_id


def test_task_view_is_a_point_in_time_snapshot() -> None:
    """TAGG-03: read access returns a snapshot, so a child changes only through the root."""
    run = make_run()
    task_id = open_task(run)
    snapshot_pending = run.task(task_id)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    snapshot_running = run.task(task_id)
    assert snapshot_pending.status is TaskStatus.PENDING
    assert snapshot_running.status is TaskStatus.RUNNING


def test_distinct_tasks_are_independent() -> None:
    """TID-03: opening two Tasks yields distinct ids and independent states."""
    run = make_run()
    first = open_task(run)
    second = open_task(run)
    assert first != second
    run.transition_task(first, TaskStatus.RUNNING, by=CD)
    assert run.task(first).status is TaskStatus.RUNNING
    assert run.task(second).status is TaskStatus.PENDING


# --- Events ------------------------------------------------------------------------------


def test_open_emits_task_created_event() -> None:
    """TEV-01: opening a Task emits exactly one TaskCreated carrying the fixed input."""
    run = make_run()
    task_id = open_task(run)
    created = [event for event in run.events if isinstance(event, TaskCreated)]
    assert len(created) == 1
    assert created[0].task_id == task_id
    assert created[0].run_id == RUN_ID
    assert created[0].workflow_step_ref == STEP_REF
    assert created[0].agent_ref == AGENT_REF


def test_task_started_is_emitted_once_and_not_on_retry() -> None:
    """TEV-02: TaskStarted is emitted on the first start only, never on a retry."""
    run = make_run()
    task_id = open_task(run, TaskRetryPolicy(max_attempts=3))
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # retry
    started = [event for event in run.events if isinstance(event, TaskStarted)]
    assert len(started) == 1


def test_succeeded_emits_task_completed() -> None:
    """TEV-03: reaching SUCCEEDED emits TaskCompleted."""
    run, task_id = task_in(TaskStatus.RUNNING)
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    assert isinstance(run.events[-1], TaskCompleted)


def test_task_events_are_recorded_in_the_run_log_in_order() -> None:
    """TEV-06 / TINV-08: Task events appear, in order, in the owning Run's single event log."""
    run = make_run()
    task_id = open_task(run)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    task_events: list[type[TaskEvent]] = [
        type(event) for event in run.events if isinstance(event, TaskEvent)
    ]
    assert task_events == [TaskCreated, TaskStarted, TaskCompleted]


# --- Cross-entity (Run <-> Task) ---------------------------------------------------------


def test_run_cannot_complete_with_a_non_terminal_task() -> None:
    """TXC-01: a non-terminal Task blocks the Run from reaching COMPLETED."""
    run = make_run()
    task_id = open_task(run)
    drive_run_to_waiting_human(run)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)  # non-terminal
    with pytest.raises(InvalidTransitionError):
        run.transition(RunStatus.COMPLETED, by=CD)
    assert run.status is RunStatus.WAITING_HUMAN


@pytest.mark.parametrize(
    "outcome",
    [(TaskStatus.RUNNING, TaskStatus.SUCCEEDED), (TaskStatus.SKIPPED,)],
)
def test_run_completes_when_all_tasks_are_terminal(outcome: tuple[TaskStatus, ...]) -> None:
    """TXC-02: terminal Tasks (Succeeded/Skipped) do not block COMPLETED."""
    run = make_run()
    task_id = open_task(run)
    for status in outcome:
        run.transition_task(task_id, status, by=CD)
    drive_run_to_waiting_human(run)
    run.transition(RunStatus.COMPLETED, by=CD)
    assert run.status is RunStatus.COMPLETED


# --- Regression smoke --------------------------------------------------------------------


def test_smoke_task_happy_path_succeeds() -> None:
    """Regression: open -> run -> succeed reaches SUCCEEDED."""
    run = make_run()
    task_id = open_task(run)
    run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=CD)
    assert run.task(task_id).status is TaskStatus.SUCCEEDED


def test_smoke_terminal_task_is_final() -> None:
    """Regression: a terminal Task rejects further transitions."""
    run, task_id = task_in(TaskStatus.SUCCEEDED)
    with pytest.raises(InvalidTaskTransitionError):
        run.transition_task(task_id, TaskStatus.RUNNING, by=CD)
