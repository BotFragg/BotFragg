"""Behaviour checks for match history parsing, reduction, and caching."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.http import HTTPFailure, HTTPResult
from src.services.matches import (
    MATCH_SUMMARY_LIMIT,
    MatchesService,
    MatchesUnavailable,
)

ACCOUNT = SimpleNamespace(puuid="puuid-1", region="eu")


def history(*entries: tuple[str, str]):
    """Build one match-history payload from ``(match id, queue id)`` pairs."""
    return {
        "History": [
            {
                "MatchID": match_id,
                "GameStartTime": 1_700_000_000_000,
                "QueueID": queue_id,
            }
            for match_id, queue_id in entries
        ]
    }


def detail(
    *,
    won: bool = True,
    queue_id: str = "competitive",
    map_id: str = "map-1",
    team: bool = True,
):
    """Build one match-details payload with both teams and one damage event."""
    teams = (
        [
            {"teamId": "blue", "won": won, "roundsWon": 13 if won else 9},
            {"teamId": "red", "won": not won, "roundsWon": 9 if won else 13},
        ]
        if team
        else []
    )
    return {
        "matchInfo": {"mapId": map_id, "queueID": queue_id, "isCompleted": True},
        "players": [
            {
                "subject": "puuid-1",
                "teamId": "blue",
                "characterId": "agent-1",
                "stats": {
                    "kills": 21,
                    "deaths": 14,
                    "assists": 5,
                    "score": 6400,
                    "roundsPlayed": 22,
                },
            },
            {
                "subject": "puuid-2",
                "teamId": "red",
                "characterId": "agent-2",
                "stats": {
                    "kills": 12,
                    "deaths": 19,
                    "assists": 3,
                    "score": 4100,
                    "roundsPlayed": 22,
                },
            },
        ],
        "teams": teams,
        "roundResults": [
            {
                "playerStats": [
                    {
                        "subject": "puuid-1",
                        "damage": [
                            {"headshots": 3, "bodyshots": 5, "legshots": 2},
                        ],
                    }
                ]
            }
        ],
    }


def service(
    details: dict[str, object],
    *,
    match_ids=("m1", "m2"),
    entries=None,
    ranked: object = None,
):
    """Build a match service whose HTTP client serves history and details."""
    http = AsyncMock()
    rows = (
        entries
        if entries is not None
        else tuple((match_id, "competitive") for match_id in match_ids)
    )

    async def request(_method, url, *, headers=None):
        if "competitiveupdates" in url:
            if isinstance(ranked, Exception):
                raise ranked
            return HTTPResult(200, {"Matches": ranked or []})
        if "match-history" in url:
            return HTTPResult(200, history(*rows))
        for match_id, payload in details.items():
            if match_id in url:
                if isinstance(payload, Exception):
                    raise payload
                return HTTPResult(200, payload)
        raise AssertionError(url)

    http.request = request
    auth = SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    return MatchesService(http, auth), http


async def test_recent_matches_are_reduced_for_the_card():
    """One match must expose its result, score, map, and the caller's stats."""
    instance, _http = service({"m1": detail(), "m2": detail(won=False)})

    matches = await instance.recent(ACCOUNT)

    assert [match.match_id for match in matches] == ["m1", "m2"]
    first = matches[0].player("puuid-1")
    assert first is not None
    assert first.won is True
    assert (first.rounds_won, first.rounds_lost) == (13, 9)
    assert (first.killed, first.died, first.assisted) == (21, 14, 5)
    assert first.headshot_percent == 30
    assert first.combat_score == 291
    assert matches[0].map_id == "map-1"
    assert matches[0].queue_id == "competitive"


async def test_the_other_team_reads_the_match_as_a_loss():
    """The same cached match must resolve differently for each player."""
    instance, _http = service({"m1": detail(), "m2": detail()})

    matches = await instance.recent(ACCOUNT)

    opponent = matches[0].player("puuid-2")
    assert opponent is not None
    assert opponent.won is False
    assert (opponent.rounds_won, opponent.rounds_lost) == (9, 13)


async def test_match_details_are_cached_across_calls():
    """Finished matches are immutable, so they must be fetched only once."""
    instance, http = service({"m1": detail(), "m2": detail()})
    calls: list[str] = []
    original = http.request

    async def counting(method, url, *, headers=None):
        calls.append(url)
        return await original(method, url, headers=headers)

    http.request = counting

    await instance.recent(ACCOUNT)
    # Clear only the history cache so the summaries must be reused.
    instance._history.clear()
    await instance.recent(ACCOUNT)

    assert sum("match-details" in url for url in calls) == 2


async def test_a_failed_match_detail_is_skipped():
    """One broken match must not hide the rest of the list."""
    instance, _http = service(
        {"m1": HTTPFailure("down"), "m2": detail()}, match_ids=("m1", "m2")
    )

    matches = await instance.recent(ACCOUNT)

    assert [match.match_id for match in matches] == ["m2"]


async def test_matches_without_teams_are_skipped():
    """A match with no team result must not render as a loss."""
    instance, _http = service({"m1": detail(team=False)}, match_ids=("m1",))

    matches = await instance.recent(ACCOUNT)

    assert matches == []


async def test_history_failure_raises():
    """A failed history call must map to one service error."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(500, {}))
    instance = MatchesService(
        http, SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    )

    with pytest.raises(MatchesUnavailable):
        await instance.recent(ACCOUNT)


async def test_concurrent_lookups_share_one_fetch():
    """Two simultaneous lookups must fetch each match detail once."""
    instance, http = service({"m1": detail(), "m2": detail()})
    calls = 0
    original = http.request

    async def counting(method, url, *, headers=None):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return await original(method, url, headers=headers)

    http.request = counting

    await asyncio.gather(instance.recent(ACCOUNT), instance.recent(ACCOUNT))

    assert calls == 3


async def test_recent_filters_matches_by_queue():
    """Only matches from the requested queue must be fetched and returned."""
    instance, _http = service(
        {"m1": detail(), "m3": detail()},
        entries=(("m1", "competitive"), ("m2", "unrated"), ("m3", "competitive")),
    )

    matches = await instance.recent(ACCOUNT, queue="competitive")

    assert [match.match_id for match in matches] == ["m1", "m3"]


async def test_ranked_changes_map_each_match_to_its_rr():
    """Every competitive match must carry the RR it gained or lost."""
    instance, _http = service(
        {},
        ranked=[
            {"MatchID": "m1", "RankedRatingEarned": 17},
            {"MatchID": "m2", "RankedRatingEarned": -12},
            {"MatchID": "bad", "RankedRatingEarned": "unknown"},
        ],
    )

    assert await instance.ranked_changes(ACCOUNT) == {"m1": 17, "m2": -12}


async def test_ranked_changes_are_cached():
    """Repeated lookups inside the window must not refetch."""
    instance, http = service({}, ranked=[{"MatchID": "m1", "RankedRatingEarned": 17}])
    calls = 0
    original = http.request

    async def counting(method, url, *, headers=None):
        nonlocal calls
        if "competitiveupdates" in url:
            calls += 1
        return await original(method, url, headers=headers)

    http.request = counting

    await instance.ranked_changes(ACCOUNT)
    await instance.ranked_changes(ACCOUNT)

    assert calls == 1


async def test_ranked_changes_fail_soft():
    """A failed RR lookup must not break the match list."""
    instance, _http = service({}, ranked=HTTPFailure("down"))

    assert await instance.ranked_changes(ACCOUNT) == {}


async def test_failed_history_is_not_retried_immediately():
    """A history failure must be remembered for a short window."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(500, {}))
    instance = MatchesService(
        http, SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    )

    with pytest.raises(MatchesUnavailable):
        await instance.recent(ACCOUNT)
    calls = http.request.await_count

    with pytest.raises(MatchesUnavailable):
        await instance.recent(ACCOUNT)

    assert http.request.await_count == calls


async def test_failed_ranked_changes_are_not_retried_immediately():
    """A failed RR lookup must cool down before the next attempt."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(500, {}))
    instance = MatchesService(
        http, SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    )

    assert await instance.ranked_changes(ACCOUNT) == {}
    calls = http.request.await_count

    assert await instance.ranked_changes(ACCOUNT) == {}
    assert http.request.await_count == calls


async def test_a_malformed_round_does_not_break_the_match():
    """A round entry that is not an object must only lose its shot counts."""
    payload = detail()
    payload["roundResults"] = [None, "junk", *payload["roundResults"]]

    instance, _http = service({"m1": payload}, match_ids=("m1",))
    matches = await instance.recent(ACCOUNT, queue="competitive")

    stats = matches[0].player(ACCOUNT.puuid)
    assert stats is not None
    assert stats.headshot_hits == 3
    assert stats.total_hits == 10


async def test_failed_match_cooldowns_are_bounded():
    """Repeated failures must not grow the cooldown table forever."""
    instance, _http = service({})
    match_ids = [f"match-{index}" for index in range(MATCH_SUMMARY_LIMIT + 1)]

    instance._store_summaries(match_ids, [None] * len(match_ids), {})

    assert len(instance._summary_retry_at) == MATCH_SUMMARY_LIMIT
