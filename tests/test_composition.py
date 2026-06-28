"""Tests for the Composition Root (build-time graph compiler).

Verify: deterministic construction of agent_ref -> executor, Prompt injection at construction,
build-time consistency validation, no execution/model-call at build time, and that the assembled
ContentDirector runs the executors at runtime.
"""

from __future__ import annotations

import pytest

from omemo_content_factory.composition import (
    CompositionError,
    build_content_director,
    build_executor_map,
    build_schema_map,
    compile_runtime,
    validate_workflow_executors,
)
from omemo_content_factory.domain.agent import Agent
from omemo_content_factory.domain.prompt import Prompt, PromptVersion
from omemo_content_factory.domain.run import Run, RunStatus
from omemo_content_factory.domain.schema import Schema, SchemaVersion
from omemo_content_factory.domain.task import TaskStatus
from omemo_content_factory.domain.workflow import Workflow, WorkflowStep
from omemo_content_factory.infrastructure.llm import LLMTaskExecutor


class _FakeClient:
    """Records calls so we can assert the model is not invoked at build time."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, system: str, user: str) -> str:
        self.calls += 1
        return f"out:{user}"


def _prompt(prompt_id: str = "p1", version: int = 1) -> Prompt:
    return Prompt(
        prompt_id=prompt_id,
        version=PromptVersion(version),
        system=f"system-{prompt_id}",
        user_template="Brief: {input}",
        schema_ref=f"{prompt_id}@{version}",
    )


def _agent(agent_id: str = "researcher@v1", prompt_ref: str = "p1") -> Agent:
    return Agent(agent_id=agent_id, name=agent_id, prompt_ref=prompt_ref)


# --- construction & injection ------------------------------------------------------------


def test_build_maps_agent_ref_to_executor_with_injected_prompt() -> None:
    client = _FakeClient()
    executors = build_executor_map([_agent()], {"p1": _prompt()}, client)
    assert set(executors) == {"researcher@v1"}
    executor = executors["researcher@v1"]
    assert isinstance(executor, LLMTaskExecutor)
    assert executor.system_prompt == "system-p1"  # Prompt.system injected at construction
    assert executor.schema_ref == "p1@1"  # Prompt.schema_ref injected at construction


def test_build_does_not_execute_or_call_model() -> None:
    client = _FakeClient()
    build_executor_map([_agent()], {"p1": _prompt()}, client)
    assert client.calls == 0  # no execution / no runtime simulation at build time


def test_build_is_deterministic() -> None:
    client = _FakeClient()
    agents, prompts = [_agent()], {"p1": _prompt()}
    first = build_executor_map(agents, prompts, client)
    second = build_executor_map(agents, prompts, client)
    assert first == second


# --- build-time consistency validation ---------------------------------------------------


def test_unknown_prompt_ref_raises_build_time() -> None:
    with pytest.raises(CompositionError):
        build_executor_map([_agent(prompt_ref="missing")], {"p1": _prompt()}, _FakeClient())


def test_duplicate_agent_ref_raises_build_time() -> None:
    with pytest.raises(CompositionError):
        build_executor_map([_agent(), _agent()], {"p1": _prompt()}, _FakeClient())


# --- assembled ContentDirector runs at runtime -------------------------------------------


def test_content_director_runs_assembled_executors() -> None:
    client = _FakeClient()
    director = build_content_director([_agent()], {"p1": _prompt()}, client)
    run = Run.create(run_id="run-1", content_brief_ref="b", workflow_version_ref="wf@1")
    workflow = Workflow.create(
        workflow_id="wf",
        name="wf",
        steps=[
            WorkflowStep(step_id="s1", task_type="t", agent_ref="researcher@v1", schema_ref="p1@1")
        ],
    )

    director.execute_workflow(run, workflow, brief="brief")

    assert run.status is RunStatus.COMPLETED
    assert [v.status for v in run.tasks] == [TaskStatus.SUCCEEDED]
    assert client.calls == 1  # executor used at runtime, not at build time


# --- build-time graph integrity: Workflow.agent_ref must be in the executor map (F2) -----


def _workflow(*agent_refs: str) -> Workflow:
    return Workflow.create(
        workflow_id="wf",
        name="wf",
        steps=[
            WorkflowStep(step_id=f"s{i}", task_type="t", agent_ref=ref, schema_ref="x@1")
            for i, ref in enumerate(agent_refs)
        ],
    )


def test_validate_workflow_unknown_agent_ref_raises_build_time() -> None:
    executors = build_executor_map([_agent()], {"p1": _prompt()}, _FakeClient())
    with pytest.raises(CompositionError):
        validate_workflow_executors(_workflow("researcher@v1", "ghost@v1"), executors)


def test_validate_workflow_passes_for_known_refs() -> None:
    executors = build_executor_map([_agent()], {"p1": _prompt()}, _FakeClient())
    validate_workflow_executors(_workflow("researcher@v1"), executors)  # no raise


def test_compile_runtime_rejects_unknown_agent_ref_before_run() -> None:
    with pytest.raises(CompositionError):
        compile_runtime([_agent()], {"p1": _prompt()}, _FakeClient(), _workflow("ghost@v1"))


def test_compile_runtime_runs_valid_workflow_without_runtime_keyerror() -> None:
    client = _FakeClient()
    workflow = _workflow("researcher@v1")
    director = compile_runtime([_agent()], {"p1": _prompt()}, client, workflow)
    run = Run.create(run_id="r", content_brief_ref="b", workflow_version_ref="wf@1")
    director.execute_workflow(run, workflow, brief="brief")
    assert run.status is RunStatus.COMPLETED
    assert client.calls == 1


# --- 3A: Schema resolution map (build-time, structural only) ------------------------------


def _schema(schema_id: str = "p1") -> Schema:
    return Schema.create(
        schema_id=schema_id, version=SchemaVersion(1), description="d", required_fields=["facts"]
    )


def test_build_schema_map_resolves_agent_ref_to_schema() -> None:
    schema = _schema()
    # _prompt().schema_ref == "p1@1"
    result = build_schema_map([_agent()], {"p1": _prompt()}, {"p1@1": schema})
    assert result == {"researcher@v1": schema}


def test_build_schema_map_unknown_schema_ref_raises_build_time() -> None:
    with pytest.raises(CompositionError):
        build_schema_map([_agent()], {"p1": _prompt()}, {})


def test_build_schema_map_unknown_prompt_ref_raises_build_time() -> None:
    with pytest.raises(CompositionError):
        build_schema_map([_agent(prompt_ref="missing")], {"p1": _prompt()}, {"p1@1": _schema()})


def test_build_schema_map_duplicate_agent_ref_raises_build_time() -> None:
    with pytest.raises(CompositionError):
        build_schema_map([_agent(), _agent()], {"p1": _prompt()}, {"p1@1": _schema()})
