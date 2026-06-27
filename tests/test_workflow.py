"""Behavioural tests for Workflow / Workflow Step and the Content Director expansion.

Maps WORKFLOW_ACCEPTANCE.md scenarios to tests. Only the public contract is exercised:
``Workflow.create`` / construction validation, immutability, and ``ContentDirector.expand`` /
``execute_workflow`` (strict list-order, ``depends_on`` inert, execution core unchanged).
"""

from __future__ import annotations

import dataclasses

import pytest

from omemo_content_factory.application.content_director import ContentDirector, TaskRequest
from omemo_content_factory.application.task_execution import ExecutionResult
from omemo_content_factory.domain.run import Run, RunStatus
from omemo_content_factory.domain.task import TaskStatus
from omemo_content_factory.domain.workflow import (
    DuplicateStepIdError,
    EmptyWorkflowError,
    UnknownDependencyError,
    Workflow,
    WorkflowStep,
)


def _step(
    step_id: str, *, agent_ref: str = "a@v1", depends_on: tuple[str, ...] = ()
) -> WorkflowStep:
    return WorkflowStep(
        step_id=step_id,
        task_type="t",
        agent_ref=agent_ref,
        schema_ref="s@1",
        depends_on=depends_on,
    )


class _FakeExecutor:
    """Deterministic executor: succeeds and yields output + a schema_ref (drives the real path)."""

    def execute(self, task_input: str) -> ExecutionResult:
        return ExecutionResult(succeeded=True, output=f"out:{task_input}", schema_ref="s@1")


def _run() -> Run:
    return Run.create(run_id="run-1", content_brief_ref="brief-1", workflow_version_ref="wf@v1")


# --- 2. Construction (WHP) ---------------------------------------------------------------


def test_whp_01_valid_construction_preserves_order() -> None:
    wf = Workflow.create(
        workflow_id="article",
        name="article pipeline",
        steps=[_step("research"), _step("write"), _step("edit")],
    )
    assert [s.step_id for s in wf.steps] == ["research", "write", "edit"]
    assert wf.steps[0].agent_ref == "a@v1"


# --- 3. Ordering + 5. Content Director resolution (WORD / WCD) ----------------------------


def test_word_01_expand_is_strict_list_order() -> None:
    wf = Workflow.create(
        workflow_id="w",
        name="w",
        steps=[_step("A", agent_ref="ra"), _step("B", agent_ref="rb"), _step("C", agent_ref="rc")],
    )
    requests = ContentDirector.expand(wf, brief="brief")
    assert [r.workflow_step_ref for r in requests] == ["A", "B", "C"]
    assert [r.agent_ref for r in requests] == ["ra", "rb", "rc"]
    assert requests[0].task_input == "brief"
    assert requests[1].task_input == "" and requests[2].task_input == ""


def test_word_02_depends_on_does_not_change_order() -> None:
    # B declares a (forward) dependency on C; order must still be the list order A, B, C.
    wf = Workflow.create(
        workflow_id="w",
        name="w",
        steps=[_step("A"), _step("B", depends_on=("C",)), _step("C")],
    )
    assert [r.workflow_step_ref for r in ContentDirector.expand(wf, brief="b")] == ["A", "B", "C"]


def test_wcd_03_execute_workflow_runs_through_existing_core_in_order() -> None:
    run = _run()
    executors = {"ra": _FakeExecutor(), "rb": _FakeExecutor(), "rc": _FakeExecutor()}
    director = ContentDirector(executors)
    wf = Workflow.create(
        workflow_id="w",
        name="w",
        steps=[_step("A", agent_ref="ra"), _step("B", agent_ref="rb"), _step("C", agent_ref="rc")],
    )

    director.execute_workflow(run, wf, brief="brief")

    assert [v.workflow_step_ref for v in run.tasks] == ["A", "B", "C"]
    assert all(v.status is TaskStatus.SUCCEEDED for v in run.tasks)
    assert run.status is RunStatus.COMPLETED


def test_wcd_equivalent_to_direct_execute() -> None:
    # execute_workflow == execute over the expanded TaskRequests (execution core unchanged).
    wf = Workflow.create(
        workflow_id="w", name="w", steps=[_step("A", agent_ref="ra"), _step("B", agent_ref="rb")]
    )
    direct_run, wf_run = _run(), _run()
    ContentDirector({"ra": _FakeExecutor(), "rb": _FakeExecutor()}).execute(
        direct_run,
        [TaskRequest("A", "ra", "brief"), TaskRequest("B", "rb", "")],
    )
    ContentDirector({"ra": _FakeExecutor(), "rb": _FakeExecutor()}).execute_workflow(
        wf_run, wf, brief="brief"
    )
    assert [v.workflow_step_ref for v in wf_run.tasks] == [
        v.workflow_step_ref for v in direct_run.tasks
    ]
    assert wf_run.status is direct_run.status


# --- 4. depends_on edge cases (WDEP) -----------------------------------------------------


def test_wdep_01_empty_depends_on_is_valid() -> None:
    wf = Workflow.create(workflow_id="w", name="w", steps=[_step("A"), _step("B")])
    assert all(s.depends_on == () for s in wf.steps)


def test_wdep_02_03_backward_and_forward_references_are_valid_and_inert() -> None:
    backward = Workflow.create(
        workflow_id="w", name="w", steps=[_step("A"), _step("B", depends_on=("A",))]
    )
    forward = Workflow.create(
        workflow_id="w", name="w", steps=[_step("A", depends_on=("B",)), _step("B")]
    )
    assert [s.step_id for s in backward.steps] == ["A", "B"]
    assert [s.step_id for s in forward.steps] == ["A", "B"]


def test_wdep_04_self_and_cyclic_references_are_accepted_not_detected() -> None:
    # ADR-0009 §5: only referential integrity is checked; cycles/self-refs are valid and inert.
    self_ref = Workflow.create(workflow_id="w", name="w", steps=[_step("A", depends_on=("A",))])
    cyclic = Workflow.create(
        workflow_id="w",
        name="w",
        steps=[_step("A", depends_on=("B",)), _step("B", depends_on=("A",))],
    )
    assert self_ref.steps[0].depends_on == ("A",)
    assert [s.step_id for s in cyclic.steps] == ["A", "B"]


# --- 6. Invalid workflow detection (WFL) -------------------------------------------------


def test_wfl_01_empty_workflow_rejected() -> None:
    with pytest.raises(EmptyWorkflowError):
        Workflow.create(workflow_id="w", name="w", steps=[])


def test_wfl_02_duplicate_step_id_rejected() -> None:
    with pytest.raises(DuplicateStepIdError):
        Workflow.create(workflow_id="w", name="w", steps=[_step("A"), _step("A")])


def test_wfl_03_dangling_dependency_rejected() -> None:
    with pytest.raises(UnknownDependencyError):
        Workflow.create(
            workflow_id="w", name="w", steps=[_step("A"), _step("B", depends_on=("X",))]
        )


# --- 7. Invariants (WINV) ----------------------------------------------------------------


def test_winv_01_workflow_and_step_are_immutable() -> None:
    wf = Workflow.create(workflow_id="w", name="w", steps=[_step("A")])
    with pytest.raises(dataclasses.FrozenInstanceError):
        wf.name = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        wf.steps[0].step_id = "y"  # type: ignore[misc]
