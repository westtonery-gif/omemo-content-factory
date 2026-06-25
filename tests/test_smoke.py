"""Smoke tests: the package imports and the entrypoint runs."""

from __future__ import annotations

import omemo_content_factory
from omemo_content_factory.__main__ import main


def test_version_is_non_empty_string() -> None:
    assert isinstance(omemo_content_factory.__version__, str)
    assert omemo_content_factory.__version__


def test_main_runs_without_error() -> None:
    main()
