"""Tests for the additive VALIDATED Output wiring (application/schema_validation.py).

Exercises both outcomes through the real domain, without touching the legacy path: a valid result
is recorded via the existing ``Run.record_output``; an invalid result is gated out (not recorded).
"""

from __future__ import annotations

import pytest

from omemo_content_factory.application.schema_validation import (
    resolve_active_schema,
    validate_and_record_output,
)
from omemo_content_factory.domain.output import OutputStatus
from omemo_content_factory.domain.run import Actor, Run
from omemo_content_factory.domain.schema import (
    Schema,
    SchemaNotActiveError,
    SchemaStatus,
    SchemaVersion,
)
from omemo_content_factory.domain.task import TaskId, TaskStatus

_CD = Actor.CONTENT_DIRECTOR


def _succeeded_task(run: Run) -> TaskId:
    task_id = run.open_task(
        workflow_step_ref="research",
        agent_ref="researcher@v1",
        task_input="brief",
        by=_CD,
    )
    run.transition_task(task_id, TaskStatus.RUNNING, by=_CD)
    run.transition_task(task_id, TaskStatus.SUCCEEDED, by=_CD)
    return task_id


def _run() -> Run:
    return Run.create(
        run_id="run-1",
        content_brief_ref="brief-1",
        workflow_version_ref="wf@v1",
    )


def _active_schema() -> Schema:
    schema = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(1),
        description="research notes contract",
        required_fields=["facts", "structure"],
    )
    schema.transition(SchemaStatus.ACTIVE)
    return schema


def test_valid_result_is_recorded_via_existing_record_output() -> None:
    run = _run()
    task_id = _succeeded_task(run)
    schema = _active_schema()

    output_id = validate_and_record_output(
        run,
        task_id,
        schema=schema,
        payload_fields={"facts": "a", "structure": "b"},
        payload="the produced content",
        schema_ref="research-notes@1",
    )

    assert output_id is not None
    output = run.task(task_id).output
    assert output is not None
    assert output.status is OutputStatus.VALID
    assert output.schema_ref == "research-notes@1"
    assert output.payload == "the produced content"


def test_invalid_result_is_gated_out_not_recorded() -> None:
    run = _run()
    task_id = _succeeded_task(run)
    schema = _active_schema()

    output_id = validate_and_record_output(
        run,
        task_id,
        schema=schema,
        payload_fields={"facts": "a"},  # missing "structure"
        payload="the produced content",
        schema_ref="research-notes@1",
    )

    assert output_id is None
    assert run.task(task_id).output is None


def test_resolve_active_schema_maps_ref_to_schema() -> None:
    schema = _active_schema()
    registry = {"research-notes@1": schema}
    assert resolve_active_schema(registry, "research-notes@1") is schema


def test_validation_against_non_active_schema_raises() -> None:
    run = _run()
    task_id = _succeeded_task(run)
    draft = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(1),
        description="research notes contract",
        required_fields=["facts"],
    )
    with pytest.raises(SchemaNotActiveError):
        validate_and_record_output(
            run,
            task_id,
            schema=draft,
            payload_fields={"facts": "a"},
            payload="x",
            schema_ref="research-notes@1",
        )
    assert run.task(task_id).output is None
