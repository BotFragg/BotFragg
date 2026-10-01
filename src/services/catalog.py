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
CATALOG_FORMAT_VERSION = 3
BUDDY_ITEM_TYPE_ID = "dd3bf334-87f3-40bd-b043-682a57a8dc3a"

log = logging.getLogger(__name__)


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


@dataclass(slots=True)
class Bundle:
    """Hold static display metadata for a VALORANT bundle."""

    uuid: str
    name: str
    subtitle: str | None
    description: str | None
    icon: str | None


@dataclass(slots=True)
class Accessory:
    """Hold normalized display data for a non-skin cosmetic reward."""

    name: str
    icon: str | None
    title_text: str | None = None


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
            "GET", f"https://valorant-api.com/v1/{kind}?language={ENGLISH_LOCALE}"
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
                    f"https://valorant-api.com/v1/missions?language={ENGLISH_LOCALE}",
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
                skin_map[uuid] = Skin(
                    uuid=uuid,
                    offer_uuid=offer_uuid,
                    name=str(raw.get("displayName") or uuid),
                    icon=raw.get("displayIcon")
                    or (levels[0] if levels else {}).get("displayIcon"),
                    tier_uuid=raw.get("contentTierUuid"),
                    levels=levels,
                    chromas=raw.get("chromas") or [],
                )
        bundle_map = {
            str(raw["uuid"]): Bundle(
                uuid=str(raw["uuid"]),
                name=str(raw.get("displayName") or raw["uuid"]),
                subtitle=raw.get("displayNameSubText"),
                description=raw.get("description") or raw.get("extraDescription"),
                icon=raw.get("displayIcon")
                or raw.get("displayIcon2")
                or raw.get("verticalPromoImage"),
            )
            for raw in bundles
            if isinstance(raw, dict) and raw.get("uuid")
        }
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
                f"https://valorant-api.com/v1/{endpoint}/{uuid}?language={ENGLISH_LOCALE}",
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
                        f"https://valorant-api.com/v1/buddies?language={ENGLISH_LOCALE}",
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
                        name = str(buddy.get("displayName") or "Unknown Buddy")
                        base_icon = buddy.get("displayIcon")
                        buddy_uuid = str(buddy.get("uuid") or "")
                        if buddy_uuid:
                            buddies[buddy_uuid.lower()] = Accessory(name, base_icon)
                        for level in buddy.get("levels") or []:
                            if not isinstance(level, dict) or not level.get("uuid"):
                                continue
                            buddies[str(level["uuid"]).lower()] = Accessory(
                                name, level.get("displayIcon") or base_icon
                            )
                    if not buddies:
                        raise HTTPFailure("Gun buddy catalog contained no entries")
                    self._buddy_catalog = buddies
        return self._buddy_catalog.get(identifier)

    @staticmethod
    def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory:
        """Convert endpoint-specific Riot accessory data into a common display shape."""
        if endpoint == "playercards":
            return Accessory(
                str(raw.get("displayName") or "Unknown Card"),
                raw.get("largeArt") or raw.get("wideArt"),
            )
        if endpoint == "playertitles":
            return Accessory(
                str(raw.get("displayName") or "Unknown Title"),
                None,
                raw.get("titleText"),
            )
        return Accessory(
            str(raw.get("displayName") or "Unknown Accessory"),
            raw.get("fullTransparentIcon") or raw.get("displayIcon"),
        )

    def search_skins(self, query: str, *, limit: int = 25) -> list[Skin]:
        """Return fuzzy name matches whose weighted score is at least 35."""
        return [
            self.skins[uuid]
            for _, score, uuid in process.extract(
                query, self._skin_choices, scorer=fuzz.WRatio, limit=limit
            )
            if score >= 35
        ]

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
                    "subtitle": bundle.subtitle,
                    "description": bundle.description,
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
                name=item.get("name")
                or item.get("names", {}).get(ENGLISH_LOCALE)
                or item["uuid"],
                icon=item.get("icon"),
                tier_uuid=item.get("tier_uuid"),
                price=item.get("price"),
                levels=item.get("levels", []),
                chromas=item.get("chromas", []),
            )
            for item in raw.get("skins", [])
            if item.get("uuid") and item.get("offer_uuid")
        }
        self.bundles = {
            item["uuid"]: Bundle(
                uuid=item["uuid"],
                name=item.get("name") or item["uuid"],
                subtitle=item.get("subtitle"),
                description=item.get("description"),
                icon=item.get("icon"),
            )
            for item in raw.get("bundles", [])
            if item.get("uuid")
        }
        self._reindex()
