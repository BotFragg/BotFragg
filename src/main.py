"""Executable entry point that configures logging and starts BotFragg."""

from __future__ import annotations

import logging

from .bot import BotFraggBot
from .config import Settings
from .monitoring import LOG_FORMAT, PlainFormatter


def main() -> None:
    """Load settings, configure logging, and run the Discord client."""
    config = Settings.from_env()
    handler = logging.StreamHandler()
    handler.setFormatter(PlainFormatter(LOG_FORMAT))
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
    )
    bot = BotFraggBot(config)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
