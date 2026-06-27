"""Additive wiring — the VALIDATED Output path layered beside the untouched legacy path.

Application layer only. It resolves the ACTIVE Schema for a ref, runs the pure
``Schema.validate``, and records the Task's Output through the **existing** ``Run.record_output``
**only when the result is valid**. Nothing in the domain (Run, Output, Schema), nor
``TaskExecutor``/``ExecutionResult``/``ContentDirector``, is changed.

Schema stays a pure validator here: it does not know Run, Output or the Content Director — this
module calls it, not the other way round.

Note on the gate: ``Run.record_output`` fixes a ``VALID`` Output and takes no status (the Run
contract is unchanged). So an **invalid** result is *gated out* — not recorded — rather than
recorded as an ``INVALID`` Output. Recording an ``INVALID`` Output would change the Run contract
and is out of scope for this wiring.
"""

from __future__ import annotations

from collections.abc import Mapping

from omemo_content_factory.application.schema_observability import (
    ValidationObserver,
    record_validation,
)
from omemo_content_factory.domain.output import OutputId
from omemo_content_factory.domain.run import Actor, Run
from omemo_content_factory.domain.schema import Schema
from omemo_content_factory.domain.task import TaskId


def resolve_active_schema(schemas: Mapping[str, Schema], schema_ref: str) -> Schema:
    """Resolution layer (local, minimal): pick the Schema registered for ``schema_ref``.

    ``schemas`` is an injected, explicit registry (no global state, PROJECT.md §6). ACTIVE-ness is
    enforced downstream by ``Schema.validate`` (``SchemaNotActiveError``); this layer only maps a
    ref to its Schema.
    """
    return schemas[schema_ref]


def validate_and_record_output(
    run: Run,
    task_id: TaskId,
    *,
    schema: Schema,
    payload_fields: Mapping[str, str],
    payload: str,
    schema_ref: str,
    by: Actor = Actor.CONTENT_DIRECTOR,
    observer: ValidationObserver | None = None,
) -> OutputId | None:
    """VALIDATED path (add-on): validate, then record only when valid.

    Calls the pure ``schema.validate`` (the single place Schema is invoked). On a valid verdict it
    records the Output through the **existing** ``Run.record_output`` and returns its id; on an
    invalid verdict nothing is recorded (the result is gated out) and ``None`` is returned. The
    owning Task must already be ``SUCCEEDED`` (precondition of ``Run.record_output``), exactly as on
    the legacy path. Run, Output and the legacy path are untouched.

    The optional ``observer`` receives a log-only trace of the decision (VALID/INVALID); it never
    affects the outcome (best-effort dispatch). With no observer the behaviour is unchanged.
    """
    verdict = schema.validate(payload_fields)
    record_validation(observer, schema, verdict, payload_fields)
    if not verdict.is_valid:
        return None
    return run.record_output(task_id, payload=payload, schema_ref=schema_ref, by=by)
