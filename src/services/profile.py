"""Fetch a linked account's VALORANT identity, rank, and account level."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from weakref import WeakValueDictionary

from ..models import Account
from .auth import AuthService, pd_url, request_many_with_claims_repair
from .catalog import CatalogService
from .http import HTTPClient, HTTPFailure
from .riot_values import identifier, nonnegative

PROFILE_TTL_SECONDS = 300
NEGATIVE_CACHE_SECONDS = 30
# Every account level needs a flat 5,000 Account Points; Riot returns the
# progress inside the current level but never the target.
LEVEL_XP_TARGET = 5000
COMMON_QUEUE = "competitive"


class ProfileUnavailable(RuntimeError):
    """Raised when Riot's profile endpoints cannot be used."""


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """Identity, rank, and level data for one linked account."""

    card_id: str | None
    title_id: str | None
    level: int | None
    xp: int | None
    tier: int
    rr: int | None
    wins: int | None
    games: int | None
    peak_tier: int | None

    @property
    def xp_target(self) -> int | None:
        """Return the XP needed for the next level when progress is known."""
        return (
            LEVEL_XP_TARGET if self.level is not None and self.xp is not None else None
        )


class ProfileService:
    """Fetch and cache one account's profile for a few minutes."""

    def __init__(
        self, http: HTTPClient, auth: AuthService, catalog: CatalogService
    ) -> None:
        """Bind the shared services and start an empty per-account cache."""
        self.http = http
        self.auth = auth
        self.catalog = catalog
        self._cache: dict[str, tuple[float, PlayerProfile]] = {}
        self._retry_at: dict[str, float] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def profile(self, account: Account) -> PlayerProfile:
        """Return the account's profile, reusing a recent result when possible."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            now = time.monotonic()
            cached = self._cache.get(account.puuid)
            if cached is not None and cached[0] > now:
                return cached[1]
            if now < self._retry_at.get(account.puuid, 0.0):
                raise ProfileUnavailable("Profile data is temporarily unavailable")
            try:
                result = await self._fetch(account)
            except ProfileUnavailable:
                self._retry_at[account.puuid] = (
                    time.monotonic() + NEGATIVE_CACHE_SECONDS
                )
                raise
            self._cache[account.puuid] = (now + PROFILE_TTL_SECONDS, result)
            self._retry_at.pop(account.puuid, None)
            return result

    async def _fetch(self, account: Account) -> PlayerProfile:
        """Fetch the loadout, account XP, and MMR payloads and normalize them."""
        urls = (
            pd_url(
                account.region,
                f"/personalization/v3/players/{account.puuid}/playerloadout",
            ),
            pd_url(account.region, f"/account-xp/v1/players/{account.puuid}"),
            pd_url(account.region, f"/mmr/v1/players/{account.puuid}"),
        )
        try:
            headers = await self.auth.auth_headers(account)
            loadout, xp, mmr = await request_many_with_claims_repair(
                self.auth,
                account,
                headers,
                tuple(_profile_request(self.http, url) for url in urls),
            )
        except HTTPFailure as exc:
            raise ProfileUnavailable("Could not fetch profile data") from exc
        for response in (loadout, xp, mmr):
            if response.status != 200 or not isinstance(response.data, dict):
                raise ProfileUnavailable(f"Riot returned HTTP {response.status}")
        act = await self.catalog.current_act()
        return self._parse(loadout.data, xp.data, mmr.data, act[0] if act else None)

    @staticmethod
    def _parse(
        loadout: dict[str, Any],
        xp: dict[str, Any],
        mmr: dict[str, Any],
        act_id: str | None,
    ) -> PlayerProfile:
        """Normalize the three Riot payloads into one profile record."""
        identity = loadout.get("Identity")
        identity = identity if isinstance(identity, dict) else {}
        progress = xp.get("Progress")
        progress = progress if isinstance(progress, dict) else {}
        # Riot still returns the level when the player hides it, and the card
        # always shows it.
        level = nonnegative(identity.get("AccountLevel")) or nonnegative(
            progress.get("Level")
        )
        xp_value = nonnegative(progress.get("XP"))
        queue = _competitive(mmr)
        seasonal = queue.get("SeasonalInfoBySeasonID")
        seasonal = seasonal if isinstance(seasonal, dict) else {}
        entry = seasonal.get(act_id) if act_id else None
        if not isinstance(entry, dict):
            latest = mmr.get("LatestCompetitiveUpdate")
            season = latest.get("SeasonID") if isinstance(latest, dict) else None
            entry = seasonal.get(season) if isinstance(season, str) else None
        entry = entry if isinstance(entry, dict) else {}
        tier = nonnegative(entry.get("CompetitiveTier")) or 0
        return PlayerProfile(
            card_id=identifier(identity.get("PlayerCardID")),
            title_id=identifier(identity.get("PlayerTitleID")),
            level=level,
            xp=xp_value,
            tier=tier,
            rr=nonnegative(entry.get("RankedRating")) if tier else None,
            wins=nonnegative(entry.get("NumberOfWins")),
            games=nonnegative(entry.get("NumberOfGames")),
            peak_tier=_peak_tier(seasonal),
        )


def _profile_request(http: HTTPClient, url: str) -> Any:
    """Build one authenticated profile request for a batch."""

    def request(headers: dict[str, str]) -> Any:
        return http.request("GET", url, headers=headers)

    return request


def _competitive(mmr: dict[str, Any]) -> dict[str, Any]:
    """Return the competitive queue block of an MMR payload."""
    queues = mmr.get("QueueSkills")
    if not isinstance(queues, dict):
        return {}
    competitive = queues.get(COMMON_QUEUE)
    return competitive if isinstance(competitive, dict) else {}


def _peak_tier(seasonal: dict[str, Any]) -> int | None:
    """Return the highest competitive tier recorded across every act."""
    tiers = [
        tier
        for entry in seasonal.values()
        if isinstance(entry, dict)
        and (tier := nonnegative(entry.get("CompetitiveTier")))
    ]
    return max(tiers) if tiers else None
