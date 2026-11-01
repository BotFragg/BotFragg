"""Behaviour checks for the profile service's parsing and caching."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.http import HTTPFailure, HTTPResult
from src.services.profile import (
    LEVEL_XP_TARGET,
    ProfileService,
    ProfileUnavailable,
)

ACCOUNT = SimpleNamespace(puuid="puuid-1", region="eu")
ACT = "act-1"


def loadout(
    *, card: str = "card-1", title: str | None = None, level: int = 214, hidden=False
):
    """Build one player-loadout payload."""
    return {
        "Identity": {
            "PlayerCardID": card,
            "PlayerTitleID": title or "00000000-0000-0000-0000-000000000000",
            "AccountLevel": level,
            "HideAccountLevel": hidden,
        }
    }


def xp(*, level: int = 214, progress: int = 8420):
    """Build one account-XP payload."""
    return {"Progress": {"Level": level, "XP": progress}}


def mmr(
    *,
    tier: int = 19,
    rr: int = 47,
    wins: int = 29,
    games: int = 50,
    peak: int = 24,
    seasonal: bool = True,
):
    """Build one MMR payload with an older peak season."""
    seasons = (
        {
            ACT: {
                "CompetitiveTier": tier,
                "RankedRating": rr,
                "NumberOfWins": wins,
                "NumberOfGames": games,
            },
            "old-act": {"CompetitiveTier": peak, "RankedRating": 0},
        }
        if seasonal
        else {}
    )
    return {
        "QueueSkills": {"competitive": {"SeasonalInfoBySeasonID": seasons}},
        "LatestCompetitiveUpdate": {"SeasonID": ACT},
    }


def service(
    *,
    loadout_payload=None,
    xp_payload=None,
    mmr_payload=None,
    act: tuple[str, dict[str, str]] | None = (ACT, {"en-US": "Episode 10 Act 2"}),
):
    """Build a profile service whose HTTP client serves the given payloads."""
    http = AsyncMock()

    async def request(_method, url, *, headers=None):
        if "playerloadout" in url:
            return HTTPResult(
                200, loadout() if loadout_payload is None else loadout_payload
            )
        if "account-xp" in url:
            return HTTPResult(200, xp() if xp_payload is None else xp_payload)
        if "/mmr/" in url:
            return HTTPResult(200, mmr() if mmr_payload is None else mmr_payload)
        raise AssertionError(url)

    http.request = request
    auth = SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    catalog = SimpleNamespace(current_act=AsyncMock(return_value=act))
    return ProfileService(http, auth, catalog), http, catalog


async def test_profile_parses_rank_level_and_peak():
    """The card's numbers must come from the three Riot payloads."""
    instance, _http, _catalog = service()

    data = await instance.profile(ACCOUNT)

    assert data.card_id == "card-1"
    assert data.title_id is None
    assert data.level == 214
    assert data.xp == 8420
    assert data.xp_target == LEVEL_XP_TARGET
    assert data.tier == 19
    assert data.rr == 47
    assert data.wins == 29
    assert data.games == 50
    assert data.peak_tier == 24


async def test_a_hidden_level_is_shown_anyway():
    """The card shows the level even when the account hides it in game."""
    instance, _http, _catalog = service(loadout_payload=loadout(hidden=True))

    data = await instance.profile(ACCOUNT)

    assert data.level == 214
    assert data.xp == 8420
    assert data.xp_target == LEVEL_XP_TARGET


async def test_missing_identity_falls_back_to_account_xp():
    """A loadout without an account level still yields the XP endpoint's level."""
    instance, _http, _catalog = service(loadout_payload={})

    data = await instance.profile(ACCOUNT)

    assert data.level == 214
    assert data.card_id is None


async def test_unranked_account_has_no_rating():
    """An account with no seasonal entry must render as unranked."""
    instance, _http, _catalog = service(mmr_payload=mmr(seasonal=False))

    data = await instance.profile(ACCOUNT)

    assert data.tier == 0
    assert data.rr is None
    assert data.peak_tier is None


async def test_latest_act_is_used_when_the_catalog_is_unavailable():
    """A failed season lookup must fall back to the last played ranked act."""
    instance, _http, _catalog = service(act=None)

    data = await instance.profile(ACCOUNT)

    assert data.tier == 19
    assert data.rr == 47


async def test_profile_is_cached_between_calls():
    """Repeated lookups inside the window must not refetch."""
    instance, http, _catalog = service()
    calls = 0
    original = http.request

    async def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(*args, **kwargs)

    http.request = counting

    await instance.profile(ACCOUNT)
    # The catalog call is outside the HTTP client's counters.
    first = calls
    await instance.profile(ACCOUNT)

    assert calls == first == 3


async def test_concurrent_lookups_share_one_fetch():
    """Two simultaneous calls for one account must fetch the three payloads once."""
    instance, http, _catalog = service()
    calls = 0
    original = http.request

    async def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return await original(*args, **kwargs)

    http.request = counting

    results = await asyncio.gather(instance.profile(ACCOUNT), instance.profile(ACCOUNT))

    assert calls == 3
    assert results[0] == results[1]


@pytest.mark.parametrize("status", [401, 500])
async def test_failed_requests_raise_profile_unavailable(status):
    """Riot failures must map to one service error."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(status, {}))
    instance = ProfileService(
        http,
        SimpleNamespace(auth_headers=AsyncMock(return_value={})),
        SimpleNamespace(current_act=AsyncMock(return_value=None)),
    )

    with pytest.raises(ProfileUnavailable):
        await instance.profile(ACCOUNT)


async def test_transport_failure_raises_profile_unavailable():
    """A transport failure is reported as unavailable, not propagated raw."""
    http = AsyncMock()
    http.request = AsyncMock(side_effect=HTTPFailure("down"))
    instance = ProfileService(
        http,
        SimpleNamespace(auth_headers=AsyncMock(return_value={})),
        SimpleNamespace(current_act=AsyncMock(return_value=None)),
    )

    with pytest.raises(ProfileUnavailable):
        await instance.profile(ACCOUNT)


async def test_rejected_claims_are_repaired_once_for_all_requests():
    """Three rejected requests must trigger one token refresh, not three."""
    seen: list[str | None] = []

    async def request(_method, url, *, headers=None):
        seen.append((headers or {}).get("Authorization"))
        if (headers or {}).get("Authorization") == "old":
            return HTTPResult(400, {"errorCode": "BAD_CLAIMS"})
        if "playerloadout" in url:
            return HTTPResult(200, loadout())
        if "account-xp" in url:
            return HTTPResult(200, xp())
        return HTTPResult(200, mmr())

    repaired = SimpleNamespace(success=True, account=ACCOUNT)
    auth = SimpleNamespace(
        auth_headers=AsyncMock(
            side_effect=[{"Authorization": "old"}, {"Authorization": "new"}]
        ),
        ensure=AsyncMock(return_value=repaired),
    )
    instance = ProfileService(
        SimpleNamespace(request=request),
        auth,
        SimpleNamespace(current_act=AsyncMock(return_value=None)),
    )

    data = await instance.profile(ACCOUNT)

    assert auth.ensure.await_count == 1
    assert seen.count("old") == 3
    assert seen.count("new") == 3
    assert data.tier == 19


async def test_a_failed_profile_is_not_retried_immediately():
    """A failure must be remembered for a short window instead of re-hammering Riot."""
    http = AsyncMock()
    http.request = AsyncMock(side_effect=HTTPFailure("down"))
    instance = ProfileService(
        http,
        SimpleNamespace(auth_headers=AsyncMock(return_value={})),
        SimpleNamespace(current_act=AsyncMock(return_value=None)),
    )

    with pytest.raises(ProfileUnavailable):
        await instance.profile(ACCOUNT)
    calls = http.request.await_count

    with pytest.raises(ProfileUnavailable):
        await instance.profile(ACCOUNT)

    assert http.request.await_count == calls
