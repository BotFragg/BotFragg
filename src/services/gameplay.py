"""Fetch VALORANT progression and matchmaking penalties for linked accounts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from ..models import Account
from .auth import AuthService, riot_region
from .catalog import CatalogService
from .http import HTTPClient, HTTPFailure


class GameplayService:
    """Riot gameplay APIs used by battlepass, mission, and penalty commands."""

    def __init__(
        self,
        http: HTTPClient,
        auth: AuthService,
        catalog: CatalogService,
    ) -> None:
        """Bind the shared Riot client, authentication service, and catalog."""
        self.http, self.auth, self.catalog = http, auth, catalog

    async def battlepass(self, account: Account) -> dict[str, Any]:
        """Return the active battlepass level, XP, expiry, and next reward."""
        try:
            headers = await self.auth.auth_headers(account)
            contracts, seasons, definitions = await asyncio.gather(
                self.http.request(
                    "GET",
                    f"https://pd.{riot_region(account.region)}.a.pvp.net/contracts/v1/contracts/{account.puuid}",
                    headers=headers,
                ),
                self.http.request("GET", "https://valorant-api.com/v1/seasons"),
                self.http.request("GET", "https://valorant-api.com/v1/contracts"),
            )
        except HTTPFailure as exc:
            raise GameplayUnavailable("Could not fetch battlepass data") from exc
        if contracts.status != 200 or not isinstance(contracts.data, dict):
            raise GameplayUnavailable("Could not fetch battlepass progress")
        acts = sorted(
            (
                item
                for item in _api_data(seasons.data)
                if item.get("type") == "EAresSeasonType::Act"
            ),
            key=lambda item: item.get("startTime", ""),
            reverse=True,
        )
        passes = [
            item
            for item in _api_data(definitions.data)
            if (item.get("content") or {}).get("relationType") == "Season"
        ]
        active = next(
            (
                (act, definition)
                for act in acts
                for definition in passes
                if (definition.get("content") or {}).get("relationUuid")
                == act.get("uuid")
            ),
            None,
        )
        if not active:
            raise GameplayUnavailable("Active battlepass metadata is unavailable")
        act, definition = active
        contract = next(
            (
                item
                for item in contracts.data.get("Contracts", [])
                if item.get("ContractDefinitionID") == definition.get("uuid")
            ),
            None,
        )
        if not contract:
            raise GameplayUnavailable(
                "The active battlepass contract is not available for this account"
            )
        level = int(contract.get("ProgressionLevelReached", 0))
        progress = int(contract.get("ProgressionTowardsNextLevel", 0))
        end = datetime.fromisoformat(str(act["endTime"]).replace("Z", "+00:00"))
        levels = [
            entry
            for chapter in (definition.get("content") or {}).get("chapters", [])
            for entry in chapter.get("levels", [])
        ]
        return {
            "act": str(act.get("displayName") or "Current act"),
            "level": level,
            "progress": progress,
            "next_level_xp": int(
                (levels[level] if level < len(levels) else {}).get("xp") or 0
            ),
            "end": end,
            "next_reward": await self._reward(levels, level),
        }

    async def missions(self, account: Account) -> list[dict[str, Any]]:
        """Join the account's live mission progress with cached catalog definitions."""
        try:
            headers = await self.auth.auth_headers(account)
            contracts, definitions = await asyncio.gather(
                self.http.request(
                    "GET",
                    f"https://pd.{riot_region(account.region)}.a.pvp.net/contracts/v1/contracts/{account.puuid}",
                    headers=headers,
                ),
                self.catalog.mission_metadata(),
            )
        except HTTPFailure as exc:
            raise GameplayUnavailable("Could not fetch mission data") from exc
        if contracts.status != 200 or not isinstance(contracts.data, dict):
            raise GameplayUnavailable("Could not fetch mission progress")
        rows = contracts.data.get("Missions", [])
        if not isinstance(rows, list):
            raise GameplayUnavailable("Mission progress is malformed")
        return [
            mission
            for row in rows
            if (mission := self._mission_progress(row, definitions)) is not None
        ]

    async def penalties(self, account: Account) -> list[dict[str, Any]]:
        """Fetch and normalize an account's current Riot matchmaking penalties."""
        try:
            headers = await self.auth.auth_headers(account)
            response = await self.http.request(
                "GET",
                f"https://pd.{riot_region(account.region)}.a.pvp.net/restrictions/v3/penalties",
                headers=headers,
            )
        except HTTPFailure as exc:
            raise GameplayUnavailable("Could not fetch penalty data") from exc
        payload = response.data
        if response.status != 200 or not isinstance(payload, dict):
            raise GameplayUnavailable("Could not fetch penalty data")
        subject = payload.get("Subject")
        if (
            not isinstance(subject, str)
            or subject.casefold() != account.puuid.casefold()
        ):
            raise GameplayUnavailable("Riot returned penalties for a different account")
        rows = payload.get("Penalties")
        infractions = payload.get("Infractions")
        if (
            not isinstance(rows, list)
            or not isinstance(infractions, list)
            or any(not isinstance(row, dict) for row in [*rows, *infractions])
        ):
            raise GameplayUnavailable("Riot returned malformed penalty data")

        infraction_by_id = {
            str(infraction["ID"]): infraction
            for infraction in infractions
            if isinstance(infraction.get("ID"), str) and infraction["ID"]
        }
        effect_labels = (
            ("DelayedPenaltyEffect", "delayed-penalty"),
            ("GameBanEffect", "game-ban"),
            ("QueueDelayEffect", "queue-delay"),
            ("QueueRestrictionEffect", "queue-restriction"),
            ("RankedRatingPenaltyEffect", "ranked-rating-penalty"),
            ("RiotRestrictionEffect", "riot-restriction"),
            ("RMSNotifyEffect", "riot-notification"),
            ("XPMultiplierEffect", "xp-multiplier"),
            ("PremierRestrictionEffect", "premier-restriction"),
        )
        result = []
        for row in rows:
            infraction_id = str(row.get("InfractionID") or "")
            infraction = infraction_by_id.get(infraction_id, {})
            name = next(
                (
                    value.strip()
                    for value in (infraction.get("Name"), infraction.get("RatingName"))
                    if isinstance(value, str) and value.strip()
                ),
                infraction_id or "Unknown infraction",
            )
            platform_values = []
            if row.get("ApplyToAllPlatforms") is not True:
                for field in ("ApplyToPlatforms", "ApplyToPlatformGroups"):
                    values = row.get(field)
                    if isinstance(values, list):
                        platform_values.extend(
                            value.strip()
                            for value in values
                            if isinstance(value, str) and value.strip()
                        )
            platform_scope = (
                "All platforms"
                if row.get("ApplyToAllPlatforms") is True
                else ", ".join(dict.fromkeys(platform_values)) or "Not specified"
            )
            effects = [
                key for field, key in effect_labels if row.get(field) is not None
            ]
            warning = row.get("WarningEffect")
            warning_type = (
                warning.get("WarningType")
                if isinstance(warning, dict)
                and isinstance(warning.get("WarningType"), str)
                else None
            )
            warning_tier = (
                _nonnegative_int(warning.get("WarningTier"))
                if isinstance(warning, dict)
                else None
            )
            if warning is not None:
                effects.append("warning")
            result.append(
                {
                    "infraction": name,
                    "expires": _parse_datetime(row.get("Expiry")),
                    "games_remaining": _nonnegative_int(row.get("GamesRemaining")),
                    "platform_scope": platform_scope,
                    "effects": effects,
                    "warning_type": warning_type,
                    "warning_tier": warning_tier,
                }
            )
        return result

    @staticmethod
    def _mission_progress(
        row: Any,
        definitions: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Normalize one Riot mission row and its objective progress for display."""
        if not isinstance(row, dict) or not (mission_id := str(row.get("ID") or "")):
            return None
        definition = definitions.get(mission_id)
        if not definition:
            return {
                "type": "Missions",
                "title": "Mission details unavailable",
                "xp": None,
                "complete": bool(row.get("Complete")),
                "expires": _parse_datetime(row.get("ExpirationTime")),
                "tasks": [],
            }

        raw_objectives = row.get("Objectives")
        current = (
            {
                str(key): progress
                for key, value in raw_objectives.items()
                if (progress := _nonnegative_int(value)) is not None
            }
            if isinstance(raw_objectives, dict)
            else {}
        )
        mission_objectives = definition.get("objectives")
        mission_objectives = (
            [item for item in mission_objectives if isinstance(item, dict)]
            if isinstance(mission_objectives, list)
            else []
        )
        mission_target = _positive_int(definition.get("progressToComplete"))
        live_objectives = list(current.items())
        tasks: list[dict[str, Any]] = []
        for item in mission_objectives:
            objective_id = str(item.get("objectiveUuid") or "")
            if not objective_id:
                continue
            progress = current.get(objective_id)
            if (
                progress is None
                and len(mission_objectives) == len(live_objectives) == 1
            ):
                progress = live_objectives[0][1]
            target = mission_target if len(mission_objectives) == 1 else None
            target = target or _positive_int(item.get("value"))
            tasks.append(
                {
                    "progress": progress,
                    "target": target,
                }
            )
        if not tasks and live_objectives:
            tasks = [
                {
                    "progress": progress,
                    "target": mission_target if len(live_objectives) == 1 else None,
                }
                for _, progress in live_objectives
            ]
        title = str(
            definition.get("title") or definition.get("displayName") or "Mission"
        )
        kind = str(definition.get("type") or "").rsplit("::", 1)[-1].casefold()
        mission_type = (
            f"{kind.title()} Missions" if kind in {"daily", "weekly"} else "Missions"
        )
        return {
            "type": mission_type,
            "title": title,
            "xp": _nonnegative_int(definition.get("xpGrant")),
            "complete": bool(row.get("Complete")),
            "expires": _parse_datetime(row.get("ExpirationTime")),
            "tasks": tasks,
        }

    async def _reward(self, levels: list[dict[str, Any]], level: int) -> dict[str, Any]:
        """Resolve the next battlepass reward to display data, including its icon."""
        if level >= 55:
            return {
                "name": "🎉 Congratulations, you've finished the battlepass!",
                "type": "Finished",
                "xp": 0,
                "icon": None,
            }
        reward = (levels[level] if level < len(levels) else {}).get("reward") or {}
        kind, uuid = str(reward.get("type") or "Reward"), str(reward.get("uuid") or "")
        if kind == "EquippableSkinLevel" and (skin := self.catalog.get_skin(uuid)):
            return {
                "name": skin.name,
                "type": kind,
                "xp": levels[level].get("xp", 0),
                "icon": skin.icon,
                "tier_uuid": skin.tier_uuid,
            }
        types = {
            "EquippableCharmLevel": "dd3bf334-87f3-40bd-b043-682a57a8dc3a",
            "PlayerCard": "3f296c07-64c3-494c-923b-fe692a4fa1bd",
            "Spray": "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475",
            "Totem": "03a572de-4234-31ed-d344-ababa488f981",
        }
        if kind in types and (item := await self.catalog.accessory(types[kind], uuid)):
            return {
                "name": item.name,
                "type": kind,
                "xp": levels[level].get("xp", 0),
                "icon": item.icon,
            }
        return {
            "name": "Radianite" if kind == "Currency" else "Reward",
            "type": kind,
            "xp": levels[level].get("xp", 0),
            "icon": None,
        }


def _api_data(value: Any) -> list[dict[str, Any]]:
    """Return a validated API response's data list or an empty list."""
    return (
        value.get("data", [])
        if isinstance(value, dict) and isinstance(value.get("data"), list)
        else []
    )


class GameplayUnavailable(RuntimeError):
    """Riot did not return usable gameplay data."""


def _nonnegative_int(value: Any) -> int | None:
    """Convert a non-Boolean value to a nonnegative integer when possible."""
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except TypeError, ValueError:
        return None
    return result if result >= 0 else None


def _positive_int(value: Any) -> int | None:
    """Convert a value to a positive integer or return ``None``."""
    return _nonnegative_int(value) or None


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp and attach UTC when the input has no timezone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result
