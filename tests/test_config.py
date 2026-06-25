"""Tests for infrastructure configuration loading."""

from __future__ import annotations

import pytest

from omemo_content_factory.config import (
    APP_ENV_VAR,
    DEFAULT_APP_ENV,
    DEFAULT_LOG_LEVEL,
    LOG_LEVEL_VAR,
    AppEnv,
    load_config,
)


def test_defaults_when_env_empty() -> None:
    config = load_config({})
    assert config.app_env is DEFAULT_APP_ENV
    assert config.log_level == DEFAULT_LOG_LEVEL
    assert config.is_production is False


def test_reads_values_from_environ() -> None:
    config = load_config({APP_ENV_VAR: "production", LOG_LEVEL_VAR: "debug"})
    assert config.app_env is AppEnv.PRODUCTION
    assert config.log_level == "DEBUG"
    assert config.is_production is True


def test_app_env_is_case_insensitive_and_trimmed() -> None:
    config = load_config({APP_ENV_VAR: "  Testing  "})
    assert config.app_env is AppEnv.TESTING


def test_invalid_app_env_raises() -> None:
    with pytest.raises(ValueError, match=APP_ENV_VAR):
        load_config({APP_ENV_VAR: "staging"})


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ValueError, match=LOG_LEVEL_VAR):
        load_config({LOG_LEVEL_VAR: "verbose"})


def test_config_is_immutable() -> None:
    config = load_config({})
    with pytest.raises(AttributeError):
        setattr(config, "log_level", "DEBUG")
