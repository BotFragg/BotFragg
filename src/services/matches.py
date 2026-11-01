"""Fetch a linked account's recent matches and reduce them for display."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from weakref import WeakValueDictionary

from ..models import Account
from .auth import (
    AuthService,
    pd_url,
    request_many_with_claims_repair,
    request_with_claims_repair,
)
from .http import HTTPClient, HTTPFailure, HTTPResult
from .riot_values import identifier, nonnegative

log = logging.getLogger(__name__)

MATCH_HISTORY_TTL_SECONDS = 120
MATCH_SUMMARY_LIMIT = 2000
RECENT_MATCH_LIMIT = 4
NEGATIVE_CACHE_SECONDS = 30


class MatchesUnavailable(RuntimeError):
    """Raised when Riot's match history cannot be loaded."""


@dataclass(frozen=True, slots=True)
class PlayerStats:
    """One player's result and combat numbers in a single match."""

    agent_id: str | None = None
    killed: int = 0
    died: int = 0
    assisted: int = 0
    headshot_hits: int = 0
    total_hits: int = 0
    score: int = 0
    rounds: int = 0
    won: bool | None = None
    rounds_won: int | None = None
    rounds_lost: int | None = None

    @property
    def headshot_percent(self) -> int | None:
        """Return the share of hits that landed on the head, or ``None``."""
        if not self.total_hits:
            return None
        return round(self.headshot_hits * 100 / self.total_hits)

    @property
    def combat_score(self) -> int | None:
        """Return the average combat score per round, or ``None``."""
        if not self.rounds:
            return None
        return round(self.score / self.rounds)


@dataclass(frozen=True, slots=True)
class MatchSummary:
    """One finished match, reduced to the numbers a profile card shows."""

    match_id: str
    map_id: str | None
    queue_id: str | None
    players: dict[str, PlayerStats]

    def player(self, puuid: str) -> PlayerStats | None:
        """Return the requested player's stats from this match."""
        return self.players.get(puuid.casefold())


class MatchesService:
    """Fetch recent match identifiers, then cache each reduced match for good."""

    def __init__(self, http: HTTPClient, auth: AuthService) -> None:
        """Bind the shared services and start empty history and match caches."""
        self.http = http
        self.auth = auth
        self._history: dict[str, tuple[float, tuple[tuple[str, str | None], ...]]] = {}
        self._history_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._history_retry_at: dict[str, float] = {}
        self._summaries: OrderedDict[str, MatchSummary] = OrderedDict()
        self._summary_retry_at: dict[str, float] = {}
        self._detail_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._ranked: dict[str, tuple[float, dict[str, int]]] = {}
        self._ranked_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._ranked_retry_at: dict[str, float] = {}

    async def recent(
        self,
        account: Account,
        *,
        limit: int = RECENT_MATCH_LIMIT,
        queue: str | None = None,
    ) -> list[MatchSummary]:
        """Return the account's most recent team matches, newest first."""
        try:
            headers = await self.auth.auth_headers(account)
            entries = await self._recent_entries(account, headers)
            match_ids = [
                match_id
                for match_id, queue_id in entries
                if queue is None or queue_id == queue
            ][:limit]
            summaries = await self._summaries_for(account, headers, match_ids)
        except HTTPFailure as exc:
            raise MatchesUnavailable("Could not fetch match history") from exc
        result: list[MatchSummary] = []
        for summary in summaries:
            player = summary.player(account.puuid)
            if player is not None and player.won is not None:
                result.append(summary)
        return result[:limit]

    async def ranked_changes(self, account: Account) -> dict[str, int]:
        """Return each recent competitive match's RR change for one account."""
        headers = await self.auth.auth_headers(account)
        async with self._ranked_locks.setdefault(account.puuid, asyncio.Lock()):
            now = time.monotonic()
            cached = self._ranked.get(account.puuid)
            if cached is not None and cached[0] > now:
                return cached[1]
            if now < self._ranked_retry_at.get(account.puuid, 0.0):
                return {}
            try:
                response = await request_with_claims_repair(
                    self.auth,
                    account,
                    headers,
                    lambda request_headers: self.http.request(
                        "GET",
                        pd_url(
                            account.region,
                            f"/mmr/v1/players/{account.puuid}/competitiveupdates",
                        ),
                        headers=request_headers,
                    ),
                )
            except HTTPFailure:
                self._ranked_retry_at[account.puuid] = now + NEGATIVE_CACHE_SECONDS
                log.warning("Could not fetch competitive updates", exc_info=True)
                return {}
            if response.status != 200 or not isinstance(response.data, dict):
                self._ranked_retry_at[account.puuid] = now + NEGATIVE_CACHE_SECONDS
                return {}
            rows = response.data.get("Matches")
            changes = {
                str(row["MatchID"]): int(row["RankedRatingEarned"])
                for row in rows or []
                if isinstance(row, dict)
                and isinstance(row.get("MatchID"), str)
                and isinstance(row.get("RankedRatingEarned"), int)
                and not isinstance(row.get("RankedRatingEarned"), bool)
            }
            self._ranked[account.puuid] = (
                now + MATCH_HISTORY_TTL_SECONDS,
                changes,
            )
            self._ranked_retry_at.pop(account.puuid, None)
            return changes

    async def _recent_entries(
        self, account: Account, headers: dict[str, str]
    ) -> tuple[tuple[str, str | None], ...]:
        """Return cached or freshly fetched match identifiers and their queues."""
        async with self._history_locks.setdefault(account.puuid, asyncio.Lock()):
            now = time.monotonic()
            cached = self._history.get(account.puuid)
            if cached is not None and cached[0] > now:
                return cached[1]
            if now < self._history_retry_at.get(account.puuid, 0.0):
                raise MatchesUnavailable("Match history is temporarily unavailable")
            response = await request_with_claims_repair(
                self.auth,
                account,
                headers,
                lambda request_headers: self.http.request(
                    "GET",
                    pd_url(
                        account.region,
                        f"/match-history/v1/history/{account.puuid}",
                    ),
                    headers=request_headers,
                ),
            )
            if response.status != 200 or not isinstance(response.data, dict):
                self._history_retry_at[account.puuid] = now + NEGATIVE_CACHE_SECONDS
                raise MatchesUnavailable(
                    f"Riot returned HTTP {response.status} for match history"
                )
            rows = response.data.get("History")
            rows = rows if isinstance(rows, list) else []
            entries = tuple(
                (
                    match_id,
                    queue_id
                    if isinstance(queue_id := row.get("QueueID"), str)
                    else None,
                )
                for row in rows
                if isinstance(row, dict)
                and isinstance(match_id := row.get("MatchID"), str)
                and match_id
            )
            self._history[account.puuid] = (
                now + MATCH_HISTORY_TTL_SECONDS,
                entries,
            )
            self._history_retry_at.pop(account.puuid, None)
            return entries

    async def _summaries_for(
        self, account: Account, headers: dict[str, str], match_ids: list[str]
    ) -> list[MatchSummary]:
        """Return reduced matches, fetching only the ones not already cached."""
        found: dict[str, MatchSummary] = {}
        missing: list[str] = []
        now = time.monotonic()
        for match_id in match_ids:
            cached = self._summaries.get(match_id)
            if cached is not None:
                self._summaries.move_to_end(match_id)
                found[match_id] = cached
            elif now >= self._summary_retry_at.get(match_id, 0.0):
                missing.append(match_id)
        if missing:
            async with self._detail_locks.setdefault(account.puuid, asyncio.Lock()):
                awaiting: list[str] = []
                for match_id in missing:
                    cached = self._summaries.get(match_id)
                    if cached is not None:
                        found[match_id] = cached
                    elif now >= self._summary_retry_at.get(match_id, 0.0):
                        awaiting.append(match_id)
                if awaiting:
                    responses: list[HTTPResult | None]
                    try:
                        responses = list(
                            await request_many_with_claims_repair(
                                self.auth,
                                account,
                                headers,
                                tuple(
                                    _match_request(self.http, account.region, match_id)
                                    for match_id in awaiting
                                ),
                            )
                        )
                    except HTTPFailure:
                        # One broken match must not hide the others, so fall back
                        # to fetching them separately.
                        responses = []
                        for match_id in awaiting:
                            try:
                                responses.append(
                                    await request_with_claims_repair(
                                        self.auth,
                                        account,
                                        headers,
                                        _match_request(
                                            self.http, account.region, match_id
                                        ),
                                    )
                                )
                            except HTTPFailure:
                                responses.append(None)
                    self._store_summaries(awaiting, responses, found)
        return [found[match_id] for match_id in match_ids if match_id in found]

    def _store_summaries(
        self,
        match_ids: list[str],
        responses: list[HTTPResult | None],
        found: dict[str, MatchSummary],
    ) -> None:
        """Reduce successful match responses and cooldown the failed ones."""
        for match_id, response in zip(match_ids, responses, strict=True):
            summary = (
                _summary(match_id, response.data)
                if response is not None
                and response.status == 200
                and isinstance(response.data, dict)
                else None
            )
            if summary is None:
                self._summary_retry_at[match_id] = (
                    time.monotonic() + NEGATIVE_CACHE_SECONDS
                )
                continue
            self._summaries[match_id] = summary
            while len(self._summaries) > MATCH_SUMMARY_LIMIT:
                self._summaries.popitem(last=False)
            self._summary_retry_at.pop(match_id, None)
            found[match_id] = summary
        while len(self._summary_retry_at) > MATCH_SUMMARY_LIMIT:
            self._summary_retry_at.pop(next(iter(self._summary_retry_at)))


def _match_request(http: HTTPClient, region: str | None, match_id: str) -> Any:
    """Build one authenticated match-detail request for a batch."""

    def request(headers: dict[str, str]) -> Any:
        return http.request(
            "GET",
            pd_url(region, f"/match-details/v1/matches/{match_id}"),
            headers=headers,
        )

    return request


def _summary(match_id: str, raw: dict[str, Any]) -> MatchSummary | None:
    """Reduce one match-details payload, dropping matches without a team result."""
    info = raw.get("matchInfo")
    players = raw.get("players")
    teams = raw.get("teams")
    if not isinstance(info, dict) or not isinstance(players, list):
        return None
    teams_by_id = {
        str(team["teamId"]).casefold(): team
        for team in teams or []
        if isinstance(team, dict) and isinstance(team.get("teamId"), str)
    }
    if len(teams_by_id) < 2:
        return None
    hits = _hits_by_player(raw.get("roundResults"))
    stats: dict[str, PlayerStats] = {}
    for player in players:
        if not isinstance(player, dict) or not isinstance(player.get("subject"), str):
            continue
        subject = player["subject"].casefold()
        raw_stats = player.get("stats")
        numbers: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
        team_id = str(player.get("teamId", "")).casefold()
        team = teams_by_id.get(team_id)
        opponent = next(
            (row for key, row in teams_by_id.items() if key != team_id), None
        )
        won = team.get("won") if isinstance(team, dict) else None
        headshot_hits, total_hits = hits.get(subject, (0, 0))
        stats[subject] = PlayerStats(
            agent_id=identifier(player.get("characterId")),
            killed=nonnegative(numbers.get("kills")) or 0,
            died=nonnegative(numbers.get("deaths")) or 0,
            assisted=nonnegative(numbers.get("assists")) or 0,
            headshot_hits=headshot_hits,
            total_hits=total_hits,
            score=nonnegative(numbers.get("score")) or 0,
            rounds=nonnegative(numbers.get("roundsPlayed")) or 0,
            won=won if isinstance(won, bool) else None,
            rounds_won=nonnegative(team.get("roundsWon"))
            if isinstance(team, dict)
            else None,
            rounds_lost=nonnegative(opponent.get("roundsWon"))
            if isinstance(opponent, dict)
            else None,
        )
    if not stats:
        return None
    return MatchSummary(
        match_id=match_id,
        map_id=identifier(info.get("mapId")),
        queue_id=info.get("queueID") if isinstance(info.get("queueID"), str) else None,
        players=stats,
    )


def _hits_by_player(rounds: Any) -> dict[str, tuple[int, int]]:
    """Return headshot and total hit counts per player across every round."""
    hits: dict[str, tuple[int, int]] = {}
    for game_round in rounds or []:
        if not isinstance(game_round, dict):
            continue
        for entry in game_round.get("playerStats") or []:
            subject = entry.get("subject") if isinstance(entry, dict) else None
            if not isinstance(subject, str):
                continue
            headshots, total = hits.get(subject.casefold(), (0, 0))
            for damage in entry.get("damage") or []:
                if not isinstance(damage, dict):
                    continue
                heads = nonnegative(damage.get("headshots")) or 0
                headshots += heads
                total += (
                    heads
                    + (nonnegative(damage.get("bodyshots")) or 0)
                    + (nonnegative(damage.get("legshots")) or 0)
                )
            hits[subject.casefold()] = (headshots, total)
    return hits
