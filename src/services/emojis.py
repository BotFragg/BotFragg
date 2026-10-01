"""Cache Discord application emojis and create them from bundled image assets."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord

from ..config import ROOT

log = logging.getLogger(__name__)

SKIN_TIER_EMOJIS = {
    "0cebb8be-46d7-c12a-d306-e9907bfc5a25": ("tier_deluxe", "deluxe.png"),
    "e046854e-406c-37f4-6607-19a9ba8426fc": ("tier_exclusive", "exclusive.png"),
    "60bca009-4182-7998-dee7-b8a2558dc369": ("tier_premium", "premium.png"),
    "12683d76-48d7-84a3-4e09-6985794f0445": ("tier_select", "select.png"),
    "411e4a55-4e59-7757-41f0-86a53f101bb5": ("tier_ultra", "ultra.png"),
}
CURRENCY_EMOJIS = {
    "vp": ("ValPointsIcon", "vp.png"),
    "rp": ("RadianiteIcon", "rad.png"),
    "kc": ("KingdomCreditIcon", "kc.png"),
}


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
                *CURRENCY_EMOJIS.values(),
                ("fbar", "fbar.png"),
                ("ebar", "ebar.png"),
                *SKIN_TIER_EMOJIS.values(),
            ):
                await self._get_or_create(name, ROOT / "assets" / filename)
        except discord.HTTPException:
            log.warning("Could not warm application emoji cache; using text fallbacks")

    async def currency(self, kind: str) -> str:
        """Return the emoji for VP, Radianite, or Kingdom Credits, if available."""
        name, filename = CURRENCY_EMOJIS[kind]
        return await self._get_or_create(name, ROOT / "assets" / filename)

    async def battlepass_bars(self) -> tuple[str, str]:
        """Return the filled and empty battlepass progress-bar emoji strings."""
        return (
            await self._get_or_create("fbar", ROOT / "assets" / "fbar.png"),
            await self._get_or_create("ebar", ROOT / "assets" / "ebar.png"),
        )

    def skin_emoji(self, tier_uuid: str | None) -> str:
        """Return a cached application emoji for a skin tier, if available."""
        if (tier := SKIN_TIER_EMOJIS.get(tier_uuid or "")) and (
            emoji := self._emojis.get(tier[0])
        ):
            return str(emoji)
        return ""

    def skin_name(self, name: str, tier_uuid: str | None) -> str:
        """Prefix a skin name with its cached tier emoji when available."""
        emoji = self.skin_emoji(tier_uuid)
        return f"{emoji} {name}" if emoji else name

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
