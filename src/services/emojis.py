"""Cache Discord application emojis and create them from bundled image assets."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from weakref import WeakValueDictionary

import discord

from ..config import ROOT
from .http import DISCORD_HTTP_ERRORS

log = logging.getLogger(__name__)

SKIN_TIER_EMOJIS = {
    "0cebb8be-46d7-c12a-d306-e9907bfc5a25": ("tier_deluxe", "emojis/skins/deluxe.png"),
    "e046854e-406c-37f4-6607-19a9ba8426fc": (
        "tier_exclusive",
        "emojis/skins/exclusive.png",
    ),
    "60bca009-4182-7998-dee7-b8a2558dc369": (
        "tier_premium",
        "emojis/skins/premium.png",
    ),
    "12683d76-48d7-84a3-4e09-6985794f0445": ("tier_select", "emojis/skins/select.png"),
    "411e4a55-4e59-7757-41f0-86a53f101bb5": ("tier_ultra", "emojis/skins/ultra.png"),
}
CURRENCY_EMOJIS = {
    "vp": ("ValPointsIcon", "emojis/currency/vp.png"),
    "rp": ("RadianiteIcon", "emojis/currency/rad.png"),
    "kc": ("KingdomCreditIcon", "emojis/currency/kc.png"),
}
# Tiers 1 and 2 are placeholders; Riot ships art for unranked and 3 through 27.
RANK_EMOJIS = {
    tier: (f"rank_{tier}", f"emojis/ranks/rank_{tier}.png")
    for tier in (0, *range(3, 28))
}
AGENT_EMOJIS = {
    "41fb69c1-4189-7b37-f117-bcaf1e96f1bf": "astra",
    "5f8d3a7f-467b-97f3-062c-13acf203c006": "breach",
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417": "brimstone",
    "22697a3d-45bf-8dd7-4fec-84a9e28c69d7": "chamber",
    "1dbf2edd-4729-0984-3115-daa5eed44993": "clove",
    "117ed9e3-49f3-6512-3ccf-0cada7e3823b": "cypher",
    "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235": "deadlock",
    "dade69b4-4f5a-8528-247b-219e5a1facd6": "fade",
    "e370fa57-4757-3604-3648-499e1f642d3f": "gekko",
    "95b78ed7-4637-86d9-7e41-71ba8c293152": "harbor",
    "ddd5a15c-4fbe-42fa-3789-11a55ca5ee04": "hush",
    "0e38b510-41a8-5780-5e8f-568b2a4f2d6c": "iso",
    "add6443a-41bd-e414-f6ad-e58d267f4e95": "jett",
    "601dbbe7-43ce-be57-2a40-4abd24953621": "kayo",
    "1e58de9c-4950-5125-93e9-a0aee9f98746": "killjoy",
    "7c8a4701-4de6-9355-b254-e09bc2a34b72": "miks",
    "bb2a4828-46eb-8cd1-e765-15848195d751": "neon",
    "8e253930-4c05-31dd-1b6c-968525494517": "omen",
    "eb93336a-449b-9c1b-0a54-a891f7921d69": "phoenix",
    "f94c3b30-42be-e959-889c-5aa313dba261": "raze",
    "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc": "reyna",
    "569fdd95-4d10-43ab-ca70-79becc718b46": "sage",
    "6f2a04ca-43e0-be17-7f36-b3908627744d": "skye",
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa": "sova",
    "b444168c-4e35-8076-db47-ef9bf368f384": "tejo",
    "92eeef5d-43b5-1d4a-8d03-b3927a09034b": "veto",
    "707eab51-4836-f488-046a-cda6bf494859": "viper",
    "efba5359-4016-a1e5-7626-b1ae76895940": "vyse",
    "df1cb487-4902-002e-5c17-d28e83e78588": "waylay",
    "7f94d92c-4234-0a36-9646-3a87eb8b5c89": "yoru",
}

QUEUE_EMOJIS = {
    "competitive": ("queue_competitive", "emojis/queues/queue_competitive.png")
}
PROFILE_EMOJI_ASSETS = (
    *RANK_EMOJIS.values(),
    *(
        (f"agent_{slug}", f"emojis/agents/agent_{slug}.png")
        for slug in AGENT_EMOJIS.values()
    ),
    *QUEUE_EMOJIS.values(),
)


class ApplicationEmojiService:
    """Application emoji cache with safe text fallbacks."""

    def __init__(self, client: discord.Client) -> None:
        """Bind the Discord client and initialize the serialized emoji cache."""
        self.client = client
        self._emojis: dict[str, discord.Emoji] = {}
        self._retry_at: dict[str, float] = {}
        self._loaded = False
        self._load_retry_at = 0.0
        self._load_lock = asyncio.Lock()
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def warm(self) -> None:
        """Load existing application emojis and create any bundled assets that are missing."""
        try:
            await self._load()
            for name, filename in (
                *CURRENCY_EMOJIS.values(),
                ("fbar", "emojis/bars/fbar.png"),
                ("ebar", "emojis/bars/ebar.png"),
                *SKIN_TIER_EMOJIS.values(),
            ):
                await self._get_or_create(name, ROOT / "assets" / filename)
            await self.ensure_profile_emojis()
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not warm application emoji cache; using text fallbacks")

    async def ensure_profile_emojis(self) -> None:
        """Create the rank, agent, and queue emojis that are still missing."""
        now = time.monotonic()
        pending = [
            (name, filename)
            for name, filename in PROFILE_EMOJI_ASSETS
            if name not in self._emojis and now >= self._retry_at.get(name, 0)
        ]
        if not pending:
            return
        semaphore = asyncio.Semaphore(4)

        async def create(name: str, filename: str) -> None:
            async with semaphore:
                await self._get_or_create(name, ROOT / "assets" / filename)

        await asyncio.gather(*(create(name, filename) for name, filename in pending))

    def rank_emoji(self, tier: int | None) -> str:
        """Return the cached application emoji for a competitive tier, if available."""
        if (entry := RANK_EMOJIS.get(tier)) and (emoji := self._emojis.get(entry[0])):
            return str(emoji)
        return ""

    def agent_emoji(self, agent_id: str | None) -> str:
        """Return the cached application emoji for one agent, if available."""
        if (slug := AGENT_EMOJIS.get(agent_id or "")) and (
            emoji := self._emojis.get(f"agent_{slug}")
        ):
            return str(emoji)
        return ""

    def queue_emoji(self, queue_id: str | None) -> str:
        """Return the cached application emoji for one queue, if available."""
        if (entry := QUEUE_EMOJIS.get(queue_id or "")) and (
            emoji := self._emojis.get(entry[0])
        ):
            return str(emoji)
        return ""

    async def _load(self) -> None:
        """Replace the cache with the application emojis that currently exist."""
        self._emojis = {
            emoji.name: emoji for emoji in await self.client.fetch_application_emojis()
        }
        self._loaded = True

    async def _retry_load(self) -> None:
        """Reload after a failed warm, at most once per cooldown window."""
        if time.monotonic() < self._load_retry_at:
            return
        async with self._load_lock:
            if time.monotonic() < self._load_retry_at:
                return
            try:
                await self._load()
            except DISCORD_HTTP_ERRORS:
                self._load_retry_at = time.monotonic() + 30
                log.warning("Could not load application emoji cache", exc_info=True)

    async def currency(self, kind: str) -> str:
        """Return the emoji for VP, Radianite, or Kingdom Credits, if available."""
        name, filename = CURRENCY_EMOJIS[kind]
        return await self._get_or_create(name, ROOT / "assets" / filename)

    async def battlepass_bars(self) -> tuple[str, str]:
        """Return the filled and empty battlepass progress-bar emoji strings."""
        return (
            await self._get_or_create("fbar", ROOT / "assets" / "emojis/bars/fbar.png"),
            await self._get_or_create("ebar", ROOT / "assets" / "emojis/bars/ebar.png"),
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
        if time.monotonic() < self._retry_at.get(name, 0):
            return ""
        async with self._locks.setdefault(name, asyncio.Lock()):
            if emoji := self._emojis.get(name):
                return str(emoji)
            if time.monotonic() < self._retry_at.get(name, 0):
                return ""
            if not self._loaded:
                await self._retry_load()
                if emoji := self._emojis.get(name):
                    return str(emoji)
            try:
                image = await asyncio.to_thread(source.read_bytes)
                emoji = await self.client.create_application_emoji(
                    name=name, image=image
                )
            except DISCORD_HTTP_ERRORS:
                self._retry_at[name] = time.monotonic() + 30
                log.warning(
                    "Could not create application emoji %s", name, exc_info=True
                )
                return ""
            self._emojis[name] = emoji
            self._retry_at.pop(name, None)
            return str(emoji)
