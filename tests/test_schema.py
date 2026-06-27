"""Behavioural tests for the Schema aggregate root (SCHEMA_ACCEPTANCE.md, ADR-0008).

One scenario -> one (or a few) tests. Only the public contract of Schema is exercised:
``create`` / ``view`` / ``transition`` / ``validate``.
"""

from __future__ import annotations

import pytest

from omemo_content_factory.domain.schema import (
    ImmutableSchemaAttributeError,
    InvalidSchemaTransitionError,
    Schema,
    SchemaNotActiveError,
    SchemaStatus,
    SchemaValidation,
    SchemaVersion,
)


def _make(status: SchemaStatus = SchemaStatus.DRAFT) -> Schema:
    schema = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(1),
        description="research notes contract",
        required_fields=["facts", "structure"],
    )
    if status is SchemaStatus.ACTIVE:
        schema.transition(SchemaStatus.ACTIVE)
    elif status is SchemaStatus.DEPRECATED:
        schema.transition(SchemaStatus.ACTIVE)
        schema.transition(SchemaStatus.DEPRECATED)
    return schema


# --- 2. Lifecycle (SHP) ------------------------------------------------------------------


def test_shp_01_create_in_draft() -> None:
    schema = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(1),
        description="research notes contract",
        required_fields=["facts", "structure"],
    )
    view = schema.view
    assert view.schema_id == "research-notes"
    assert view.version == SchemaVersion(1)
    assert view.description == "research notes contract"
    assert view.required_fields == ("facts", "structure")
    assert view.status is SchemaStatus.DRAFT


def test_shp_02_draft_to_active() -> None:
    schema = _make(SchemaStatus.DRAFT)
    schema.transition(SchemaStatus.ACTIVE)
    assert schema.view.status is SchemaStatus.ACTIVE


def test_shp_03_active_to_deprecated() -> None:
    schema = _make(SchemaStatus.ACTIVE)
    schema.transition(SchemaStatus.DEPRECATED)
    assert schema.view.status is SchemaStatus.DEPRECATED


# --- 3. Forbidden transitions (SFL) ------------------------------------------------------


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (SchemaStatus.DRAFT, SchemaStatus.DRAFT),
        (SchemaStatus.DRAFT, SchemaStatus.DEPRECATED),
        (SchemaStatus.ACTIVE, SchemaStatus.DRAFT),
        (SchemaStatus.ACTIVE, SchemaStatus.ACTIVE),
        (SchemaStatus.DEPRECATED, SchemaStatus.DRAFT),
        (SchemaStatus.DEPRECATED, SchemaStatus.ACTIVE),
        (SchemaStatus.DEPRECATED, SchemaStatus.DEPRECATED),
    ],
)
def test_sfl_01_forbidden_transitions_rejected(frm: SchemaStatus, to: SchemaStatus) -> None:
    schema = _make(frm)
    with pytest.raises(InvalidSchemaTransitionError):
        schema.transition(to)
    assert schema.view.status is frm


# --- 4. Identity & versioning (SID) ------------------------------------------------------


def test_sid_01_schema_id_stable_through_lifecycle() -> None:
    schema = _make(SchemaStatus.DRAFT)
    schema.transition(SchemaStatus.ACTIVE)
    schema.transition(SchemaStatus.DEPRECATED)
    assert schema.view.schema_id == "research-notes"


def test_sid_02_version_compared_by_value() -> None:
    assert SchemaVersion(3) == SchemaVersion(3)
    assert SchemaVersion(3) != SchemaVersion(4)


def test_sid_03_new_revision_is_new_version_first_unchanged() -> None:
    v1 = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(1),
        description="v1 contract",
        required_fields=["facts"],
    )
    before = v1.view
    v2 = Schema.create(
        schema_id="research-notes",
        version=SchemaVersion(2),
        description="v2 contract",
        required_fields=["facts", "sources"],
    )
    assert v1.view.schema_id == v2.view.schema_id
    assert v1.view.version != v2.view.version
    assert v1.view == before


# --- 5. Validation (SVAL) ----------------------------------------------------------------


def test_sval_01_valid_result() -> None:
    schema = _make(SchemaStatus.ACTIVE)
    verdict = schema.validate({"facts": "a", "structure": "b"})
    assert verdict == SchemaValidation(is_valid=True, missing_fields=())


def test_sval_02_invalid_result_missing_or_empty() -> None:
    schema = _make(SchemaStatus.ACTIVE)
    verdict = schema.validate({"facts": "a", "structure": ""})
    assert verdict.is_valid is False
    assert verdict.missing_fields == ("structure",)
    assert schema.validate({"facts": "a"}).missing_fields == ("structure",)


def test_sval_03_determinism() -> None:
    schema = _make(SchemaStatus.ACTIVE)
    payload = {"facts": "a", "structure": "b"}
    assert schema.validate(payload) == schema.validate(payload)


def test_sval_04_repeatable_without_side_effect() -> None:
    schema = _make(SchemaStatus.ACTIVE)
    before = schema.view
    schema.validate({"facts": "a"})
    schema.validate({"facts": "a"})
    assert schema.view == before


def test_sval_05_validation_only_against_active() -> None:
    with pytest.raises(SchemaNotActiveError):
        _make(SchemaStatus.DRAFT).validate({"facts": "a", "structure": "b"})
    with pytest.raises(SchemaNotActiveError):
        _make(SchemaStatus.DEPRECATED).validate({"facts": "a", "structure": "b"})


# --- 6. Invariant (SINV) -----------------------------------------------------------------


def test_sinv_01_version_content_immutable_through_lifecycle() -> None:
    schema = _make(SchemaStatus.DRAFT)
    description = schema.view.description
    required_fields = schema.view.required_fields
    for to in (SchemaStatus.ACTIVE, SchemaStatus.DEPRECATED):
        schema.transition(to)
        assert schema.view.description == description
        assert schema.view.required_fields == required_fields


def test_immutable_attributes_rejected() -> None:
    schema = _make(SchemaStatus.DRAFT)
    for name in ("schema_id", "version", "description", "required_fields"):
        with pytest.raises(ImmutableSchemaAttributeError):
            setattr(schema, name, "x")


# --- 7. Isolation (SISO) -----------------------------------------------------------------


def test_siso_01_lifecycle_independent_of_run() -> None:
    schema = Schema.create(
        schema_id="article-draft",
        version=SchemaVersion(1),
        description="article draft contract",
        required_fields=["body"],
    )
    schema.transition(SchemaStatus.ACTIVE)
    schema.transition(SchemaStatus.DEPRECATED)
    assert schema.view.status is SchemaStatus.DEPRECATED
