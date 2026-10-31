"""Fetch, decode, and encode a user's VALORANT crosshair profiles."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from weakref import WeakValueDictionary

from ..models import Account
from .auth import AuthenticationRequired, AuthService
from .crosshair_render import render_png
from .http import HTTPClient

log = logging.getLogger(__name__)

PLAYER_PREFERENCES_URL = (
    "https://player-preferences-usw2.pp.sgp.pvp.net"
    "/playerPref/v3/getPreference/Ares.PlayerSettings"
)
SAVED_PROFILE_KEY = "EAresStringSettingName::SavedCrosshairProfileData"
CACHE_TTL_SECONDS = 300
MAX_CACHE_ENTRIES = 500

PALETTE = (
    "FFFFFF",
    "00FF00",
    "7FFF00",
    "DFFF00",
    "FFFF00",
    "00FFFF",
    "FF00FF",
    "FF0000",
)
# defaults: length, thickness, offset, opacity, movement error, firing error
INNER = {"l": 6, "v": 6, "t": 2, "o": 3, "a": 0.8, "m": False, "f": True}
OUTER = {"l": 2, "v": 2, "t": 2, "o": 10, "a": 0.35, "m": True, "f": True}
# Key letters not yet confirmed against a real in-game code.
UNVERIFIED = {"s", "m", "0g", "0m", "1g", "1m", "A"}


class CrosshairUnavailable(RuntimeError):
    """Raised when Riot's crosshair settings cannot be loaded or decoded."""


@dataclass(frozen=True, slots=True)
class CrosshairProfile:
    """One crosshair profile and its import/export code."""

    index: int
    name: str
    code: str
    current: bool


@dataclass(slots=True)
class _CacheEntry:
    """Cached profiles tied to one account identity."""

    expires: float
    identity: tuple[int, datetime]
    profiles: list[CrosshairProfile] = field(default_factory=list)


def _hex(color: Mapping[str, Any], *, alpha: bool = False) -> str:
    """Format one RGBA colour mapping as an uppercase hex string."""
    value = f"{color['r']:02X}{color['g']:02X}{color['b']:02X}"
    return value + (f"{color['a']:02X}" if alpha else "")


def _fmt(value: Any) -> str:
    """Format a setting the same way the game writes it into a share code."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    rounded = round(float(value), 3)
    if rounded == int(rounded) and abs(float(value) - rounded) < 1e-12:
        return str(int(rounded))
    return repr(rounded)


class _Encoder:
    """Collect code tokens and warnings for one crosshair section."""

    def __init__(self) -> None:
        """Start an empty token list."""
        self.tokens: list[str] = []
        self.warnings: list[str] = []

    def put(self, key: str, value: object, default: object) -> None:
        """Emit ``key;value`` unless it equals the game's default."""
        if isinstance(default, bool) or isinstance(value, bool):
            differs = bool(value) != bool(default)
        else:
            differs = _fmt(value) != _fmt(default)
        if differs:
            self.tokens.extend((key, _fmt(value)))


def _color(
    encoder: _Encoder,
    color: Mapping[str, Any],
    custom: Mapping[str, Any],
    use_custom: bool,
    default_index: int,
) -> None:
    """Encode the colour index and custom colour of one crosshair section."""
    index = (
        8
        if use_custom
        else (PALETTE.index(_hex(color)) if _hex(color) in PALETTE else 8)
    )
    if index != default_index:
        encoder.tokens.extend(("c", str(index)))
    if index == 8 and _hex(custom, alpha=True) == "FFFFFFFF" and not use_custom:
        encoder.tokens.extend(("u", _hex(color, alpha=True)))
    elif _hex(custom, alpha=True) != "FFFFFFFF":
        encoder.tokens.extend(("u", _hex(custom, alpha=True)))


def _lines(
    encoder: _Encoder,
    group: Mapping[str, Any],
    prefix: str,
    defaults: Mapping[str, object],
) -> None:
    """Encode one set of inner or outer lines."""
    if not group["bShowLines"]:
        encoder.tokens.extend((prefix + "b", "0"))
        return
    encoder.put(prefix + "t", group["lineThickness"], defaults["t"])
    encoder.put(prefix + "l", group["lineLength"], defaults["l"])
    if group["bAllowVertScaling"]:
        encoder.tokens.extend((prefix + "g", "1"))
    encoder.put(prefix + "v", group["lineLengthVertical"], defaults["v"])
    encoder.put(prefix + "o", group["lineOffset"], defaults["o"])
    encoder.put(prefix + "a", group["opacity"], defaults["a"])
    encoder.put(prefix + "m", group["bShowMovementError"], defaults["m"])
    encoder.put(prefix + "f", group["bShowShootingError"], defaults["f"])
    if not group["bShowMinError"]:
        encoder.warnings.append(
            f"{prefix}: 'show minimum error' is off - key letter unknown"
        )
    for flag, scale, name in (
        ("bShowMovementError", "movementErrorScale", "movement"),
        ("bShowShootingError", "firingErrorScale", "firing"),
    ):
        if group[flag] and abs(group[scale] - 1) >= 0.002:
            encoder.warnings.append(
                f"{prefix}: {name} error multiplier {group[scale]:.3f} not encoded"
            )


def _crosshair(profile: Mapping[str, Any]) -> _Encoder:
    """Encode one primary, ADS, or focus-mode crosshair section."""
    encoder = _Encoder()
    _color(
        encoder,
        profile["color"],
        profile["colorCustom"],
        profile["bUseCustomColor"],
        0,
    )
    if not profile["bHasOutline"]:
        encoder.tokens.extend(("h", "0"))
    else:
        encoder.put("t", profile["outlineThickness"], 1)
        encoder.put("o", profile["outlineOpacity"], 0.5)
    if profile["bDisplayCenterDot"]:
        encoder.tokens.extend(("d", "1"))
        encoder.put("z", profile["centerDotSize"], 2)
        encoder.put("a", profile["centerDotOpacity"], 1)
    encoder.put("f", profile["bFadeCrosshairWithFiringError"], True)
    encoder.put("s", profile["bShowSpectatedPlayerCrosshair"], True)
    encoder.put("m", profile["bFixMinErrorAcrossWeapons"], False)
    if profile["bHideCrosshair"]:
        encoder.warnings.append("bHideCrosshair is on - key letter unknown")
    _lines(encoder, profile["innerLines"], "0", INNER)
    _lines(encoder, profile["outerLines"], "1", OUTER)
    return encoder


def profile_to_code(profile: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Encode one saved crosshair profile into a VALORANT share code."""
    warnings: list[str] = []
    parts = ["0"]
    if profile["bUseAdvancedOptions"]:
        parts.extend(("s", "1"))
    primary = _crosshair(profile["primary"])
    parts.extend(["P", *primary.tokens])
    warnings.extend(primary.warnings)
    used = set(primary.tokens[::2])
    if not profile["bUsePrimaryCrosshairForADS"]:
        ads = _crosshair(profile["aDS"])
        parts.extend(["A", *ads.tokens])
        warnings.extend(ads.warnings)
        warnings.append("ADS section encoded with the same keys as P - unverified")
    sniper = profile["sniper"]
    encoded = _Encoder()
    index = (
        8
        if sniper["bUseCustomCenterDotColor"]
        else (
            PALETTE.index(_hex(sniper["centerDotColor"]))
            if _hex(sniper["centerDotColor"]) in PALETTE
            else 8
        )
    )
    if index != 7:
        encoded.tokens.extend(("c", str(index)))
    if _hex(sniper["centerDotColorCustom"], alpha=True) != "FFFFFFFF":
        encoded.tokens.extend(("u", _hex(sniper["centerDotColorCustom"], alpha=True)))
    encoded.put("s", sniper["centerDotSize"], 1)
    encoded.put("o", sniper["centerDotOpacity"], 0.75)
    if not sniper["bDisplayCenterDot"]:
        warnings.append("sniper dot is hidden - key letter unknown, not encoded")
    if encoded.tokens:
        parts.extend(["S", *encoded.tokens])
    unverified = sorted(used & UNVERIFIED)
    if unverified:
        warnings.append("unverified key letters emitted: " + ", ".join(unverified))
    return ";".join(parts), warnings


def decode_settings(body: Any) -> dict[str, Any]:
    """Decode Riot's base64 and zlib player-preferences payload into JSON."""
    if not isinstance(body, dict) or not isinstance(body.get("data"), str):
        raise CrosshairUnavailable("Player preferences payload is malformed")
    encoded = body["data"]
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as exc:
        raise CrosshairUnavailable("Player preferences are not valid base64") from exc
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, 16 + zlib.MAX_WBITS):
        try:
            decoded = zlib.decompress(raw, wbits)
        except zlib.error:
            continue
        try:
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CrosshairUnavailable("Player preferences are not valid JSON") from exc
        if not isinstance(value, dict):
            raise CrosshairUnavailable("Player preferences have an invalid shape")
        return value
    raise CrosshairUnavailable("Player preferences are not compressed")


def profiles_from_settings(settings: Mapping[str, Any]) -> list[CrosshairProfile]:
    """Extract and encode every saved crosshair profile."""
    entries = settings.get("stringSettings")
    if not isinstance(entries, list):
        raise CrosshairUnavailable("Player preferences have no string settings")
    value: str | None = None
    for entry in entries:
        if (
            isinstance(entry, dict)
            and entry.get("settingEnum") == SAVED_PROFILE_KEY
            and isinstance(entry.get("value"), str)
        ):
            value = entry["value"]
            break
    if value is None:
        raise CrosshairUnavailable("No saved crosshair profiles were found")
    try:
        saved = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CrosshairUnavailable(
            "Saved crosshair profiles are not valid JSON"
        ) from exc
    if not isinstance(saved, dict) or not isinstance(saved.get("profiles"), list):
        raise CrosshairUnavailable("Saved crosshair profiles have an invalid shape")
    current = saved.get("currentProfile")
    profiles: list[CrosshairProfile] = []
    for index, profile in enumerate(saved["profiles"]):
        if not isinstance(profile, dict):
            raise CrosshairUnavailable("A crosshair profile has an invalid shape")
        try:
            code, warnings = profile_to_code(profile)
        except (KeyError, TypeError, ValueError) as exc:
            raise CrosshairUnavailable(
                "A crosshair profile could not be encoded"
            ) from exc
        name = profile.get("profileName")
        for warning in warnings:
            log.debug("Crosshair profile %s: %s", index, warning)
        profiles.append(
            CrosshairProfile(
                index=index,
                name=name if isinstance(name, str) and name else f"Profile {index}",
                code=code,
                current=index == current,
            )
        )
    if not profiles:
        raise CrosshairUnavailable("No saved crosshair profiles were found")
    if not any(profile.current for profile in profiles):
        profiles[0] = CrosshairProfile(
            index=profiles[0].index,
            name=profiles[0].name,
            code=profiles[0].code,
            current=True,
        )
    return profiles


class CrosshairService:
    """Fetch crosshair profiles from Riot and encode them for the command."""

    def __init__(
        self,
        auth: AuthService,
        http: HTTPClient,
        *,
        ttl: float = CACHE_TTL_SECONDS,
    ) -> None:
        """Bind the authentication and HTTP services and start an empty cache."""
        self.auth = auth
        self.http = http
        self.ttl = ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def profiles(
        self, account: Account, *, refresh: bool = False
    ) -> list[CrosshairProfile]:
        """Return encoded profiles, reusing or refreshing the account's cache."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            now = time.monotonic()
            identity = (account.user_id, account.created_at)
            cached = self._cache.get(account.puuid)
            if (
                not refresh
                and cached is not None
                and cached.expires > now
                and cached.identity == identity
            ):
                return cached.profiles
            headers = await self.auth.auth_headers(account)
            result = await self.http.request(
                "GET", PLAYER_PREFERENCES_URL, headers=headers
            )
            if result.status in {401, 403}:
                raise AuthenticationRequired("Riot login is required")
            if result.status != 200:
                raise CrosshairUnavailable(
                    f"Player preferences returned HTTP {result.status}"
                )
            profiles = profiles_from_settings(decode_settings(result.data))
            self._cache[account.puuid] = _CacheEntry(
                expires=now + self.ttl, identity=identity, profiles=profiles
            )
            self._prune(now)
            return profiles

    def render_png(self, profile: CrosshairProfile) -> bytes:
        """Render one encoded profile to PNG bytes."""
        return render_png(profile.code)

    def invalidate(self, puuid: str) -> None:
        """Drop a cached account after logout or credential changes."""
        self._cache.pop(puuid, None)

    def _prune(self, now: float) -> None:
        """Drop expired entries and bound the cache size."""
        for key, entry in list(self._cache.items()):
            if entry.expires <= now:
                del self._cache[key]
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.pop(next(iter(self._cache)))
