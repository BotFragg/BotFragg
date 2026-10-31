"""Crosshair payload decoding, encoding, caching, and service errors."""

from __future__ import annotations

import base64
import json
import zlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import crosshair as crosshair_module
from src.services.auth import AuthenticationRequired
from src.services.crosshair import (
    CrosshairService,
    CrosshairUnavailable,
    decode_settings,
    profile_to_code,
    profiles_from_settings,
)
from src.services.http import HTTPResult


def line_group(
    thickness: int = 1,
    length: int = 2,
    offset: int = 2,
    shown: bool = True,
) -> dict[str, object]:
    """Build one inner or outer line group."""
    return {
        "lineThickness": thickness,
        "lineLength": length,
        "lineLengthVertical": length,
        "lineOffset": offset,
        "bAllowVertScaling": False,
        "bShowMovementError": False,
        "bShowShootingError": True,
        "bShowMinError": True,
        "opacity": 1,
        "bShowLines": shown,
        "firingErrorScale": 1,
        "movementErrorScale": 1,
    }


def saved_profile(name: str, color: int = 255) -> dict[str, object]:
    """Build one minimally valid saved crosshair profile."""
    return {
        "profileName": name,
        "bUseAdvancedOptions": False,
        "bUsePrimaryCrosshairForADS": True,
        "aDS": None,
        "primary": {
            "color": {"r": color, "g": 255, "b": 255, "a": 255},
            "colorCustom": {"r": 0, "g": 0, "b": 0, "a": 255},
            "bUseCustomColor": False,
            "bHasOutline": False,
            "outlineThickness": 1,
            "outlineOpacity": 1,
            "bDisplayCenterDot": False,
            "centerDotSize": 2,
            "centerDotOpacity": 1,
            "bFadeCrosshairWithFiringError": True,
            "bShowSpectatedPlayerCrosshair": True,
            "bHideCrosshair": False,
            "bFixMinErrorAcrossWeapons": False,
            "innerLines": line_group(),
            "outerLines": line_group(shown=False),
        },
        "sniper": {
            "centerDotColor": {"r": 255, "g": 255, "b": 255, "a": 255},
            "centerDotColorCustom": {"r": 255, "g": 255, "b": 255, "a": 255},
            "centerDotSize": 1,
            "centerDotOpacity": 0.75,
            "bDisplayCenterDot": True,
            "bUseCustomCenterDotColor": False,
        },
    }


def settings(profiles: list[dict[str, object]], current: int = 0) -> dict[str, object]:
    """Wrap saved profiles in the shape Riot stores them in."""
    return {
        "stringSettings": [
            {
                "settingEnum": "EAresStringSettingName::SavedCrosshairProfileData",
                "value": json.dumps({"currentProfile": current, "profiles": profiles}),
            }
        ]
    }


def body(value: dict[str, object]) -> dict[str, str]:
    """Encode a settings mapping the way the player-preferences endpoint does."""
    compressed = zlib.compress(json.dumps(value).encode())
    return {"data": base64.b64encode(compressed).decode()}


def account(**overrides: object) -> SimpleNamespace:
    """Build one account with a stable ownership identity."""
    values = {
        "puuid": "synthetic",
        "user_id": 1,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def service() -> tuple[CrosshairService, AsyncMock, AsyncMock]:
    """Build a service with fake auth and HTTP dependencies."""
    auth = AsyncMock()
    auth.auth_headers = AsyncMock(return_value={"Authorization": "synthetic"})
    http = AsyncMock()
    return CrosshairService(auth, http), auth, http


def test_profiles_from_settings_encodes_every_profile():
    """Each saved profile must be encoded and marked with its current flag."""
    profiles = [saved_profile("one"), saved_profile("two", 0)]
    result = profiles_from_settings(settings(profiles, current=1))

    assert [profile.name for profile in result] == ["one", "two"]
    assert [profile.current for profile in result] == [False, True]
    assert [profile.code for profile in result] == [
        profile_to_code(profile)[0] for profile in profiles
    ]


def test_missing_or_out_of_range_current_falls_back_to_the_first_profile():
    """A stale current index must not leave the view without a selection."""
    result = profiles_from_settings(settings([saved_profile("only")], current=7))
    assert result[0].current


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"data": "not base64 or zlib"},
        {"data": base64.b64encode(b"plain text").decode()},
        {"data": base64.b64encode(zlib.compress(b"[]")).decode()},
    ],
)
def test_decode_settings_rejects_malformed_payloads(payload):
    """Malformed player-preferences payloads must map to one service error."""
    with pytest.raises(CrosshairUnavailable):
        decode_settings(payload)


def test_decode_settings_accepts_the_riot_encoding():
    """The base64 + zlib encoding used by Riot must round-trip."""
    value = {"currentProfile": 0, "profiles": []}
    assert decode_settings(body(value)) == value


async def test_service_caches_and_invalidates():
    """A fresh cache entry must avoid a second Riot request."""
    service_instance, _auth, http = service()
    http.request = AsyncMock(
        return_value=HTTPResult(200, body(settings([saved_profile("one")])))
    )
    target = account()

    first = await service_instance.profiles(target)
    second = await service_instance.profiles(target)

    assert first is second
    assert http.request.await_count == 1
    service_instance.invalidate(target.puuid)
    await service_instance.profiles(target)
    assert http.request.await_count == 2


async def test_service_refetches_after_the_ttl(monkeypatch):
    """Entries must expire so an in-game change appears without a restart."""
    clock = [1000.0]
    monkeypatch.setattr(crosshair_module.time, "monotonic", lambda: clock[0])
    service_instance, _auth, http = service()
    http.request = AsyncMock(
        return_value=HTTPResult(200, body(settings([saved_profile("one")])))
    )
    target = account()

    await service_instance.profiles(target)
    clock[0] += 301
    await service_instance.profiles(target)

    assert http.request.await_count == 2


async def test_service_refetches_when_the_account_identity_changes():
    """A relinked account with the same puuid must not reuse cached data."""
    service_instance, _auth, http = service()
    http.request = AsyncMock(
        return_value=HTTPResult(200, body(settings([saved_profile("one")])))
    )

    await service_instance.profiles(account(user_id=1))
    await service_instance.profiles(account(user_id=2))

    assert http.request.await_count == 2


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationRequired),
        (403, AuthenticationRequired),
        (503, CrosshairUnavailable),
    ],
)
async def test_service_maps_http_statuses(status, error):
    """Unauthorized responses ask for login; other failures use the command error."""
    service_instance, _auth, http = service()
    http.request = AsyncMock(return_value=HTTPResult(status, {}))

    with pytest.raises(error):
        await service_instance.profiles(account())


async def test_render_png_returns_a_png():
    """The service must render an encoded profile without network access."""
    service_instance, _auth, _http = service()
    profile = profiles_from_settings(settings([saved_profile("one")]))[0]
    assert service_instance.render_png(profile).startswith(b"\x89PNG")
