"""Cache Discord application emojis and create them from bundled image assets."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord

from ..config import ROOT

log = logging.getLogger(__name__)


class ApplicationEmojiService:
    """Application emoji cache with safe text fallbacks."""

    def __init__(self, client: discord.Client) -> None:
        """Bind the Discord client and initialize the serialized emoji cache."""
        self.client = client
        self._emojis: dict[str, discord.Emoji] = {}
        self._lock = asyncio.Lock()

    async def warm(self) -> None:
        """Load existing application emojis and create any bundled assets that are missing."""
        try:
            self._emojis = {
                emoji.name: emoji
                for emoji in await self.client.fetch_application_emojis()
            }
            for name, filename in (
                ("ValPointsIcon", "vp.png"),
                ("RadianiteIcon", "rad.png"),
                ("KingdomCreditIcon", "kc.png"),
                ("fbar", "fbar.png"),
                ("ebar", "ebar.png"),
            ):
                await self._get_or_create(name, ROOT / "assets" / filename)
        except discord.HTTPException:
            log.warning("Could not warm application emoji cache; using text fallbacks")

    async def currency(self, kind: str) -> str:
        """Return the emoji for VP, Radianite, or Kingdom Credits, if available."""
        names = {
            "vp": "ValPointsIcon",
            "rp": "RadianiteIcon",
            "kc": "KingdomCreditIcon",
        }
        filenames = {"vp": "vp.png", "rp": "rad.png", "kc": "kc.png"}
        return await self._get_or_create(names[kind], ROOT / "assets" / filenames[kind])

    async def battlepass_bars(self) -> tuple[str, str]:
        """Return the filled and empty battlepass progress-bar emoji strings."""
        return (
            await self._get_or_create("fbar", ROOT / "assets" / "fbar.png"),
            await self._get_or_create("ebar", ROOT / "assets" / "ebar.png"),
        )

    async def _get_or_create(self, name: str, source: Path) -> str:
        """Resolve or create one application emoji, returning empty text on failure."""
        if emoji := self._emojis.get(name):
            return str(emoji)
        async with self._lock:
            if emoji := self._emojis.get(name):
                return str(emoji)
            try:
                image = await asyncio.to_thread(source.read_bytes)
                emoji = await self.client.create_application_emoji(
                    name=name, image=image
                )
            except OSError, discord.HTTPException:
                log.warning(
                    "Could not create application emoji %s", name, exc_info=True
                )
                return ""
            self._emojis[name] = emoji
            return str(emoji)
