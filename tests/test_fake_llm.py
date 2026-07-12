"""Tests for FakeLLMClient — the keyless, universal provider behind the LLMClient port.

Verify the invariants that keep it agent-agnostic: a value per requested field, deterministic,
derived only from ``fields`` (never ``system``/``user``), with no per-field-name branching — and
that it plugs into the existing ``LLMTaskExecutor`` unchanged (a normal port implementation, not a
new execution branch).
"""

from __future__ import annotations

from omemo_content_factory.infrastructure.fake_llm import FakeLLMClient
from omemo_content_factory.infrastructure.llm import LLMTaskExecutor


def test_returns_a_value_for_every_requested_field() -> None:
    result = FakeLLMClient().complete(system="s", user="u", fields=["a", "b", "c"])
    assert set(result) == {"a", "b", "c"}
    assert all(result[name] for name in result)  # every value non-empty


def test_is_deterministic() -> None:
    client = FakeLLMClient()
    first = client.complete(system="s", user="u", fields=["x", "y"])
    second = client.complete(system="s", user="u", fields=["x", "y"])
    assert first == second


def test_ignores_system_and_user_fields_are_the_sole_source() -> None:
    client = FakeLLMClient()
    a = client.complete(system="one", user="alpha", fields=["f"])
    b = client.complete(system="two", user="omega", fields=["f"])
    assert a == b  # same fields -> same result regardless of system/user


def test_is_agent_agnostic_no_field_name_branching() -> None:
    client = FakeLLMClient()
    # Unrelated field sets from hypothetical future agents all get non-empty values,
    # and a given field name maps identically regardless of the surrounding fields.
    leo = client.complete(system="s", user="u", fields=["title", "hook", "script"])
    qa = client.complete(system="s", user="u", fields=["verdict", "score", "notes"])
    solo = client.complete(system="s", user="u", fields=["verdict"])
    assert all(leo.values()) and all(qa.values())
    assert qa["verdict"] == solo["verdict"]  # value depends only on the field name, not the set


def test_plugs_into_llm_task_executor_unchanged() -> None:
    executor = LLMTaskExecutor(
        client=FakeLLMClient(),
        system_prompt="system",
        user_template="{input}",
        schema_ref="x@1",
        output_fields=("f1", "f2"),
    )
    result = executor.execute("brief")
    assert result.succeeded is True
    assert result.schema_ref == "x@1"
    assert set(result.payload_fields or {}) == {"f1", "f2"}
