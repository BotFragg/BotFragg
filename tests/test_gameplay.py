"""Behavior and regression checks for gameplay."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from src.services.gameplay import GameplayService, GameplayUnavailable
from src.services.http import HTTPFailure


async def test_battlepass_uses_active_act_instead_of_future_act():
    now = datetime.now(UTC)

    def act(uuid, year):
        return {
            "uuid": uuid,
            "type": "EAresSeasonType::Act",
            "displayName": uuid,
            "startTime": f"{year}-01-01T00:00:00Z",
            "endTime": f"{year}-12-31T00:00:00Z",
        }

    def definition(uuid):
        return {
            "uuid": "contract-" + uuid,
            "content": {
                "relationType": "Season",
                "relationUuid": uuid,
                "chapters": [{"levels": [{"xp": 100}]}],
            },
        }

    responses = iter(
        [
            {
                "Contracts": [
                    {
                        "ContractDefinitionID": "contract-active",
                        "ProgressionLevelReached": 0,
                    }
                ]
            },
            {"data": [act("active", now.year), act("future", now.year + 1)]},
            {"data": [definition("active"), definition("future")]},
        ]
    )

    async def request(*args, **kwargs):
        return SimpleNamespace(status=200, data=next(responses))

    gameplay = GameplayService(
        SimpleNamespace(request=request),
        SimpleNamespace(auth_headers=AsyncMock(return_value={})),
        None,
    )
    data = await gameplay.battlepass(SimpleNamespace(puuid="synthetic", region="na"))
    assert data["act"] == "active"


@pytest.mark.parametrize(
    "kind",
    [
        "season-row",
        "definition-row",
        "content",
        "chapters",
        "levels",
        "level",
        "progress",
        "negative",
        "infinite",
        "boolean",
        "next-progress",
        "contract-row",
        "contracts",
        "reward",
        "xp",
    ],
)
async def test_bad_battlepass_payload_is_recoverable(kind):
    seasons = [
        {
            "uuid": "act",
            "type": "EAresSeasonType::Act",
            "startTime": "2020-01-01T00:00:00Z",
            "endTime": "2100-01-01T00:00:00Z",
        }
    ]
    definition = {
        "uuid": "pass",
        "content": {
            "relationType": "Season",
            "relationUuid": "act",
            "chapters": [{"levels": [{"xp": 100, "reward": {}}]}],
        },
    }
    progress = {
        "Contracts": [
            {
                "ContractDefinitionID": "pass",
                "ProgressionLevelReached": 0,
                "ProgressionTowardsNextLevel": 0,
            }
        ]
    }
    if kind == "season-row":
        seasons.append(None)
    elif kind == "definition-row":
        definition = None
    elif kind == "content":
        definition["content"] = ["malformed"]
    elif kind == "chapters":
        definition["content"]["chapters"] = [None]
    elif kind == "level":
        definition["content"]["chapters"][0]["levels"] = [None]
    elif kind == "levels":
        definition["content"]["chapters"][0]["levels"] = 5
    elif kind == "reward":
        definition["content"]["chapters"][0]["levels"][0]["reward"] = ["malformed"]
    elif kind == "xp":
        definition["content"]["chapters"][0]["levels"][0]["xp"] = "malformed"
    elif kind == "contracts":
        progress["Contracts"] = 5
    elif kind == "contract-row":
        progress["Contracts"].append(None)
    elif kind == "next-progress":
        progress["Contracts"][0]["ProgressionTowardsNextLevel"] = "malformed"
    elif kind == "negative":
        progress["Contracts"][0]["ProgressionLevelReached"] = -1
    elif kind == "infinite":
        progress["Contracts"][0]["ProgressionLevelReached"] = float("inf")
    elif kind == "boolean":
        progress["Contracts"][0]["ProgressionLevelReached"] = True
    elif kind == "progress":
        progress["Contracts"][0]["ProgressionLevelReached"] = "malformed"

    async def request(method, url, **kwargs):
        data = (
            {"data": seasons}
            if "/seasons?" in url
            else {"data": [definition]}
            if "/contracts?" in url
            else progress
        )
        return NS(status=200, data=data)

    service = GameplayService(
        NS(request=request), NS(auth_headers=AsyncMock(return_value={})), NS()
    )
    with pytest.raises(GameplayUnavailable):
        await service.battlepass(NS(puuid="synthetic", region="na"))


@pytest.mark.parametrize("level", [0, 55])
async def test_valid_battlepass_and_finished_pass(level):
    seasons = [
        {
            "uuid": "act",
            "type": "EAresSeasonType::Act",
            "displayName": {"en-US": "Synthetic Act"},
            "startTime": "2020-01-01T00:00:00",
            "endTime": "2100-01-01T00:00:00Z",
        }
    ]
    definitions = [
        {
            "uuid": "pass",
            "content": {
                "relationType": "Season",
                "relationUuid": "act",
                "chapters": [{"levels": [{"xp": "100", "reward": {"type": "Reward"}}]}],
            },
        }
    ]
    progress = {
        "Contracts": [
            {
                "ContractDefinitionID": "pass",
                "ProgressionLevelReached": level,
                "ProgressionTowardsNextLevel": "50",
            }
        ]
    }

    async def request(method, url, **kwargs):
        data = (
            {"data": seasons}
            if "/seasons?" in url
            else {"data": definitions}
            if "/contracts?" in url
            else progress
        )
        return NS(status=200, data=data)

    service = GameplayService(
        NS(request=request), NS(auth_headers=AsyncMock(return_value={})), NS()
    )
    result = await service.battlepass(NS(puuid="synthetic", region="na"))
    assert result["level"] == level
    assert result["progress"] == 50
    assert result["act"] == "Synthetic Act"
    assert result["end"].tzinfo is not None
    assert (
        result["next_level_xp"]
        == result["next_reward"]["xp"]
        == (100 if level == 0 else 0)
    )
    assert result["next_reward"]["type"] == ("Reward" if level == 0 else "Finished")


async def test_gameplay_normalizes_transient_auth_failures() -> None:
    """Verify that gameplay normalizes transient auth failures."""

    class FailingAuth:
        """Raise controlled credential errors so dependent services can classify login failures."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise HTTPFailure("transport unavailable")

    service = GameplayService(None, FailingAuth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.battlepass(SimpleNamespace(puuid="gameplay", region="na"))


async def test_gameplay_normalizes_transient_http_failures() -> None:
    """Verify that gameplay normalizes transient HTTP failures."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {}

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = GameplayService(FailingHTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.battlepass(SimpleNamespace(puuid="gameplay", region="na"))


async def test_gameplay_penalties_join_infractions_and_normalize_effects() -> None:
    """Verify penalties use the account shard and join Riot infraction metadata."""
    puuid = "2e2a6f06-0d0e-4b52-bf98-4d7b7ce9f5a4"
    infraction_id = "f5d4a5c9-5d4a-4ec6-bfe0-12b32cf08fe4"
    requests: list[tuple[str, str, dict[str, str]]] = []

    class Auth:
        """Return the authenticated headers expected by the Riot endpoint."""

        async def auth_headers(self, account) -> dict[str, str]:
            """Return test headers for the requested account."""
            assert account.puuid == puuid
            return {"Authorization": "Bearer token", "X-Riot-Entitlements-JWT": "ent"}

    class HTTP:
        """Return a representative Riot penalties response."""

        async def request(self, method, url, *, headers):
            """Record the request and return test penalty data."""
            requests.append((method, url, headers))
            return SimpleNamespace(
                status=200,
                data={
                    "Subject": puuid,
                    "Penalties": [
                        {
                            "InfractionID": infraction_id,
                            "Expiry": "2026-11-03T00:00:00.000Z",
                            "GamesRemaining": 2,
                            "ApplyToAllPlatforms": False,
                            "ApplyToPlatforms": ["PC"],
                            "ApplyToPlatformGroups": ["Competitive"],
                            "QueueRestrictionEffect": {"Duration": 300},
                            "RankedRatingPenaltyEffect": {"Amount": 5},
                            "WarningEffect": {
                                "WarningType": "QUEUE_DODGING",
                                "WarningTier": 2,
                            },
                        }
                    ],
                    "Infractions": [
                        {
                            "ID": infraction_id,
                            "Name": "Queue Dodging",
                            "RatingName": "Competitive restriction",
                        }
                    ],
                },
            )

    service = GameplayService(HTTP(), Auth(), None)

    penalties = await service.penalties(SimpleNamespace(puuid=puuid, region="br"))

    assert requests == [
        (
            "GET",
            "https://pd.na.a.pvp.net/restrictions/v3/penalties",
            {"Authorization": "Bearer token", "X-Riot-Entitlements-JWT": "ent"},
        )
    ]
    assert penalties == [
        {
            "infraction": "Queue Dodging",
            "expires": datetime(2026, 11, 3, tzinfo=UTC),
            "games_remaining": 2,
            "platform_scope": "PC, Competitive",
            "effects": ["queue-restriction", "ranked-rating-penalty", "warning"],
            "warning_type": "QUEUE_DODGING",
            "warning_tier": 2,
        }
    ]


async def test_gameplay_penalties_use_metadata_fallback_and_return_empty_list() -> None:
    """Verify missing infraction metadata falls back to its ID and empty data stays empty."""
    responses = [
        {
            "Subject": "player",
            "Penalties": [
                {"InfractionID": "rating-only"},
                {"InfractionID": "missing-metadata", "ApplyToAllPlatforms": True},
            ],
            "Infractions": [
                {"ID": "rating-only", "Name": None, "RatingName": "Rating fallback"}
            ],
        },
        {"Subject": "player", "Penalties": [], "Infractions": []},
    ]

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {"Authorization": "Bearer token"}

    class HTTP:
        """Return penalty responses in order."""

        async def request(self, *_args, **_kwargs):
            """Return the next configured response."""
            return SimpleNamespace(status=200, data=responses.pop(0))

    service = GameplayService(HTTP(), Auth(), None)
    account = SimpleNamespace(puuid="player", region="eu")

    penalties = await service.penalties(account)
    empty = await service.penalties(account)

    assert penalties[0]["infraction"] == "Rating fallback"
    assert penalties[1]["infraction"] == "missing-metadata"
    assert penalties[1]["platform_scope"] == "All platforms"
    assert empty == []


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status=503, data={}),
        SimpleNamespace(
            status=200, data={"Subject": "other", "Penalties": [], "Infractions": []}
        ),
        SimpleNamespace(
            status=200, data={"Subject": "player", "Penalties": {}, "Infractions": []}
        ),
        SimpleNamespace(
            status=200, data={"Subject": "player", "Penalties": [], "Infractions": None}
        ),
    ],
)
async def test_gameplay_penalties_reject_unusable_responses(response) -> None:
    """Verify penalties reject unsuccessful, cross-account, and malformed responses."""

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {}

    class HTTP:
        """Return the configured Riot response."""

        async def request(self, *_args, **_kwargs):
            """Return the configured response."""
            return response

    service = GameplayService(HTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.penalties(SimpleNamespace(puuid="player", region="eu"))


async def test_gameplay_penalties_normalize_transient_http_failures() -> None:
    """Verify the penalties service classifies HTTP transport failures."""

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {}

    class HTTP:
        """Raise a controlled transport failure."""

        async def request(self, *_args, **_kwargs):
            """Raise a failure like the shared HTTP client does."""
            raise HTTPFailure("transport unavailable")

    service = GameplayService(HTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.penalties(SimpleNamespace(puuid="player", region="eu"))
