"""Commands and embed builders for VALORANT battlepass and mission progress."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...localization import BotFraggTranslator
from ...services.accounts import get_user, selected_account
from ...services.auth import AuthenticationRequired
from ...services.emojis import ApplicationEmojiService
from ...services.gameplay import GameplayUnavailable
from ...views import timestamp
from ._ui import _account_display_name, embed, error


class BattlepassCog(commands.Cog):
    """Display the caller's current battlepass level and mission progress."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's gameplay, account, and emoji services."""
        self.bot = bot

    @app_commands.command(
        name=app_commands.locale_str("battlepass", key="command-battlepass-name"),
        description=app_commands.locale_str(
            "View battlepass progression.", key="command-battlepass-description"
        ),
    )
    async def battlepass(self, interaction: discord.Interaction) -> None:
        """Fetch and display the active battlepass for the caller's selected account."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            data = await self.bot.gameplay.battlepass(account)
        except (AuthenticationRequired, GameplayUnavailable) as exc:
            await error(interaction, exc)
            return
        filled_bar, empty_bar = await self.bot.emoji_service.battlepass_bars()
        user = await get_user(interaction.user.id)
        username = _account_display_name(
            account.username,
            hide_ign=bool(user and user.hide_ign),
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        card = self._battlepass_card(
            username,
            data,
            filled_bar or "█",
            empty_bar or "░",
            emoji_service=self.bot.emoji_service,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        await interaction.followup.send(embed=card)

    @app_commands.command(
        name=app_commands.locale_str("missions", key="command-missions-name"),
        description=app_commands.locale_str(
            "View your daily and weekly mission progress.",
            key="command-missions-description",
        ),
    )
    async def missions(self, interaction: discord.Interaction) -> None:
        """Show the selected account's daily and weekly mission progress privately."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            data = await self.bot.gameplay.missions(account)
        except (AuthenticationRequired, GameplayUnavailable) as exc:
            await error(interaction, exc)
            return
        filled_bar, empty_bar = await self.bot.emoji_service.battlepass_bars()
        await interaction.followup.send(
            embed=self._missions_card(
                data,
                filled_bar or "█",
                empty_bar or "░",
                translator=self.bot.translator,
                locale=interaction.locale,
            ),
            ephemeral=True,
        )

    @staticmethod
    def _missions_card(
        missions: list[dict],
        filled_bar: str = "█",
        empty_bar: str = "░",
        *,
        translator: BotFraggTranslator,
        locale: discord.Locale,
    ) -> discord.Embed:
        """Group mission entries by type and expiry and render progress bars."""
        card = embed(title=translator.text(locale, "missions-title"))
        if not missions:
            card.description = translator.text(locale, "missions-empty")
            return card
        groups: dict[tuple[str, object], list[dict]] = {}
        for mission in missions:
            key = (str(mission.get("type") or "Missions"), mission.get("expires"))
            groups.setdefault(key, []).append(mission)

        for (kind, expires), group in groups.items():
            name = kind
            if expires:
                name = translator.text(
                    locale,
                    "missions-group-expires",
                    kind=kind,
                    timestamp=timestamp(expires),
                )
            lines: list[str] = []
            for mission in group:
                title = " ".join(
                    str(
                        mission.get("title")
                        or translator.text(locale, "mission-default")
                    ).split()
                )
                xp = mission.get("xp")
                reward = (
                    translator.text(locale, "missions-xp", xp=xp)
                    if isinstance(xp, int) and not isinstance(xp, bool)
                    else translator.text(locale, "missions-xp-unavailable")
                )
                lines.append(
                    translator.text(
                        locale, "missions-title-reward", title=title, reward=reward
                    )
                )
                complete = bool(mission.get("complete"))
                tasks = mission.get("tasks") or []
                for task in tasks:
                    progress, target = task.get("progress"), task.get("target")
                    if isinstance(target, int) and target > 0 and complete:
                        progress = target
                    elif (
                        isinstance(progress, int)
                        and isinstance(target, int)
                        and target > 0
                    ):
                        progress = max(0, progress)
                    elif complete:
                        lines.append(filled_bar * 10)
                        continue
                    else:
                        lines.append(
                            translator.text(locale, "missions-progress-unavailable")
                        )
                        continue
                    filled = min(10, progress * 10 // target)
                    bar = filled_bar * filled + empty_bar * (10 - filled)
                    lines.append(
                        translator.text(
                            locale,
                            "missions-progress",
                            bar=bar,
                            progress=f"{min(progress, target):,}",
                            target=f"{target:,}",
                        )
                    )
                if not tasks:
                    lines.append(
                        filled_bar * 10
                        if complete
                        else translator.text(locale, "missions-progress-unavailable")
                    )
            card.add_field(name=name[:256], value="\n".join(lines)[:1024], inline=False)
        return card

    @staticmethod
    def _battlepass_card(
        player: str,
        data: dict,
        filled_bar: str = "█",
        empty_bar: str = "░",
        *,
        emoji_service: ApplicationEmojiService | None = None,
        translator: BotFraggTranslator,
        locale: discord.Locale,
    ) -> discord.Embed:
        """Render the active act, current tier, next reward, and XP progress bar."""
        progress = min(10, int(data["progress"] / max(1, data["next_level_xp"]) * 10))
        bar = filled_bar * progress + empty_bar * (10 - progress)
        reward = data["next_reward"]
        card = embed(
            translator.text(
                locale,
                "battlepass-summary",
                act=data["act"],
                timestamp=timestamp(data["end"]),
            ),
            title=player,
        )
        card.add_field(
            name=translator.text(locale, "battlepass-current-tier"),
            value=str(data["level"]),
            inline=False,
        )
        reward_name = reward["name"]
        if (tier_uuid := reward.get("tier_uuid")) and emoji_service:
            reward_name = emoji_service.skin_name(reward_name, tier_uuid)
        card.add_field(
            name=translator.text(locale, "battlepass-next-reward"),
            value=reward_name,
            inline=False,
        )
        card.add_field(
            name=translator.text(locale, "common-type"),
            value=reward["type"],
            inline=False,
        )
        card.add_field(
            name=translator.text(locale, "common-xp"),
            value=translator.text(
                locale,
                "battlepass-xp-progress",
                progress=f"{data['progress']:,}",
                target=f"{data['next_level_xp']:,}",
                bar=bar,
            ),
            inline=False,
        )
        if reward.get("icon"):
            if reward["type"] in {"PlayerCard", "EquippableSkinLevel"}:
                card.set_image(url=reward["icon"])
            else:
                card.set_thumbnail(url=reward["icon"])
        return card


async def setup(bot: BotFraggBot) -> None:
    """Register the battlepass and mission commands."""
    await bot.add_cog(BattlepassCog(bot))
