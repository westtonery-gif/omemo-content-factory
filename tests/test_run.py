"""Behavioural tests for the Run aggregate (``omemo_content_factory.domain.run``).

Every test exercises a single business rule of the Run aggregate and references the
corresponding `RUN_ACCEPTANCE.md` scenario(s) in its docstring. Tests drive the aggregate
only through its public contract (``create`` / ``transition`` / read-only properties / events
/ errors). No Enum/dataclass/Protocol/stdlib behaviour is tested; no mocks, monkeypatch,
sleep or randomness are used.

The expected transition table is encoded here from RUN_SPEC.md §4 (the source of truth),
independently of the implementation's private tables.
"""

from __future__ import annotations

import pytest

from omemo_content_factory.domain.run import (
    Actor,
    ImmutableAttributeError,
    InvalidTransitionError,
    ReworkLimitExceededError,
    ReworkPolicy,
    Run,
    RunCompleted,
    RunCreated,
    RunEvent,
    RunFailed,
    RunQueued,
    RunStarted,
    RunStatus,
    UnauthorizedActorError,
)

RUN_ID = "run-0001"
BRIEF_REF = "brief-0001"
WORKFLOW_REF = "workflow@v1"
CONTENT_DIRECTOR = Actor.CONTENT_DIRECTOR

# Canonical happy-path sub-paths (sequences of transitions driven by the Content Director).
_TO_WAITING_QA: tuple[RunStatus, ...] = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_QA)
_TO_WAITING_HUMAN: tuple[RunStatus, ...] = (*_TO_WAITING_QA, RunStatus.WAITING_HUMAN)
_TO_COMPLETED: tuple[RunStatus, ...] = (*_TO_WAITING_HUMAN, RunStatus.COMPLETED)

# Shortest path that drives a fresh Run into each state (for preconditions).
_PATH_TO: dict[RunStatus, tuple[RunStatus, ...]] = {
    RunStatus.CREATED: (),
    RunStatus.QUEUED: (RunStatus.QUEUED,),
    RunStatus.RUNNING: (RunStatus.QUEUED, RunStatus.RUNNING),
    RunStatus.WAITING_QA: _TO_WAITING_QA,
    RunStatus.WAITING_HUMAN: _TO_WAITING_HUMAN,
    RunStatus.COMPLETED: _TO_COMPLETED,
    RunStatus.FAILED: (RunStatus.FAILED,),
}

# Allowed transitions per RUN_SPEC.md §4 — the test suite's own expectation.
_ALLOWED_BY_SPEC: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.QUEUED, RunStatus.FAILED},
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.WAITING_QA, RunStatus.FAILED},
    RunStatus.WAITING_QA: {RunStatus.WAITING_HUMAN, RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.WAITING_HUMAN: {RunStatus.COMPLETED, RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
}

_FORBIDDEN_TRANSITIONS: list[tuple[RunStatus, RunStatus]] = [
    (source, target)
    for source in RunStatus
    for target in RunStatus
    if target not in _ALLOWED_BY_SPEC[source]
]

_NON_TERMINAL_STATES: list[RunStatus] = [
    RunStatus.CREATED,
    RunStatus.QUEUED,
    RunStatus.RUNNING,
    RunStatus.WAITING_QA,
    RunStatus.WAITING_HUMAN,
]


def make_run(rework_policy: ReworkPolicy | None = None) -> Run:
    """Create a fresh Run from the standard sample input."""
    return Run.create(
        run_id=RUN_ID,
        content_brief_ref=BRIEF_REF,
        workflow_version_ref=WORKFLOW_REF,
        rework_policy=rework_policy,
    )


def drive(run: Run, *statuses: RunStatus) -> None:
    """Apply a sequence of Content-Director transitions to ``run``."""
    for status in statuses:
        run.transition(status, by=CONTENT_DIRECTOR)


def run_in(state: RunStatus) -> Run:
    """Return a fresh Run driven to ``state`` along the canonical path."""
    run = make_run()
    drive(run, *_PATH_TO[state])
    return run


@pytest.fixture
def run() -> Run:
    """A fresh Run in ``CREATED``."""
    return make_run()


# --- Happy path --------------------------------------------------------------------------


def test_create_starts_in_created_status(run: Run) -> None:
    """HP-01: a newly created Run begins in CREATED."""
    assert run.status is RunStatus.CREATED


def test_full_successful_lifecycle_reaches_completed(run: Run) -> None:
    """HP-01: create -> queue -> run -> QA -> human -> approve reaches COMPLETED."""
    drive(run, *_TO_COMPLETED)
    assert run.status is RunStatus.COMPLETED


# --- Rework ------------------------------------------------------------------------------


def test_qa_risk_returns_to_running_and_increments_rework(run: Run) -> None:
    """RW-01: a QA return to RUNNING counts as one rework iteration."""
    drive(run, *_TO_WAITING_QA)
    run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)
    assert run.status is RunStatus.RUNNING
    assert run.rework_count == 1


def test_human_review_return_to_running_increments_rework(run: Run) -> None:
    """RW-02 / RW-03: a return to RUNNING after the human gate counts as a rework.

    At the Run level Reject and Request-changes are the same edge; their distinction
    (reason / guidance) belongs to the Human Review entity, which is not yet implemented.
    """
    drive(run, *_TO_WAITING_HUMAN)
    run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)
    assert run.status is RunStatus.RUNNING
    assert run.rework_count == 1


def test_run_completes_after_a_rework(run: Run) -> None:
    """RW-01: after a rework the Run can still complete normally."""
    drive(run, *_TO_WAITING_QA)
    run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)
    drive(run, RunStatus.WAITING_QA, RunStatus.WAITING_HUMAN, RunStatus.COMPLETED)
    assert run.status is RunStatus.COMPLETED
    assert run.rework_count == 1


def test_rework_beyond_policy_limit_is_rejected() -> None:
    """RW-04 / INV-08: a rework that would exceed the policy bound is rejected."""
    run = make_run(ReworkPolicy(max_rework_iterations=1))
    drive(run, *_TO_WAITING_QA)
    run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)  # rework 1 — allowed
    assert run.rework_count == 1
    run.transition(RunStatus.WAITING_QA, by=CONTENT_DIRECTOR)
    with pytest.raises(ReworkLimitExceededError):
        run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)  # rework 2 — exceeds
    assert run.status is RunStatus.WAITING_QA
    assert run.rework_count == 1


# --- Forbidden transitions & failures ----------------------------------------------------


@pytest.mark.parametrize(("source", "target"), _FORBIDDEN_TRANSITIONS)
def test_disallowed_transitions_are_rejected(source: RunStatus, target: RunStatus) -> None:
    """INV-04 / INV-05 / FL-01 / FL-03 / FL-04 / FL-09 / FL-10: only spec edges are allowed.

    Covers forbidden edges, state skips and any transition out of a terminal state.
    """
    aggregate = run_in(source)
    with pytest.raises(InvalidTransitionError):
        aggregate.transition(target, by=CONTENT_DIRECTOR)


def test_only_content_director_can_change_status(run: Run) -> None:
    """FL-08 / INV-03: a non-Content-Director actor cannot change status."""
    with pytest.raises(UnauthorizedActorError):
        run.transition(RunStatus.QUEUED, by=Actor.AGENT)
    assert run.status is RunStatus.CREATED


@pytest.mark.parametrize("attribute", ["run_id", "content_brief_ref", "workflow_version_ref"])
def test_immutable_input_cannot_be_reassigned(run: Run, attribute: str) -> None:
    """FL-05 / FL-06 / FL-07 / INV-02 / ID-01 / ID-02: input fields are immutable."""
    with pytest.raises(ImmutableAttributeError):
        setattr(run, attribute, "changed")


def test_failure_records_its_reason(run: Run) -> None:
    """FL-12: reaching FAILED records the supplied reason."""
    run.transition(RunStatus.FAILED, by=CONTENT_DIRECTOR, reason="provider unavailable")
    assert run.status is RunStatus.FAILED
    assert run.failure_reason == "provider unavailable"


# --- Invariants --------------------------------------------------------------------------


def test_run_exposes_exactly_one_status(run: Run) -> None:
    """INV-01 / FL-11: a Run has exactly one current status, replaced atomically on transition."""
    before = run.status
    run.transition(RunStatus.QUEUED, by=CONTENT_DIRECTOR)
    after = run.status
    assert before is RunStatus.CREATED
    assert after is RunStatus.QUEUED


@pytest.mark.parametrize("source", _NON_TERMINAL_STATES)
def test_failure_is_reachable_from_every_non_terminal_state(source: RunStatus) -> None:
    """INV-05: a Run can always reach a terminal state (FAILED) from any non-terminal state."""
    aggregate = run_in(source)
    aggregate.transition(RunStatus.FAILED, by=CONTENT_DIRECTOR, reason="aborted")
    assert aggregate.status is RunStatus.FAILED


def test_completion_requires_human_approval(run: Run) -> None:
    """INV-06 / HP-02 / FL-02: COMPLETED is reachable only from WAITING_HUMAN (Approve)."""
    drive(run, *_TO_WAITING_QA)
    with pytest.raises(InvalidTransitionError):
        run.transition(RunStatus.COMPLETED, by=CONTENT_DIRECTOR)  # not yet at the human gate
    drive(run, RunStatus.WAITING_HUMAN)
    run.transition(RunStatus.COMPLETED, by=CONTENT_DIRECTOR)  # approve
    assert run.status is RunStatus.COMPLETED


def test_event_history_is_append_only(run: Run) -> None:
    """INV-09: the Run's event log only grows; earlier events are never removed or changed."""
    drive(run, RunStatus.QUEUED)
    before = list(run.events)
    drive(run, RunStatus.RUNNING)
    after = list(run.events)
    assert after[: len(before)] == before
    assert len(after) > len(before)


def test_aggregate_integrity_with_children() -> None:
    """INV-07: children belong to exactly one Run and change only through it."""
    pytest.skip(
        "Requires child entities (Task/Artifact/Evaluation/Human Review/Analytics Record), "
        "not yet implemented (ADR-0003 §9)."
    )


# --- Identity ----------------------------------------------------------------------------


def test_identity_is_stable_across_lifecycle(run: Run) -> None:
    """ID-01 / ID-02 / ID-03: identifier and input survive every state change unchanged."""
    drive(run, *_TO_COMPLETED)
    assert run.run_id == RUN_ID
    assert run.content_brief_ref == BRIEF_REF
    assert run.workflow_version_ref == WORKFLOW_REF


def test_distinct_runs_are_independent() -> None:
    """ID-04: a new business object yields a new, independent Run."""
    first = make_run()
    second = Run.create(
        run_id="run-0002",
        content_brief_ref=BRIEF_REF,
        workflow_version_ref=WORKFLOW_REF,
    )
    drive(first, RunStatus.QUEUED)
    assert first is not second
    assert first.status is RunStatus.QUEUED
    assert second.status is RunStatus.CREATED


# --- Events ------------------------------------------------------------------------------


def test_happy_path_emits_events_in_order(run: Run) -> None:
    """EV-01 / EV-02 / EV-03 / EV-04 (HP-01): the happy path emits events in order."""
    drive(run, *_TO_COMPLETED)
    expected: list[type[RunEvent]] = [RunCreated, RunQueued, RunStarted, RunCompleted]
    assert [type(event) for event in run.events] == expected


def test_failure_emits_run_failed_event(run: Run) -> None:
    """EV-05: reaching FAILED emits RunFailed carrying the reason."""
    run.transition(RunStatus.FAILED, by=CONTENT_DIRECTOR, reason="boom")
    last = run.events[-1]
    assert isinstance(last, RunFailed)
    assert last.reason == "boom"


def test_rework_reentry_does_not_emit_run_started(run: Run) -> None:
    """EV-03: re-entering RUNNING via rework emits no RunStarted (no new event at all)."""
    drive(run, *_TO_WAITING_QA)
    before = list(run.events)
    run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)
    assert list(run.events) == before


# --- Regression smoke --------------------------------------------------------------------


def test_smoke_happy_path_completes() -> None:
    """Regression: the core happy path reaches COMPLETED."""
    run = make_run()
    drive(run, *_TO_COMPLETED)
    assert run.status is RunStatus.COMPLETED


def test_smoke_terminal_state_is_final() -> None:
    """Regression: a terminal Run rejects further transitions."""
    run = make_run()
    drive(run, *_TO_COMPLETED)
    with pytest.raises(InvalidTransitionError):
        run.transition(RunStatus.RUNNING, by=CONTENT_DIRECTOR)


def test_smoke_input_is_immutable() -> None:
    """Regression: immutable input cannot be reassigned."""
    run = make_run()
    with pytest.raises(ImmutableAttributeError):
        run.run_id = "changed"  # type: ignore[misc]  # read-only: assignment must raise
