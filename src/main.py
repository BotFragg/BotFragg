"""Executable entry point that configures logging and starts Botfragg."""

from __future__ import annotations

import logging

from .bot import BotfraggBot
from .config import Settings
from .monitoring import StructuredFormatter, configure_monitoring


def main() -> None:
    """Load settings, configure observability, and run the Discord client."""
    config = Settings.from_env()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logging.basicConfig(
        level=logging.DEBUG if config.verbose_logging else logging.INFO,
        handlers=[handler],
    )
    configure_monitoring(config)
    bot = BotfraggBot(config)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
