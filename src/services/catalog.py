"""VALORANT skin, bundle, accessory, and mission metadata with a local cache."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from weakref import WeakValueDictionary

from rapidfuzz import fuzz, process, utils

from ..config import ROOT
from .http import HTTPClient, HTTPFailure
from .riot_values import parse_datetime

ENGLISH_LOCALE = "en-US"
MISSION_METADATA_TTL = 1800
MISSION_METADATA_RETRY_SECONDS = 30
ACCESSORY_METADATA_RETRY_SECONDS = 30
GAME_METADATA_TTL = 1800
GAME_METADATA_RETRY_SECONDS = 30
# Maps, agents, ranks, and seasons only move on a game patch, so the saved
# game-metadata copy is reused across restarts for up to a day.
GAME_METADATA_MAX_AGE = 86400
GAME_METADATA_DOCUMENTS = (
    ("competitivetiers", "competitivetiers"),
    ("maps", "maps"),
    ("seasons", "seasons"),
)
CATALOG_FORMAT_VERSION = 4
BUDDY_ITEM_TYPE_ID = "dd3bf334-87f3-40bd-b043-682a57a8dc3a"
PLAYER_CARD_ITEM_TYPE_ID = "3f296c07-64c3-494c-923b-fe692a4fa1bd"
PLAYER_TITLE_ITEM_TYPE_ID = "de7caa6b-adf7-4588-bbd1-143831e786c6"
SPRAY_ITEM_TYPE_ID = "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
FLEX_ITEM_TYPE_ID = "03a572de-4234-31ed-d344-ababa488f981"
DISCORD_TO_VALORANT_LOCALE = {
    "id": "id-ID",
    "de": "de-DE",
    "es-ES": "es-ES",
    "es-419": "es-MX",
    "fr": "fr-FR",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "pl": "pl-PL",
    "pt-BR": "pt-BR",
    "ru": "ru-RU",
    "th": "th-TH",
    "tr": "tr-TR",
    "vi": "vi-VN",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
}

log = logging.getLogger(__name__)


def localized_text(value: Any, locale: object | None = None) -> str:
    """Resolve VALORANT-API text for a Discord locale with English fallback."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""

    locale_code = getattr(locale, "value", locale)
    locale_code = str(locale_code) if locale_code else ENGLISH_LOCALE
    if locale_code == "Automatic":
        locale_code = ENGLISH_LOCALE
    valorant_locale = DISCORD_TO_VALORANT_LOCALE.get(locale_code, ENGLISH_LOCALE)
    for key in dict.fromkeys((valorant_locale, ENGLISH_LOCALE)):
        text = value.get(key)
        if isinstance(text, str) and text:
            return text
    return ""


def _localized_values(value: Any) -> dict[str, str]:
    """Normalize a localized string or locale map into nonempty values."""
    if isinstance(value, str):
        return {ENGLISH_LOCALE: value} if value else {}
    if not isinstance(value, dict):
        return {}
    return {
        locale: text
        for locale, text in value.items()
        if isinstance(locale, str) and isinstance(text, str) and text
    }


def _combined_names(parent: dict[str, str], act: dict[str, str]) -> dict[str, str]:
    """Join a parent season name and an act name for each localized locale."""
    if not parent:
        return act
    return {
        locale: " // ".join(
            part
            for part in (
                parent.get(locale) or parent.get(ENGLISH_LOCALE),
                act.get(locale) or act.get(ENGLISH_LOCALE),
            )
            if part
        )
        for locale in set(parent) | set(act)
    }


def _catalog_rows(value: Any, label: str) -> list[dict[str, Any]]:
    """Validate upstream rows and the identifiers/media consumed by catalog views."""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise HTTPFailure(f"Invalid catalog {label}")
    for row in value:
        for key in (
            "uuid",
            "contentTierUuid",
            "displayIcon",
            "displayIcon2",
            "largeArt",
            "smallArt",
            "wideArt",
            "fullTransparentIcon",
            "verticalPromoImage",
            "fullRender",
            "swatch",
            "streamedVideo",
        ):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise HTTPFailure(f"Invalid catalog {label} {key}")
    return value


@dataclass(slots=True)
class Skin:
    """Hold normalized skin identity, display data, pricing, levels, and chromas."""

    uuid: str
    offer_uuid: str
    name: str
    icon: str | None
    tier_uuid: str | None
    price: int | None = None
    levels: list[dict[str, Any]] = field(default_factory=list)
    chromas: list[dict[str, Any]] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)

    def name_for(self, locale: object | None = None) -> str:
        """Return this skin's localized or English name, or empty when missing."""
        return localized_text(self.names, locale) or (
            "" if self.name == self.uuid else self.name
        )


@dataclass(slots=True)
class Bundle:
    """Hold static display metadata for a VALORANT bundle."""

    uuid: str
    name: str
    subtitle: str | None
    description: str | None
    icon: str | None
    names: dict[str, str] = field(default_factory=dict)
    subtitles: dict[str, str] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)

    def name_for(self, locale: object | None = None) -> str:
        """Return this bundle's localized or English name, or empty when missing."""
        return localized_text(self.names, locale) or (
            "" if self.name == self.uuid else self.name
        )

    def subtitle_for(self, locale: object | None = None) -> str | None:
        """Return this bundle's localized subtitle, if available."""
        return localized_text(self.subtitles or self.subtitle, locale) or self.subtitle

    def description_for(self, locale: object | None = None) -> str | None:
        """Return this bundle's localized description, if available."""
        return (
            localized_text(self.descriptions or self.description, locale)
            or self.description
        )


@dataclass(slots=True)
class Accessory:
    """Hold normalized display data for a non-skin cosmetic reward."""

    name: str
    icon: str | None
    title_text: str | None = None
    names: dict[str, str] = field(default_factory=dict)
    title_texts: dict[str, str] = field(default_factory=dict)
    small_icon: str | None = None

    def name_for(self, locale: object | None = None) -> str:
        """Return this accessory's localized name, or empty when metadata is missing."""
        return localized_text(self.names, locale) or self.name

    def title_text_for(self, locale: object | None = None) -> str | None:
        """Return localized accessory title text, if available."""
        return (
            localized_text(self.title_texts or self.title_text, locale)
            or self.title_text
        )


def _invalid_snapshot_rows(rows: list[Any], identifiers: tuple[str, ...]) -> bool:
    """Return whether any cached catalog row is structurally unusable."""
    for item in rows:
        if not isinstance(item, dict):
            return True
        if any(
            not isinstance(item.get(key), str) or not item[key] for key in identifiers
        ):
            return True
        price = item.get("price")
        if price is not None and (type(price) is not int or price < 0):
            return True
        if any(
            item.get(key) is not None and not isinstance(item[key], str)
            for key in ("name", "icon", "tier_uuid", "subtitle", "description")
        ):
            return True
        if any(
            not isinstance(item.get(key, []), list)
            or not all(isinstance(child, dict) for child in item.get(key, []))
            for key in ("levels", "chromas")
        ):
            return True
        if any(
            not isinstance(item.get(key, {}), dict)
            or not all(isinstance(text, str) for text in item.get(key, {}).values())
            for key in ("names", "subtitles", "descriptions")
        ):
            return True
    return False


def _skin_from_snapshot(item: dict[str, Any]) -> Skin:
    """Build a skin from a cached row, tolerating legacy single-name rows."""
    names = _localized_values(item.get("names") or item.get("name"))
    return Skin(
        uuid=item["uuid"],
        offer_uuid=item["offer_uuid"],
        name=str(
            item.get("name") or localized_text(names, ENGLISH_LOCALE) or item["uuid"]
        ),
        icon=item.get("icon"),
        tier_uuid=item.get("tier_uuid"),
        price=item.get("price"),
        levels=item.get("levels", []),
        chromas=item.get("chromas", []),
        names=names,
    )


def _bundle_from_snapshot(item: dict[str, Any]) -> Bundle:
    """Build a bundle from a cached row, tolerating legacy single-name rows."""
    names = _localized_values(item.get("names") or item.get("name"))
    subtitles = _localized_values(item.get("subtitles") or item.get("subtitle"))
    descriptions = _localized_values(
        item.get("descriptions") or item.get("description")
    )
    return Bundle(
        uuid=item["uuid"],
        name=str(
            item.get("name") or localized_text(names, ENGLISH_LOCALE) or item["uuid"]
        ),
        subtitle=item.get("subtitle")
        or localized_text(subtitles, ENGLISH_LOCALE)
        or None,
        description=item.get("description")
        or localized_text(descriptions, ENGLISH_LOCALE)
        or None,
        icon=item.get("icon"),
        names=names,
        subtitles=subtitles,
        descriptions=descriptions,
    )


class CatalogService:
    """Load, refresh, search, and cache VALORANT catalog data."""

    def __init__(self, http: HTTPClient) -> None:
        """Prepare in-memory indexes and the repository catalog snapshot."""
        self.http = http
        self.path = ROOT / "data" / "skins.json"
        self.skins: dict[str, Skin] = {}
        self._skin_choices: dict[str, str] = {}
        self.bundles: dict[str, Bundle] = {}
        self.skin_aliases: dict[str, Skin] = {}
        self._accessories: dict[tuple[str, str], Accessory | None] = {}
        self._accessory_retry_at: dict[tuple[str, str], float] = {}
        self._accessory_generation = 0
        self._accessory_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._buddy_catalog: dict[str, Accessory] | None = None
        self._buddy_retry_at = 0.0
        self._buddy_catalog_lock = asyncio.Lock()
        self._mission_definitions: dict[str, dict[str, Any]] = {}
        self._mission_metadata_loaded_at: float | None = None
        self._mission_metadata_retry_at = 0.0
        self._mission_metadata_lock = asyncio.Lock()
        self._game_documents: dict[str, tuple[float, Any]] = {}
        self._game_document_retry_at: dict[str, float] = {}
        self._game_metadata_generation = 0
        self._game_document_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._game_metadata_path = ROOT / "data" / "game_metadata.json"
        self._game_metadata_documents: dict[str, dict[str, Any]] = {}
        self._game_metadata_loaded = False
        self._game_metadata_lock = asyncio.Lock()
        self.version = ""
        self._cache_format = 0
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        """Load the saved catalog off the event loop or fetch a fresh snapshot."""
        try:
            contents = await asyncio.to_thread(self.path.read_text, "utf-8")
            raw = json.loads(contents)
            self._deserialize(raw)
        except FileNotFoundError:
            await self.refresh()
            return
        except OSError, UnicodeError, ValueError:
            log.warning(
                "Cached VALORANT catalog is unreadable; fetching a fresh snapshot",
                exc_info=True,
            )
            await self.refresh()
            return
        if self._cache_format != CATALOG_FORMAT_VERSION:
            await self.refresh()

    async def _fetch_version(self) -> str:
        """Return the upstream catalog version used to detect a game patch."""
        version_response = await self.http.request(
            "GET", "https://valorant-api.com/v1/version"
        )
        version_data = (
            version_response.data.get("data")
            if isinstance(version_response.data, dict)
            else None
        )
        if version_response.status != 200 or not isinstance(version_data, dict):
            raise HTTPFailure("Invalid VALORANT catalog version response")
        current_version = (
            version_data.get("manifestId") or version_data.get("version") or ""
        )
        if not isinstance(current_version, str) or not current_version:
            raise HTTPFailure("Invalid VALORANT catalog version identifier")
        return current_version

    async def refresh(
        self, *, check_version: bool = False, version: str | None = None
    ) -> None:
        """Fetch the current weapon and bundle catalogs and save their snapshot.

        When ``check_version`` is true, skip rebuilding only if the upstream version
        and local cache format are current. A saved version change invalidates
        accessory metadata, including requests that began before the refresh.
        A failed save restores the previous catalog even during cancellation.
        ``version`` lets a caller reuse a version it already fetched.
        """
        async with self._lock:
            current_version = version or await self._fetch_version()
            if (
                check_version
                and current_version
                and current_version == self.version
                and self._cache_format == CATALOG_FORMAT_VERSION
                and self.skins
                and self.bundles
            ):
                return
            previous = (
                self.skins,
                self._skin_choices,
                self.bundles,
                self.skin_aliases,
                self.version,
                self._cache_format,
            )
            saved = False
            try:
                weapons = await self._fetch_data("weapons")
                bundles = await self._fetch_data("bundles")
                self._build(weapons, bundles)
                if not self.skins or not self.bundles:
                    raise HTTPFailure("VALORANT catalog contained no skins or bundles")
                self.version = current_version
                self._cache_format = CATALOG_FORMAT_VERSION
                snapshot = await asyncio.to_thread(self._serialize)
                write = asyncio.create_task(asyncio.to_thread(self._save, snapshot))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    completion = asyncio.gather(write, return_exceptions=True)
                    while not completion.done():
                        try:
                            await asyncio.shield(completion)
                        except asyncio.CancelledError:
                            continue
                    raise
                finally:
                    saved = (
                        write.done()
                        and not write.cancelled()
                        and write.exception() is None
                    )
                    if saved and current_version != previous[4]:
                        self._accessory_generation += 1
                        self._accessories.clear()
                        self._accessory_retry_at.clear()
                        self._buddy_catalog = None
                        self._buddy_retry_at = 0.0
                        await self._drop_game_metadata()
            except Exception, asyncio.CancelledError:
                if not saved:
                    (
                        self.skins,
                        self._skin_choices,
                        self.bundles,
                        self.skin_aliases,
                        self.version,
                        self._cache_format,
                    ) = previous
                raise

    async def _fetch_data(self, kind: str) -> list[dict[str, Any]]:
        """Fetch one catalog endpoint and return its validated data rows."""
        response = await self.http.request(
            "GET", f"https://valorant-api.com/v1/{kind}?language=all"
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise HTTPFailure(f"Could not fetch the {kind} catalog")
        data = response.data.get("data")
        if not isinstance(data, list) or not data:
            raise HTTPFailure(f"Invalid or empty {kind} catalog response")
        return _catalog_rows(data, kind)

    async def mission_metadata(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Cache mission definitions for 30 minutes and failed refreshes for 30 seconds."""
        if time.monotonic() < self._mission_metadata_retry_at or (
            self._mission_metadata_loaded_at is not None
            and time.monotonic() - self._mission_metadata_loaded_at
            < MISSION_METADATA_TTL
        ):
            return self._mission_definitions
        async with self._mission_metadata_lock:
            if time.monotonic() < self._mission_metadata_retry_at or (
                self._mission_metadata_loaded_at is not None
                and time.monotonic() - self._mission_metadata_loaded_at
                < MISSION_METADATA_TTL
            ):
                return self._mission_definitions
            try:
                missions = await self.http.request(
                    "GET",
                    "https://valorant-api.com/v1/missions?language=all",
                )
            except HTTPFailure:
                self._mission_metadata_retry_at = (
                    time.monotonic() + MISSION_METADATA_RETRY_SECONDS
                )
                log.warning("Could not refresh mission metadata", exc_info=True)
                return self._mission_definitions
            if (
                missions.status != 200
                or not isinstance(missions.data, dict)
                or not isinstance(missions.data.get("data"), list)
            ):
                self._mission_metadata_retry_at = (
                    time.monotonic() + MISSION_METADATA_RETRY_SECONDS
                )
                log.warning(
                    "Mission metadata was not 200 with a data list (status=%s)",
                    missions.status,
                )
                return self._mission_definitions
            self._mission_definitions = {
                str(item["uuid"]): {
                    "title": item.get("title"),
                    "displayName": item.get("displayName"),
                    "type": item.get("type"),
                    "xpGrant": item.get("xpGrant"),
                    "progressToComplete": item.get("progressToComplete"),
                    "objectives": item.get("objectives"),
                }
                for item in missions.data["data"]
                if isinstance(item, dict) and item.get("uuid")
            }
            self._mission_metadata_loaded_at = time.monotonic()
            self._mission_metadata_retry_at = 0.0
            return self._mission_definitions

    async def _game_document(
        self, key: str, endpoint: str, *, force: bool = False
    ) -> Any:
        """Return one game-metadata document, refetching it when stale or forced."""
        cached = self._game_documents.get(key)
        if not force and cached is not None and cached[0] > time.monotonic():
            return cached[1]
        await self._load_game_metadata()
        cached = self._game_documents.get(key)
        if not force and cached is not None and cached[0] > time.monotonic():
            return cached[1]
        async with self._game_document_locks.setdefault(key, asyncio.Lock()):
            cached = self._game_documents.get(key)
            now = time.monotonic()
            if not force and cached is not None and cached[0] > now:
                return cached[1]
            if now < self._game_document_retry_at.get(key, 0.0):
                return cached[1] if cached is not None else None
            generation = self._game_metadata_generation
            try:
                response = await self.http.request(
                    "GET", f"https://valorant-api.com/v1/{endpoint}?language=all"
                )
            except HTTPFailure:
                self._game_document_retry_at[key] = now + GAME_METADATA_RETRY_SECONDS
                log.warning("Could not refresh %s metadata", endpoint, exc_info=True)
                # Serve the stale copy rather than blanking the card.
                return cached[1] if cached is not None else None
            data = (
                response.data.get("data")
                if response.status == 200 and isinstance(response.data, dict)
                else None
            )
            if not isinstance(data, list) or not data:
                self._game_document_retry_at[key] = now + GAME_METADATA_RETRY_SECONDS
                log.warning("%s metadata was not a non-empty data list", endpoint)
                return cached[1] if cached is not None else None
            if generation != self._game_metadata_generation:
                # A game patch dropped the cache while this request was running.
                return None
            self._game_documents[key] = (now + GAME_METADATA_TTL, data)
            self._game_document_retry_at.pop(key, None)
            await self._save_game_metadata(key, data, generation)
            return data

    async def _load_game_metadata(self) -> None:
        """Prefill the game-metadata cache from the saved snapshot."""
        if self._game_metadata_loaded:
            return
        async with self._game_metadata_lock:
            if self._game_metadata_loaded:
                return
            self._game_metadata_loaded = True
            try:
                raw = json.loads(
                    await asyncio.to_thread(self._game_metadata_path.read_text, "utf-8")
                )
            except OSError, ValueError:
                return
            documents = raw.get("documents") if isinstance(raw, dict) else None
            if not isinstance(documents, dict):
                return
            now = time.time()
            for key, entry in documents.items():
                if not isinstance(entry, dict):
                    continue
                fetched_at = entry.get("fetched_at")
                data = entry.get("data")
                if (
                    not isinstance(fetched_at, (int, float))
                    or not isinstance(data, list)
                    or not data
                ):
                    continue
                age = now - fetched_at
                if age < 0 or age >= GAME_METADATA_MAX_AGE:
                    continue
                self._game_metadata_documents[key] = entry
                self._game_documents[key] = (
                    time.monotonic() + (GAME_METADATA_MAX_AGE - age),
                    data,
                )

    async def _save_game_metadata(
        self, key: str, data: list[dict[str, Any]], generation: int
    ) -> None:
        """Persist one game-metadata document unless a patch dropped it meanwhile."""
        async with self._game_metadata_lock:
            if generation != self._game_metadata_generation:
                return
            self._game_metadata_documents[key] = {
                "fetched_at": time.time(),
                "data": data,
            }
            payload = json.dumps(
                {"documents": self._game_metadata_documents}, separators=(",", ":")
            )
            try:
                await asyncio.to_thread(self._write_game_metadata, payload)
            except OSError:
                log.warning("Could not save VALORANT game metadata", exc_info=True)

    def _write_game_metadata(self, payload: str) -> None:
        """Write the game-metadata snapshot through a temporary file replacement."""
        self._game_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._game_metadata_path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, self._game_metadata_path)

    def _unlink_game_metadata(self) -> None:
        """Remove the saved game-metadata snapshot when it is no longer valid."""
        self._game_metadata_path.unlink(missing_ok=True)

    async def _drop_game_metadata(self) -> None:
        """Forget game metadata so a game patch refreshes it on next use."""
        async with self._game_metadata_lock:
            self._game_metadata_generation += 1
            self._game_documents.clear()
            self._game_metadata_documents.clear()
            self._game_metadata_loaded = True
            try:
                await asyncio.to_thread(self._unlink_game_metadata)
            except OSError:
                log.warning("Could not drop saved game metadata", exc_info=True)

    async def refresh_game_metadata(self) -> None:
        """Refetch every game-metadata document for the version refresh."""
        await asyncio.gather(
            *(
                self._game_document(key, endpoint, force=True)
                for key, endpoint in GAME_METADATA_DOCUMENTS
            )
        )

    async def ranks(self) -> dict[int, dict[str, str]]:
        """Return competitive tier numbers mapped to their localized names."""
        rows = await self._game_document("competitivetiers", "competitivetiers")
        if not isinstance(rows, list):
            return {}
        latest = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and isinstance(row.get("tiers"), list)
            ),
            None,
        )
        if latest is None:
            return {}
        ranks: dict[int, dict[str, str]] = {}
        for tier in latest["tiers"]:
            if not isinstance(tier, dict):
                continue
            number = tier.get("tier")
            if isinstance(number, bool) or not isinstance(number, int):
                continue
            names = _localized_values(tier.get("tierName"))
            if names:
                ranks[number] = names
        return ranks

    async def maps(self) -> dict[str, dict[str, str]]:
        """Return map asset paths and identifiers mapped to localized names."""
        rows = await self._game_document("maps", "maps")
        if not isinstance(rows, list):
            return {}
        maps: dict[str, dict[str, str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            names = _localized_values(row.get("displayName"))
            if not names:
                continue
            for key in (row.get("mapUrl"), row.get("uuid")):
                if isinstance(key, str) and key:
                    maps[key.casefold()] = names
        return maps

    async def current_act(self) -> tuple[str, dict[str, str]] | None:
        """Return the running act's identifier and localized names, if known."""
        rows = await self._game_document("seasons", "seasons")
        if not isinstance(rows, list):
            return None
        now = datetime.now(UTC)
        active: tuple[datetime, dict[str, Any]] | None = None
        for row in rows:
            if not isinstance(row, dict) or row.get("type") != "EAresSeasonType::Act":
                continue
            start = parse_datetime(row.get("startTime"))
            end = parse_datetime(row.get("endTime"))
            if (
                start is None
                or end is None
                or not isinstance(row.get("uuid"), str)
                or not start <= now < end
            ):
                continue
            if active is None or start > active[0]:
                active = (start, row)
        if active is None:
            return None
        act = active[1]
        parents = {
            row["uuid"]: row
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("uuid"), str)
        }
        parent = parents.get(act.get("parentUuid"))
        parent_names = (
            _localized_values(parent.get("displayName"))
            if isinstance(parent, dict)
            else {}
        )
        return act["uuid"], _combined_names(
            parent_names, _localized_values(act.get("displayName"))
        )

    def _build(
        self,
        weapons: list[dict[str, Any]],
        bundles: list[dict[str, Any]],
    ) -> None:
        """Normalize weapon and bundle responses and rebuild lookup indexes."""
        skin_map: dict[str, Skin] = {}
        for weapon in _catalog_rows(weapons, "weapons"):
            for raw in _catalog_rows(weapon.get("skins"), "skins"):
                if not raw.get("uuid"):
                    raise HTTPFailure("Missing catalog skin identifier")
                levels = _catalog_rows(raw.get("levels"), "levels")
                chromas = _catalog_rows(raw.get("chromas"), "chromas")
                offer_uuid = str(
                    (levels[0] if levels else {}).get("uuid") or raw.get("uuid")
                )
                uuid = str(raw.get("uuid"))
                names = _localized_values(raw.get("displayName"))
                skin_map[uuid] = Skin(
                    uuid=uuid,
                    offer_uuid=offer_uuid,
                    name=localized_text(names, ENGLISH_LOCALE) or uuid,
                    icon=raw.get("displayIcon")
                    or (levels[0] if levels else {}).get("displayIcon"),
                    tier_uuid=raw.get("contentTierUuid"),
                    levels=levels,
                    chromas=chromas,
                    names=names,
                )
        bundle_map: dict[str, Bundle] = {}
        for raw in _catalog_rows(bundles, "bundles"):
            if not raw.get("uuid"):
                raise HTTPFailure("Missing catalog bundle identifier")
            names = _localized_values(raw.get("displayName"))
            subtitles = _localized_values(raw.get("displayNameSubText"))
            descriptions = _localized_values(
                raw.get("description") or raw.get("extraDescription")
            )
            uuid = str(raw["uuid"])
            bundle_map[uuid] = Bundle(
                uuid=uuid,
                name=localized_text(names, ENGLISH_LOCALE) or uuid,
                subtitle=localized_text(subtitles, ENGLISH_LOCALE) or None,
                description=localized_text(descriptions, ENGLISH_LOCALE) or None,
                icon=raw.get("displayIcon")
                or raw.get("displayIcon2")
                or raw.get("verticalPromoImage"),
                names=names,
                subtitles=subtitles,
                descriptions=descriptions,
            )
        self.skins = skin_map
        self.bundles = bundle_map
        self._reindex()

    def _reindex(self) -> None:
        """Index skins by their UUID, offer UUID, and level UUID aliases."""
        self._skin_choices = {skin.uuid: skin.name for skin in self.skins.values()}
        self.skin_aliases = {}
        for skin in self.skins.values():
            self.skin_aliases[skin.uuid] = skin
            self.skin_aliases[skin.offer_uuid] = skin
            for level in skin.levels:
                if level.get("uuid"):
                    self.skin_aliases[str(level["uuid"])] = skin

    def get_skin(self, uuid: str) -> Skin | None:
        """Resolve a skin from any indexed base, offer, or level identifier."""
        return self.skin_aliases.get(str(uuid))

    def get_bundle(self, uuid: str) -> Bundle | None:
        """Resolve bundle metadata by its Riot UUID."""
        identifier = str(uuid)
        return self.bundles.get(identifier) or self.bundles.get(identifier.lower())

    async def accessory(self, item_type: str, uuid: str) -> Accessory | None:
        """Fetch and cache a supported accessory using its Riot item type ID."""
        if item_type.lower() == BUDDY_ITEM_TYPE_ID:
            return await self._buddy_accessory(uuid)
        endpoints = {
            SPRAY_ITEM_TYPE_ID: "sprays",
            PLAYER_CARD_ITEM_TYPE_ID: "playercards",
            PLAYER_TITLE_ITEM_TYPE_ID: "playertitles",
            FLEX_ITEM_TYPE_ID: "flex",
        }
        endpoint = endpoints.get(item_type.lower())
        key = (endpoint or "", uuid)
        if key in self._accessories:
            return self._accessories[key]
        if not endpoint:
            return None
        async with self._accessory_locks.setdefault(key, asyncio.Lock()):
            if key in self._accessories:
                return self._accessories[key]
            if time.monotonic() < self._accessory_retry_at.get(key, 0.0):
                raise HTTPFailure("Could not fetch accessory metadata")
            generation = self._accessory_generation
            try:
                response = await self.http.request(
                    "GET",
                    f"https://valorant-api.com/v1/{endpoint}/{uuid}?language=all",
                )
                if response.status == 404:
                    accessory = None
                else:
                    if response.status != 200 or not isinstance(response.data, dict):
                        raise HTTPFailure("Could not fetch accessory metadata")
                    raw = response.data.get("data")
                    if not isinstance(raw, dict):
                        raise HTTPFailure("Invalid accessory metadata")
                    accessory = self._accessory_from_data(endpoint, raw)
            except HTTPFailure:
                if generation == self._accessory_generation:
                    self._accessory_retry_at[key] = (
                        time.monotonic() + ACCESSORY_METADATA_RETRY_SECONDS
                    )
                raise
            if generation == self._accessory_generation:
                self._accessories[key] = accessory
                self._accessory_retry_at.pop(key, None)
            return accessory

    async def _buddy_accessory(self, uuid: str) -> Accessory | None:
        """Resolve a Riot bundle buddy by its buddy or level UUID."""
        identifier = str(uuid).lower()
        if self._buddy_catalog is None:
            async with self._buddy_catalog_lock:
                if self._buddy_catalog is None:
                    if time.monotonic() < self._buddy_retry_at:
                        raise HTTPFailure("Could not fetch the gun buddy catalog")
                    generation = self._accessory_generation
                    try:
                        response = await self.http.request(
                            "GET",
                            "https://valorant-api.com/v1/buddies?language=all",
                        )
                        rows = (
                            response.data.get("data")
                            if response.status == 200
                            and isinstance(response.data, dict)
                            else None
                        )
                        if not isinstance(rows, list):
                            raise HTTPFailure("Could not fetch the gun buddy catalog")
                        buddies: dict[str, Accessory] = {}
                        for buddy in _catalog_rows(rows, "buddies"):
                            names = _localized_values(buddy.get("displayName"))
                            name = localized_text(names, ENGLISH_LOCALE)
                            base_icon = buddy.get("displayIcon")
                            buddy_uuid = str(buddy.get("uuid") or "")
                            if buddy_uuid:
                                buddies[buddy_uuid.lower()] = Accessory(
                                    name, base_icon, names=names
                                )
                            for level in _catalog_rows(
                                buddy.get("levels"), "buddy levels"
                            ):
                                if not level.get("uuid"):
                                    continue
                                buddies[str(level["uuid"]).lower()] = Accessory(
                                    name,
                                    level.get("displayIcon") or base_icon,
                                    names=names,
                                )
                        if not buddies:
                            raise HTTPFailure("Gun buddy catalog contained no entries")
                    except HTTPFailure:
                        if generation == self._accessory_generation:
                            self._buddy_retry_at = (
                                time.monotonic() + ACCESSORY_METADATA_RETRY_SECONDS
                            )
                        raise
                    if generation == self._accessory_generation:
                        self._buddy_catalog = buddies
                        self._buddy_retry_at = 0.0
                    return buddies.get(identifier)
        return self._buddy_catalog.get(identifier)

    @staticmethod
    def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory:
        """Convert endpoint-specific Riot accessory data into a common display shape."""
        _catalog_rows([raw], endpoint)
        names = _localized_values(raw.get("displayName"))
        name = localized_text(names, ENGLISH_LOCALE)
        if endpoint == "playercards":
            return Accessory(
                name,
                raw.get("largeArt") or raw.get("wideArt"),
                names=names,
                small_icon=raw.get("smallArt"),
            )
        if endpoint == "playertitles":
            title_texts = _localized_values(raw.get("titleText"))
            return Accessory(
                name,
                None,
                localized_text(title_texts, ENGLISH_LOCALE) or None,
                names=names,
                title_texts=title_texts,
            )
        return Accessory(
            name,
            raw.get("fullTransparentIcon") or raw.get("displayIcon"),
            names=names,
        )

    def search_skins(
        self,
        query: str,
        *,
        locale: object | None = None,
        limit: int = 25,
        min_score: int = 35,
    ) -> list[Skin]:
        """Search localized names first, retaining English-name fallback matches.

        Names are compared case-insensitively; ``min_score`` is the lowest
        fuzzy-match score accepted, and an exactly matching name scores 100.
        """
        locale_code = getattr(locale, "value", locale)
        locale_code = str(locale_code) if locale_code else ENGLISH_LOCALE
        valorant_locale = DISCORD_TO_VALORANT_LOCALE.get(locale_code, ENGLISH_LOCALE)
        choices = {uuid: skin.name_for(locale) for uuid, skin in self.skins.items()}
        choice_sets = [choices]
        if valorant_locale != ENGLISH_LOCALE:
            choice_sets.append(self._skin_choices)

        scores: dict[str, float] = {}
        for search_choices in choice_sets:
            for _, score, uuid in process.extract(
                query,
                search_choices,
                scorer=fuzz.WRatio,
                processor=utils.default_process,
                limit=limit,
            ):
                if score >= min_score:
                    scores[uuid] = max(score, scores.get(uuid, 0))
        matches = sorted(scores.items(), key=lambda match: match[1], reverse=True)
        return [self.skins[uuid] for uuid, _ in matches[:limit]]

    def update_prices(self, prices: dict[str, int]) -> None:
        """Apply current store prices to catalog skins matched by offer identifier."""
        for offer_id, price in prices.items():
            skin = self.get_skin(offer_id)
            if skin:
                skin.price = price

    def _serialize(self) -> str:
        """Encode the current version, skins, and bundles as compact JSON."""
        payload = {
            "format_version": CATALOG_FORMAT_VERSION,
            "version": self.version,
            "skins": [asdict(skin) for skin in self.skins.values()],
            "bundles": [asdict(bundle) for bundle in self.bundles.values()],
        }
        return json.dumps(payload, separators=(",", ":"))

    def _save(self, snapshot: str) -> None:
        """Write a complete catalog snapshot through a temporary file replacement."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(snapshot, "utf-8")
        os.replace(temporary, self.path)

    def _deserialize(self, raw: dict[str, Any]) -> None:
        """Restore catalog records from a snapshot and rebuild lookup indexes."""
        if not isinstance(raw, dict):
            raise ValueError("Invalid catalog snapshot")
        version = raw.get("version", "")
        cache_format = raw.get("format_version", 0)
        if not isinstance(version, str) or type(cache_format) is not int:
            raise ValueError("Invalid catalog version")
        for kind, identifiers in (
            ("skins", ("uuid", "offer_uuid")),
            ("bundles", ("uuid",)),
        ):
            rows = raw.get(kind, [])
            if not isinstance(rows, list) or _invalid_snapshot_rows(rows, identifiers):
                raise ValueError(f"Invalid catalog {kind}")
            if not rows and (kind == "skins" or cache_format == CATALOG_FORMAT_VERSION):
                raise ValueError(f"Empty catalog {kind}")
        self.skins = {
            row["uuid"]: _skin_from_snapshot(row) for row in raw.get("skins", [])
        }
        self.bundles = {
            row["uuid"]: _bundle_from_snapshot(row) for row in raw.get("bundles", [])
        }
        self.version, self._cache_format = version, cache_format
        self._reindex()
