"""Commands for viewing a linked account's VALORANT profile card."""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...localization import BotFraggTranslator
from ...models import Account
from ...services.accounts import get_user, selected_account
from ...services.auth import AuthenticationRequired
from ...services.catalog import (
    PLAYER_CARD_ITEM_TYPE_ID,
    PLAYER_TITLE_ITEM_TYPE_ID,
    Accessory,
    localized_text,
)
from ...services.emojis import ApplicationEmojiService
from ...services.http import HTTPFailure
from ...services.matches import MatchesUnavailable, MatchSummary
from ...services.profile import PlayerProfile, ProfileUnavailable
from ...views.ui import DARK, account_viewer, embed, error

log = logging.getLogger(__name__)

COMPETITIVE_QUEUE = "competitive"
FOREIGN_VIEW_COOLDOWN_SECONDS = 30
# Discord trims leading whitespace, so the stat line is indented with a
# visible corner arrow.
STAT_INDENT = "↳ "


class ProfileCog(commands.Cog):
    """Display the caller's rank, level, and most recent matches."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's profile, match, catalog, and emoji services."""
        self.bot = bot
        self._foreign_views: dict[int, float] = {}

    @app_commands.command(
        name=app_commands.locale_str("profile", key="command-profile-name"),
        description=app_commands.locale_str(
            "View a VALORANT profile",
            key="command-profile-description",
        ),
    )
    @app_commands.rename(
        user=app_commands.locale_str("user", key="option-profile-user-name")
    )
    @app_commands.describe(
        user=app_commands.locale_str(
            "User whose profile to view",
            key="option-profile-user-description",
        )
    )
    async def profile(
        self, interaction: discord.Interaction, user: discord.User | None = None
    ) -> None:
        """Show the caller's or another user's shared profile card."""
        await interaction.response.defer(thinking=True)
        target = user or interaction.user
        foreign = target.id != interaction.user.id
        granted = False

        def release() -> None:
            """Give the view slot back when no card is delivered."""
            if granted:
                self._foreign_views.pop(interaction.user.id, None)

        if foreign:
            wait = self._claim_foreign_view(interaction.user.id)
            if wait:
                await error(interaction, "profile-cooldown", seconds=wait)
                return
            granted = True
            settings = await get_user(target.id)
            if not settings or not settings.others_can_view_profile:
                release()
                await error(interaction, "profile-user-not-sharing")
                return
        account = await selected_account(target.id)
        if not account:
            release()
            await error(
                interaction,
                "profile-user-not-registered" if foreign else "error-not-registered",
            )
            return
        viewer = await account_viewer(interaction, account, self.bot.translator)
        if viewer is None:
            release()
            return
        account, _, username = viewer
        if foreign and not account.user.others_can_view_profile:
            release()
            await error(interaction, "profile-user-not-sharing")
            return
        data_result, matches_result = await asyncio.gather(
            self.bot.profiles.profile(account),
            self.bot.matches.recent(account, queue=COMPETITIVE_QUEUE),
            return_exceptions=True,
        )
        if isinstance(data_result, BaseException):
            if isinstance(data_result, AuthenticationRequired):
                release()
                await error(
                    interaction,
                    "profile-user-login-expired" if foreign else data_result,
                )
                return
            if isinstance(data_result, ProfileUnavailable):
                release()
                await error(interaction, data_result)
                return
            raise data_result
        data = data_result
        matches = matches_result if isinstance(matches_result, list) else []
        if isinstance(matches_result, BaseException) and not isinstance(
            matches_result, (AuthenticationRequired, MatchesUnavailable)
        ):
            raise matches_result
        card_art, title, act, bars, ranked = await asyncio.gather(
            self._accessory(PLAYER_CARD_ITEM_TYPE_ID, data.card_id),
            self._accessory(PLAYER_TITLE_ITEM_TYPE_ID, data.title_id),
            self.bot.catalog.current_act(),
            self.bot.emoji_service.battlepass_bars(),
            self._ranked_changes(account, matches),
        )
        rank_names, map_names = await asyncio.gather(
            self.bot.catalog.ranks(),
            self.bot.catalog.maps(),
        )
        filled_bar, empty_bar = bars
        emoji_service = self.bot.emoji_service
        # Emoji creation is slow and optional, so it stays off the card's path.
        asyncio.create_task(emoji_service.ensure_profile_emojis()).add_done_callback(
            _log_emoji_failure
        )
        card = self._profile_card(
            username,
            account,
            data,
            matches,
            ranked=ranked,
            card_art=card_art,
            title_text=title.title_text_for(interaction.locale) if title else None,
            rank_names=rank_names,
            map_names=map_names,
            act_names=act[1] if act else {},
            emoji_service=emoji_service,
            translator=self.bot.translator,
            locale=interaction.locale,
            filled_bar=filled_bar or "█",
            empty_bar=empty_bar or "░",
        )
        await interaction.followup.send(embed=card)

    async def _ranked_changes(
        self, account: Account, matches: list[MatchSummary]
    ) -> dict[str, int]:
        """Return the RR change per shown match, tolerating unavailable data."""
        if not matches:
            return {}
        try:
            return await self.bot.matches.ranked_changes(account)
        except AuthenticationRequired, MatchesUnavailable:
            return {}

    def _claim_foreign_view(self, user_id: int) -> int:
        """Reserve a third-party view slot, returning the wait when one is active."""
        now = time.monotonic()
        retry_at = self._foreign_views.get(user_id, 0.0)
        if retry_at > now:
            return max(1, round(retry_at - now))
        self._foreign_views[user_id] = now + FOREIGN_VIEW_COOLDOWN_SECONDS
        if len(self._foreign_views) > 1024:
            self._foreign_views = {
                key: value for key, value in self._foreign_views.items() if value > now
            }
        return 0

    async def _accessory(
        self, item_type: str, identifier: str | None
    ) -> Accessory | None:
        """Resolve one equipped cosmetic, ignoring metadata failures."""
        if not identifier:
            return None
        try:
            return await self.bot.catalog.accessory(item_type, identifier)
        except HTTPFailure:
            return None

    @staticmethod
    def _profile_card(
        player: str,
        account: Account,
        data: PlayerProfile,
        matches: list[MatchSummary],
        *,
        ranked: dict[str, int],
        card_art: Accessory | None,
        title_text: str | None,
        rank_names: dict[int, dict[str, str]],
        map_names: dict[str, dict[str, str]],
        act_names: dict[str, str],
        emoji_service: ApplicationEmojiService,
        translator: BotFraggTranslator,
        locale: discord.Locale,
        filled_bar: str = "█",
        empty_bar: str = "░",
    ) -> discord.Embed:
        """Render the rank, level, and recent-match blocks of a profile card."""
        card = embed(colour=DARK)
        lines: list[str] = [f"**{player}**"]
        if title_text:
            lines.append(f"-# {title_text}")
        # The name and equipped title stay together; the rank block is separate.
        lines.append("")
        rank_emoji = emoji_service.rank_emoji(data.tier)
        rank_name = localized_text(rank_names.get(data.tier), locale)
        if data.tier and rank_name:
            rank_line = f"{rank_emoji} **{rank_name}**".strip()
        else:
            rank_line = f"**{translator.text(locale, 'profile-unranked')}**"
        if data.rr is not None:
            rank_line += f" · {translator.text(locale, 'profile-rr', rr=data.rr)}"
        if data.wins is not None and data.games:
            percent = round(data.wins * 100 / data.games)
            rank_line += (
                f" · {translator.text(locale, 'profile-winrate', percent=percent)}"
            )
        lines.append(rank_line)
        if (
            data.peak_tier
            and data.peak_tier > data.tier
            and (peak_name := localized_text(rank_names.get(data.peak_tier), locale))
        ):
            peak = f"{emoji_service.rank_emoji(data.peak_tier)} {peak_name}".strip()
            lines.append(f"-# {translator.text(locale, 'profile-peak', rank=peak)}")
        if data.level is not None:
            level_line = translator.text(locale, "profile-level", level=data.level)
            target = data.xp_target
            if data.xp is not None and target:
                progress = translator.text(
                    locale,
                    "profile-xp",
                    xp=f"{data.xp:,}",
                    target=f"{target:,}",
                )
                lines.append(f"{level_line} · {progress}")
                filled = min(10, data.xp * 10 // target)
                lines.append(f"{filled_bar * filled}{empty_bar * (10 - filled)}")
            else:
                lines.append(level_line)
        card.description = "\n".join(lines)
        match_lines = [
            _match_block(
                summary,
                puuid=account.puuid,
                map_names=map_names,
                rr_change=ranked.get(summary.match_id),
                emoji_service=emoji_service,
                translator=translator,
                locale=locale,
            )
            for summary in matches
        ]
        card.add_field(
            name=translator.text(locale, "profile-last-matches"),
            value="\n".join(line for line in match_lines if line)
            or f"-# {translator.text(locale, 'profile-no-matches')}",
            inline=False,
        )
        if card_art is not None and (card_art.small_icon or card_art.icon):
            card.set_thumbnail(url=card_art.small_icon or card_art.icon)
        footer = " · ".join(
            part
            for part in (
                (account.region or "").upper(),
                localized_text(act_names, locale),
            )
            if part
        )
        if footer:
            card.set_footer(text=footer)
        return card


def _match_block(
    summary: MatchSummary,
    *,
    puuid: str,
    map_names: dict[str, dict[str, str]],
    rr_change: int | None = None,
    emoji_service: ApplicationEmojiService,
    translator: BotFraggTranslator,
    locale: discord.Locale,
) -> str:
    """Render one match as a result line and an indented stat line."""
    stats = summary.player(puuid)
    if stats is None or stats.won is None:
        return ""
    map_name = _map_name(summary.map_id, map_names, locale)
    queue_name = (
        translator.text(locale, "profile-queue-competitive")
        if summary.queue_id == COMPETITIVE_QUEUE
        else ""
    )
    prefix = " ".join(
        part
        for part in (
            "🟢" if stats.won else "🔴",
            emoji_service.queue_emoji(summary.queue_id),
            queue_name,
        )
        if part
    )
    body = " ".join(
        part
        for part in (
            f"**{map_name}**" if map_name else "",
            f"{stats.rounds_won}-{stats.rounds_lost}"
            if stats.rounds_won is not None and stats.rounds_lost is not None
            else "",
        )
        if part
    )
    tail = f"{rr_change:+d} RR" if rr_change is not None else ""
    head = " · ".join(part for part in (prefix, body, tail) if part)
    parts = [f"{stats.killed}/{stats.died}/{stats.assisted}"]
    if (percent := stats.headshot_percent) is not None:
        parts.append(translator.text(locale, "profile-hs", percent=percent))
    if (score := stats.combat_score) is not None:
        parts.append(translator.text(locale, "profile-acs", acs=score))
    agent = emoji_service.agent_emoji(stats.agent_id)
    detail = " ".join(part for part in (agent, " · ".join(parts)) if part)
    return f"{head}\n-# {STAT_INDENT}{detail}"


def _map_name(
    map_id: str | None,
    map_names: dict[str, dict[str, str]],
    locale: discord.Locale,
) -> str:
    """Return the localized map name for Riot's map path or identifier."""
    if not map_id:
        return ""
    return localized_text(map_names.get(map_id.casefold()), locale)


def _log_emoji_failure(task: asyncio.Task[None]) -> None:
    """Log an emoji-creation failure instead of leaving the task exception unread."""
    if not task.cancelled() and (error := task.exception()):
        log.warning("Could not create profile emojis", exc_info=error)


async def setup(bot: BotFraggBot) -> None:
    """Register the profile command."""
    await bot.add_cog(ProfileCog(bot))
