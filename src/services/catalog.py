"""VALORANT skin, bundle, accessory, and mission metadata with a local cache."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from .http import HTTPClient, HTTPFailure

ENGLISH_LOCALE = "en-US"
MISSION_METADATA_TTL = 1800
CATALOG_FORMAT_VERSION = 4
BUDDY_ITEM_TYPE_ID = "dd3bf334-87f3-40bd-b043-682a57a8dc3a"
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

    def name_for(self, locale: object | None = None) -> str:
        """Return this accessory's localized name, or empty when metadata is missing."""
        return localized_text(self.names, locale) or self.name

    def title_text_for(self, locale: object | None = None) -> str | None:
        """Return localized accessory title text, if available."""
        return (
            localized_text(self.title_texts or self.title_text, locale)
            or self.title_text
        )


class CatalogService:
    """Load, refresh, search, and cache VALORANT catalog data."""

    def __init__(self, http: HTTPClient) -> None:
        """Prepare in-memory indexes and the working-directory catalog snapshot."""
        self.http = http
        self.path = Path.cwd() / "data" / "skins.json"
        self.skins: dict[str, Skin] = {}
        self._skin_choices: dict[str, str] = {}
        self.bundles: dict[str, Bundle] = {}
        self.skin_aliases: dict[str, Skin] = {}
        self._accessories: dict[tuple[str, str], Accessory | None] = {}
        self._accessory_locks: defaultdict[tuple[str, str], asyncio.Lock] = defaultdict(
            asyncio.Lock
        )
        self._buddy_catalog: dict[str, Accessory] | None = None
        self._buddy_catalog_lock = asyncio.Lock()
        self._mission_definitions: dict[str, dict[str, Any]] = {}
        self._mission_metadata_loaded_at: float | None = None
        self._mission_metadata_lock = asyncio.Lock()
        self.version = ""
        self._cache_format = 0
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        """Load the saved catalog off the event loop or fetch a fresh snapshot."""
        try:
            contents = await asyncio.to_thread(self.path.read_text, "utf-8")
            raw = json.loads(contents)
        except FileNotFoundError, json.JSONDecodeError, OSError:
            await self.refresh()
            return
        self._deserialize(raw)
        if self._cache_format != CATALOG_FORMAT_VERSION:
            await self.refresh()

    async def refresh(self, *, check_version: bool = False) -> None:
        """Fetch the current weapon and bundle catalogs and save their snapshot.

        When ``check_version`` is true, skip rebuilding only if the upstream version
        and local cache format are current.
        """
        async with self._lock:
            version_response = await self.http.request(
                "GET", "https://valorant-api.com/v1/version"
            )
            version_data = (
                version_response.data.get("data", {})
                if isinstance(version_response.data, dict)
                else {}
            )
            current_version = (
                version_data.get("manifestId") or version_data.get("version") or ""
            )
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
            try:
                weapons = await self._fetch_data("weapons")
                bundles = await self._fetch_data("bundles")
                self._build(weapons, bundles)
                if not self.skins or not self.bundles:
                    raise HTTPFailure("VALORANT catalog contained no skins or bundles")
                self.version = current_version
                self._cache_format = CATALOG_FORMAT_VERSION
                snapshot = self._serialize()
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
            except Exception:
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
        return data

    async def mission_metadata(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Return cached mission definitions, refreshing them at most every 30 minutes."""
        if (
            self._mission_metadata_loaded_at is not None
            and time.monotonic() - self._mission_metadata_loaded_at
            < MISSION_METADATA_TTL
        ):
            return self._mission_definitions
        async with self._mission_metadata_lock:
            if (
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
                log.warning("Could not refresh mission metadata", exc_info=True)
                return self._mission_definitions
            if (
                missions.status != 200
                or not isinstance(missions.data, dict)
                or not isinstance(missions.data.get("data"), list)
            ):
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
            return self._mission_definitions

    def _build(
        self,
        weapons: list[dict[str, Any]],
        bundles: list[dict[str, Any]],
    ) -> None:
        """Normalize weapon and bundle responses and rebuild lookup indexes."""
        skin_map: dict[str, Skin] = {}
        for weapon in weapons:
            for raw in weapon.get("skins") or []:
                levels = raw.get("levels") or []
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
                    chromas=raw.get("chromas") or [],
                    names=names,
                )
        bundle_map: dict[str, Bundle] = {}
        for raw in bundles:
            if not isinstance(raw, dict) or not raw.get("uuid"):
                continue
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
            "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475": "sprays",
            "3f296c07-64c3-494c-923b-fe692a4fa1bd": "playercards",
            "de7caa6b-adf7-4588-bbd1-143831e786c6": "playertitles",
            "03a572de-4234-31ed-d344-ababa488f981": "flex",
        }
        endpoint = endpoints.get(item_type.lower())
        key = (endpoint or "", uuid)
        if key in self._accessories:
            return self._accessories[key]
        if not endpoint:
            return None
        async with self._accessory_locks[key]:
            if key in self._accessories:
                return self._accessories[key]
            response = await self.http.request(
                "GET",
                f"https://valorant-api.com/v1/{endpoint}/{uuid}?language=all",
            )
            if response.status == 404:
                self._accessories[key] = None
                return None
            if response.status != 200 or not isinstance(response.data, dict):
                return None
            raw = response.data.get("data")
            if not isinstance(raw, dict):
                return None
            self._accessories[key] = self._accessory_from_data(endpoint, raw)
            return self._accessories[key]

    async def _buddy_accessory(self, uuid: str) -> Accessory | None:
        """Resolve a Riot bundle buddy by its buddy or level UUID."""
        identifier = str(uuid).lower()
        if self._buddy_catalog is None:
            async with self._buddy_catalog_lock:
                if self._buddy_catalog is None:
                    response = await self.http.request(
                        "GET",
                        "https://valorant-api.com/v1/buddies?language=all",
                    )
                    rows = (
                        response.data.get("data")
                        if response.status == 200 and isinstance(response.data, dict)
                        else None
                    )
                    if not isinstance(rows, list):
                        raise HTTPFailure("Could not fetch the gun buddy catalog")
                    buddies: dict[str, Accessory] = {}
                    for buddy in rows:
                        if not isinstance(buddy, dict):
                            continue
                        names = _localized_values(buddy.get("displayName"))
                        name = localized_text(names, ENGLISH_LOCALE)
                        base_icon = buddy.get("displayIcon")
                        buddy_uuid = str(buddy.get("uuid") or "")
                        if buddy_uuid:
                            buddies[buddy_uuid.lower()] = Accessory(
                                name, base_icon, names=names
                            )
                        for level in buddy.get("levels") or []:
                            if not isinstance(level, dict) or not level.get("uuid"):
                                continue
                            buddies[str(level["uuid"]).lower()] = Accessory(
                                name,
                                level.get("displayIcon") or base_icon,
                                names=names,
                            )
                    if not buddies:
                        raise HTTPFailure("Gun buddy catalog contained no entries")
                    self._buddy_catalog = buddies
        return self._buddy_catalog.get(identifier)

    @staticmethod
    def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory:
        """Convert endpoint-specific Riot accessory data into a common display shape."""
        names = _localized_values(raw.get("displayName"))
        name = localized_text(names, ENGLISH_LOCALE)
        if endpoint == "playercards":
            return Accessory(
                name,
                raw.get("largeArt") or raw.get("wideArt"),
                names=names,
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
        self, query: str, *, locale: object | None = None, limit: int = 25
    ) -> list[Skin]:
        """Search localized names first, retaining English-name fallback matches."""
        locale_code = getattr(locale, "value", locale)
        locale_code = str(locale_code) if locale_code else ENGLISH_LOCALE
        valorant_locale = DISCORD_TO_VALORANT_LOCALE.get(locale_code, ENGLISH_LOCALE)
        choices = {uuid: skin.name_for(locale) for uuid, skin in self.skins.items()}
        choice_sets = [choices]
        if valorant_locale != ENGLISH_LOCALE:
            choice_sets.append(self._skin_choices)

        scores: dict[str, int] = {}
        for search_choices in choice_sets:
            for _, score, uuid in process.extract(
                query, search_choices, scorer=fuzz.WRatio, limit=limit
            ):
                if score >= 35:
                    scores[uuid] = max(score, scores.get(uuid, 0))
        matches = sorted(scores.items(), key=lambda match: match[1], reverse=True)
        return [self.skins[uuid] for uuid, _ in matches[:limit]]

    def update_prices(self, offers: list[dict[str, Any]]) -> None:
        """Apply current store prices to catalog skins matched by offer identifier."""
        for offer in offers:
            offer_id = str(
                offer.get("OfferID") or offer.get("Offer", {}).get("OfferID") or ""
            )
            cost = offer.get("Cost") or offer.get("Offer", {}).get("Cost") or {}
            skin = self.get_skin(offer_id)
            if skin and cost:
                skin.price = next(iter(cost.values()), skin.price)

    def _serialize(self) -> str:
        """Encode the current version, skins, and bundles as compact JSON."""
        payload = {
            "format_version": CATALOG_FORMAT_VERSION,
            "version": self.version,
            "skins": [
                {
                    "uuid": skin.uuid,
                    "offer_uuid": skin.offer_uuid,
                    "name": skin.name,
                    "names": skin.names,
                    "icon": skin.icon,
                    "tier_uuid": skin.tier_uuid,
                    "price": skin.price,
                    "levels": skin.levels,
                    "chromas": skin.chromas,
                }
                for skin in self.skins.values()
            ],
            "bundles": [
                {
                    "uuid": bundle.uuid,
                    "name": bundle.name,
                    "names": bundle.names,
                    "subtitle": bundle.subtitle,
                    "subtitles": bundle.subtitles,
                    "description": bundle.description,
                    "descriptions": bundle.descriptions,
                    "icon": bundle.icon,
                }
                for bundle in self.bundles.values()
            ],
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
        self.version = str(raw.get("version") or "")
        self._cache_format = int(raw.get("format_version") or 0)
        self.skins = {
            item["uuid"]: Skin(
                uuid=item["uuid"],
                offer_uuid=item["offer_uuid"],
                name=str(
                    item.get("name")
                    or localized_text(
                        item.get("names") or item.get("name"), ENGLISH_LOCALE
                    )
                    or item["uuid"]
                ),
                icon=item.get("icon"),
                tier_uuid=item.get("tier_uuid"),
                price=item.get("price"),
                levels=item.get("levels", []),
                chromas=item.get("chromas", []),
                names=_localized_values(item.get("names") or item.get("name")),
            )
            for item in raw.get("skins", [])
            if item.get("uuid") and item.get("offer_uuid")
        }
        self.bundles = {
            item["uuid"]: Bundle(
                uuid=item["uuid"],
                name=str(
                    item.get("name")
                    or localized_text(
                        item.get("names") or item.get("name"), ENGLISH_LOCALE
                    )
                    or item["uuid"]
                ),
                subtitle=item.get("subtitle")
                or localized_text(
                    item.get("subtitles") or item.get("subtitle"), ENGLISH_LOCALE
                )
                or None,
                description=item.get("description")
                or localized_text(
                    item.get("descriptions") or item.get("description"),
                    ENGLISH_LOCALE,
                )
                or None,
                icon=item.get("icon"),
                names=_localized_values(item.get("names") or item.get("name")),
                subtitles=_localized_values(
                    item.get("subtitles") or item.get("subtitle")
                ),
                descriptions=_localized_values(
                    item.get("descriptions") or item.get("description")
                ),
            )
            for item in raw.get("bundles", [])
            if item.get("uuid")
        }
        self._reindex()
