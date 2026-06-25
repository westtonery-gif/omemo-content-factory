"""Console entrypoint: report version and effective configuration.

This is a Stage 1 *smoke* entrypoint. It proves the package installs, imports
and reads configuration from the environment. It contains no business logic and
performs no external calls. Run with: ``python -m omemo_content_factory``.
"""

from __future__ import annotations

import logging

from omemo_content_factory.__about__ import __version__
from omemo_content_factory.config import load_config
from omemo_content_factory.log import configure_logging


def main() -> None:
    """Load configuration, configure logging and report the runtime state."""
    config = load_config()
    configure_logging(config.log_level)
    logger = logging.getLogger("omemo_content_factory")
    logger.info("OMEMO Content Factory v%s", __version__)
    logger.info("Environment: %s", config.app_env.value)
    logger.info("Log level: %s", config.log_level)


if __name__ == "__main__":
    main()
