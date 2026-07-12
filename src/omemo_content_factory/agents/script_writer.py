"""``script_writer@v1`` (Leo) — the video script-writer role definition.

The concrete, static assets of one production role, owned by the factory (migrated from Main Core
per ADR-0001 Slice A): the :class:`Agent` descriptor, its versioned :class:`Prompt` (System + User
template + ``schema_ref``; PROJECT.md §15, ADR-0011) and the ``script-draft`` :class:`Schema` its
Output conforms to (ADR-0008). They are **passive data** in existing domain types — no new entity,
no execution logic — assembled into an executor by the Composition Root, never here.

The module also exposes the three catalogues keyed as the Composition Root expects
(``agent.prompt_ref -> Prompt``, ``prompt.schema_ref -> Schema``) so a caller wires Leo without
restating any ref string. ``script-draft@v1`` is the same opaque ``schema_ref`` the Output already
carried, kept stable across the migration.
"""

from __future__ import annotations

from omemo_content_factory.domain.agent import Agent
from omemo_content_factory.domain.prompt import Prompt, PromptId, PromptVersion
from omemo_content_factory.domain.schema import Schema, SchemaStatus, SchemaVersion

# --- reference strings (opaque handles used across the Composition Root) ------------------

AGENT_REF = "script_writer@v1"
"""The ``agent_ref`` selecting this role's executor (unchanged from Main Core)."""

PROMPT_REF: PromptId = "script-writer"
"""The logical Prompt id this Agent binds to (``Agent.prompt_ref -> Prompt.prompt_id``)."""

SCHEMA_REF = "script-draft@v1"
"""The opaque ``schema_ref`` of the produced Output (stable across the migration)."""


# --- Schema: the output contract (title / hook / script), ACTIVE -------------------------

SCRIPT_DRAFT_SCHEMA = Schema.create(
    schema_id="script-draft",
    version=SchemaVersion(1),
    description="Video script draft contract: catchy title, first-seconds hook, scene script.",
    required_fields=("title", "hook", "script"),
)
SCRIPT_DRAFT_SCHEMA.transition(SchemaStatus.ACTIVE)


# --- Prompt: role behaviour (System + User template) -------------------------------------

SCRIPT_WRITER_PROMPT = Prompt(
    prompt_id=PROMPT_REF,
    version=PromptVersion(1),
    system=(
        "Ты Script Writer видео-фабрики OMEMO. По присланному ресёрчу напиши короткий "
        "вертикальный видео-сценарий на русском: цепляющий заголовок (title), хук "
        "первых секунд (hook) и сценарий по сценам с призывом к действию (script). "
        "Кратко, по делу, без воды."
    ),
    user_template="Ресёрч и контекст:\n{input}\n\nСделай сценарий: title, hook, script.",
    schema_ref=SCHEMA_REF,
)


# --- Agent: the role descriptor (agent_ref -> prompt_ref) --------------------------------

SCRIPT_WRITER_AGENT = Agent(
    agent_id=AGENT_REF,
    name="Leo — Script Writer",
    prompt_ref=PROMPT_REF,
    description="Turns research/brief into a short vertical video script (title, hook, script).",
)


# --- catalogues keyed for the Composition Root -------------------------------------------

AGENTS: tuple[Agent, ...] = (SCRIPT_WRITER_AGENT,)
PROMPTS: dict[PromptId, Prompt] = {SCRIPT_WRITER_PROMPT.prompt_id: SCRIPT_WRITER_PROMPT}
SCHEMAS: dict[str, Schema] = {SCHEMA_REF: SCRIPT_DRAFT_SCHEMA}
