"""Provider/model selection ownership — Content Factory owns which provider/model a role uses.

Realizes `ADR-0016` / `PROVIDER_MODEL_SPEC`. The **single public contract** is
:func:`client_for_role` — ``role + environment -> ready LLMClient`` (SPEC §4.1) — behind the
existing port (`ADR-0014`). Keyless is the **fake** provider; a missing or invalid binding **fails
closed** — never a silent hardcoded model default (PROJECT §5, §10). Reuses ``AnthropicLLMClient`` /
``FakeLLMClient``; the Composition Root and the ``LLMClient`` port are unchanged (the Root still
*receives* the resolved client and gains no selection logic).

The ``role -> (provider, model)`` binding, its env format, and the two-step load/resolve are
**implementation details** (SPEC §1.2): provider granularity is per-role, values come from the
environment, and API keys are never read here (the adapter's SDK obtains them; PROJECT §5, §6).
Callers depend only on :func:`client_for_role` and :class:`ProviderModelSelectionError`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from omemo_content_factory.infrastructure.fake_llm import FakeLLMClient
from omemo_content_factory.infrastructure.llm import AnthropicLLMClient, LLMClient

__all__ = ["ProviderModelSelectionError", "client_for_role"]

_PROVIDER_ANTHROPIC = "anthropic"
_PROVIDER_FAKE = "fake"
_ENV_PROVIDER_PREFIX = "OMEMO_PROVIDER__"
_ENV_MODEL_PREFIX = "OMEMO_MODEL__"


class ProviderModelSelectionError(Exception):
    """A role has no valid provider/model binding — selection fails closed (SPEC §4.2)."""


def client_for_role(agent_ref: str, environ: Mapping[str, str]) -> LLMClient:
    """Return the ready :class:`LLMClient` for a role's configured provider/model (SPEC §4.1).

    The **single public entry**: ``role + environment -> client``. Config assembly and the internal
    ``role -> binding`` representation are hidden; callers depend only on this contract and the
    ``LLMClient`` port. Fail-closed (SPEC §4.2): a missing / unknown / model-less binding raises
    :class:`ProviderModelSelectionError` — never a silent default.
    """
    config = _load_config_from_env(environ, [agent_ref])
    return _resolve_client(agent_ref, config)


# --- implementation details (not part of the public contract) -----------------------------


@dataclass(frozen=True, slots=True)
class _RoleBinding:
    """Internal: the provider and model selected for one role (SPEC §3)."""

    provider: str
    model: str = ""


def _resolve_client(agent_ref: str, config: Mapping[str, _RoleBinding]) -> LLMClient:
    """Internal: build the client for a role's binding; fail-closed (SPEC §4.2)."""
    binding = config.get(agent_ref)
    if binding is None:
        raise ProviderModelSelectionError(f"no provider/model binding for role '{agent_ref}'")
    if binding.provider == _PROVIDER_FAKE:
        return FakeLLMClient()
    if binding.provider == _PROVIDER_ANTHROPIC:
        if not binding.model:
            raise ProviderModelSelectionError(
                f"role '{agent_ref}' selects provider 'anthropic' without a model"
            )
        return AnthropicLLMClient(model=binding.model)
    raise ProviderModelSelectionError(
        f"role '{agent_ref}' selects unknown provider '{binding.provider}'"
    )


def _env_token(agent_ref: str) -> str:
    """Internal: normalize a role id to an env-safe token (impl detail, SPEC §1.2)."""
    return "".join(ch if ch.isalnum() else "_" for ch in agent_ref).upper()


def _load_config_from_env(
    environ: Mapping[str, str], roles: Iterable[str]
) -> dict[str, _RoleBinding]:
    """Internal: build ``role -> _RoleBinding`` from the environment for the given roles.

    Provider from ``OMEMO_PROVIDER__<token>``, model from ``OMEMO_MODEL__<token>`` (role
    normalized). Roles without a provider entry are omitted (fail-closed at resolution). Secrets are
    never read here (PROJECT §6).
    """
    config: dict[str, _RoleBinding] = {}
    for role in roles:
        token = _env_token(role)
        provider = environ.get(f"{_ENV_PROVIDER_PREFIX}{token}")
        if provider is None:
            continue
        model = environ.get(f"{_ENV_MODEL_PREFIX}{token}", "")
        config[role] = _RoleBinding(provider=provider.strip().lower(), model=model.strip())
    return config
