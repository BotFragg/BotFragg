"""Fetch and parse Riot's public VALORANT service status feeds."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .catalog import DISCORD_TO_VALORANT_LOCALE
from .http import HTTPClient, HTTPFailure

STATUS_URL = (
    "https://valorant.secure.dyn.riotcdn.net/channels/public/x/status/{region}.json"
)
SUPPORTED_REGIONS = ("na", "eu", "ap", "kr", "br", "latam", "pbe")
DEFAULT_REGION = "na"
DEFAULT_STATUS_LOCALE = "en_US"
CACHE_TTL_SECONDS = 60


class StatusUnavailable(RuntimeError):
    """Raised when Riot's status feed cannot be loaded or decoded."""


@dataclass(frozen=True, slots=True)
class StatusEntry:
    """One maintenance or incident reported by Riot."""

    kind: str
    title: str
    body: str | None
    updated: datetime | None
    platforms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegionStatus:
    """The current status entries of one region."""

    region: str
    entries: tuple[StatusEntry, ...]


@dataclass(slots=True)
class _CacheEntry:
    """A validated status payload with its expiry."""

    expires: float
    payload: dict[str, Any]


def _locale_code(locale: object | None) -> str:
    """Map a Discord locale to the underscore code the status feed uses."""
    code = getattr(locale, "value", locale)
    code = str(code) if code else ""
    if code == "Automatic":
        code = ""
    return DISCORD_TO_VALORANT_LOCALE.get(code, "en-US").replace("-", "_")


def _texts(value: Any) -> list[tuple[str, str]]:
    """Return the locale and content pairs of a status text list."""
    if not isinstance(value, list):
        return []
    return [
        (item["locale"], item["content"])
        for item in value
        if isinstance(item, dict)
        and isinstance(item.get("locale"), str)
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ]


def _translate(texts: list[tuple[str, str]], locale: object | None) -> str | None:
    """Pick the preferred translation, falling back to English then the first."""
    if not texts:
        return None
    preferred = _locale_code(locale)
    for wanted in (preferred, DEFAULT_STATUS_LOCALE):
        for text_locale, content in texts:
            if text_locale.replace("-", "_") == wanted.replace("-", "_"):
                return content
    return texts[0][1]


def _datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp, assuming UTC when it carries no offset."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _latest_update(updates: Any) -> tuple[dict[str, Any] | None, datetime | None]:
    """Return the newest published update and its timestamp."""
    if not isinstance(updates, list):
        return None, None
    chosen: dict[str, Any] | None = None
    chosen_at: datetime | None = None
    for update in updates:
        if not isinstance(update, dict) or update.get("publish") is False:
            continue
        created = _datetime(update.get("created_at")) or _datetime(
            update.get("updated_at")
        )
        if chosen is None or (
            created is not None and (chosen_at is None or created > chosen_at)
        ):
            chosen, chosen_at = update, created
    return chosen, chosen_at


def _entry(raw: dict[str, Any], kind: str, locale: object | None) -> StatusEntry | None:
    """Normalize one feed entry, dropping archived or unusable records."""
    if raw.get("archive_at"):
        return None
    update, update_at = _latest_update(raw.get("updates"))
    body = _translate(_texts(update.get("translations")), locale) if update else None
    title = _translate(_texts(raw.get("titles")), locale)
    if not title and not body:
        return None
    if not title:
        # Without a headline, the first body line becomes the title.
        lines = (body or "").strip().splitlines()
        title = lines[0]
        body = "\n".join(lines[1:]).strip() or None
    elif body == title:
        body = None
    raw_platforms = raw.get("platforms")
    platforms = (
        tuple(
            platform
            for platform in raw_platforms
            if isinstance(platform, str) and platform
        )
        if isinstance(raw_platforms, list)
        else ()
    )
    return StatusEntry(
        kind=kind,
        title=title[:256],
        body=body,
        updated=(
            _datetime(raw.get("updated_at"))
            or update_at
            or _datetime(raw.get("created_at"))
        ),
        platforms=platforms,
    )


class StatusService:
    """Fetch Riot's public status feed and cache it per region."""

    def __init__(self, http: HTTPClient, *, ttl: float = CACHE_TTL_SECONDS) -> None:
        """Bind the shared HTTP client and start an empty per-region cache."""
        self.http = http
        self.ttl = ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def region_for(region: str | None) -> str:
        """Return the supported status region closest to a game account region."""
        code = (region or "").lower()
        return code if code in SUPPORTED_REGIONS else DEFAULT_REGION

    async def status(
        self, region: str | None, locale: object | None = None
    ) -> RegionStatus:
        """Return the current incidents and maintenance for one region."""
        region = self.region_for(region)
        payload = await self._payload(region)
        entries: list[StatusEntry] = []
        for kind, key in (("maintenance", "maintenances"), ("incident", "incidents")):
            for raw in payload.get(key, []):
                if not isinstance(raw, dict):
                    continue
                entry = _entry(raw, kind, locale)
                if entry is not None:
                    entries.append(entry)
        entries.sort(
            key=lambda entry: entry.updated or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return RegionStatus(region=region, entries=tuple(entries))

    async def _payload(self, region: str) -> dict[str, Any]:
        """Fetch or reuse one region's validated status payload."""
        async with self._locks.setdefault(region, asyncio.Lock()):
            now = time.monotonic()
            cached = self._cache.get(region)
            if cached is not None and cached.expires > now:
                return cached.payload
            try:
                result = await self.http.request(
                    "GET", STATUS_URL.format(region=region)
                )
            except HTTPFailure as exc:
                raise StatusUnavailable("Status feed request failed") from exc
            if result.status != 200 or not isinstance(result.data, dict):
                raise StatusUnavailable(f"Status feed returned HTTP {result.status}")
            payload = result.data
            if not isinstance(payload.get("maintenances", []), list) or not isinstance(
                payload.get("incidents", []), list
            ):
                raise StatusUnavailable("Status feed has an invalid shape")
            self._cache[region] = _CacheEntry(expires=now + self.ttl, payload=payload)
            return payload
