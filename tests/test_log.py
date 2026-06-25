"""Tests for the logging configuration helper."""

from __future__ import annotations

import logging

import pytest

from omemo_content_factory.log import configure_logging


def test_configure_logging_sets_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unknown logging level"):
        configure_logging("VERBOSE")
