"""Delivery wrapper that appends pending dev notices to interaction handlers."""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Concatenate

import discord

log = logging.getLogger(__name__)


def after_interaction[**P, Result](
    callback: Callable[
        Concatenate[Any, discord.Interaction[Any], P], Awaitable[Result]
    ],
) -> Callable[
    Concatenate[Any, discord.Interaction[Any], P], Coroutine[Any, Any, Result]
]:
    """Deliver pending dev notices after a view method's interaction callback."""

    @functools.wraps(callback)
    async def wrapper(
        self: Any,
        interaction: discord.Interaction[Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Result:
        try:
            return await callback(self, interaction, *args, **kwargs)
        finally:
            try:
                await interaction.client.dev_notices.deliver(interaction)
            except Exception:
                log.exception("Could not deliver the dev announcement")

    return wrapper
