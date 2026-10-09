"""Private command for viewing Riot matchmaking penalties."""

from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...localization import BotFraggTranslator
from ...models import Account
from ...services.accounts import account_for_user, selected_account
from ...services.auth import AuthenticationRequired
from ...services.gameplay import GameplayUnavailable, Penalty
from ...views import OwnedActionButton, timestamp
from ...views.ui import EmbedMessage, _account_display_name, embed, error, view

PENALTIES_PER_PAGE = 5


class PenaltiesCog(commands.Cog):
    """Display matchmaking penalties for the caller's selected VALORANT account."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the gameplay service and register pagination handling."""
        self.bot = bot
        bot.register_component("penalties_page", self.penalties_page)

    @app_commands.command(
        name=app_commands.locale_str("penalties", key="command-penalties-name"),
        description=app_commands.locale_str(
            "View your VALORANT matchmaking penalties.",
            key="command-penalties-description",
        ),
    )
    async def penalties(self, interaction: discord.Interaction) -> None:
        """Show Riot penalties privately for the caller's selected account."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            penalties = await self.bot.gameplay.penalties(account)
        except (AuthenticationRequired, GameplayUnavailable) as exc:
            await error(interaction, exc)
            return

        account = await account.persisted_row().select_related("user").get_or_none()
        if not account:
            await error(interaction, "error-account-unavailable")
            return
        player = _account_display_name(
            account.username,
            hide_ign=account.user.hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        card, controls = _penalties_page(
            interaction.user.id,
            account,
            player,
            penalties,
            0,
            self.bot.translator,
            interaction.locale,
        )
        kwargs: EmbedMessage = {"embed": card, "ephemeral": True}
        if controls is not None:
            kwargs["view"] = controls
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        await interaction.followup.send(**kwargs)

    async def penalties_page(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Validate pagination data, reload its owned account, and edit the page."""
        await interaction.response.defer()
        puuid, separator, raw_page = payload.partition(",")
        if not separator or not puuid:
            await error(interaction, "penalties-page-invalid")
            return
        try:
            page = int(raw_page)
        except ValueError:
            await error(interaction, "penalties-page-invalid")
            return

        account = await account_for_user(interaction.user.id, puuid)
        if not account:
            await error(interaction, "error-account-unavailable")
            return
        try:
            penalties = await self.bot.gameplay.penalties(account)
        except (AuthenticationRequired, GameplayUnavailable) as exc:
            await error(interaction, exc)
            return

        account = await account.persisted_row().select_related("user").get_or_none()
        if not account:
            await error(interaction, "error-account-unavailable")
            return
        player = _account_display_name(
            account.username,
            hide_ign=account.user.hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        card, controls = _penalties_page(
            interaction.user.id,
            account,
            player,
            penalties,
            page,
            self.bot.translator,
            interaction.locale,
        )
        await interaction.edit_original_response(
            embed=card,
            view=controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def _penalties_page(
    owner_id: int,
    account: Account,
    player: str,
    penalties: list[Penalty],
    page: int,
    translator: BotFraggTranslator,
    locale: discord.Locale,
) -> tuple[discord.Embed, discord.ui.View | None]:
    """Build one five-penalty embed page and owner-bound navigation controls."""
    if not penalties:
        return (
            embed(
                translator.text(locale, "penalties-empty", player=player),
                title=translator.text(locale, "penalties-title"),
            ),
            None,
        )

    page_count = (len(penalties) + PENALTIES_PER_PAGE - 1) // PENALTIES_PER_PAGE
    page %= page_count
    start = page * PENALTIES_PER_PAGE
    card = embed(
        translator.text(locale, "penalties-account", player=player),
        title=translator.text(locale, "penalties-title"),
    )
    for penalty in penalties[start : start + PENALTIES_PER_PAGE]:
        expiry = penalty.get("expires")
        expiry_text = (
            f"{timestamp(expiry, 'F')} ({timestamp(expiry)})"
            if isinstance(expiry, datetime)
            else translator.text(locale, "common-unknown")
        )
        games_remaining = penalty.get("games_remaining")
        effect_names = [
            translator.text(locale, f"penalties-effect-{value}")
            for value in penalty.get("effects", [])
            if isinstance(value, str)
        ]
        platform_scope = penalty.get("platform_scope")
        if platform_scope == "All platforms":
            platform_scope = translator.text(locale, "penalties-all-platforms")
        elif platform_scope == "Not specified" or not platform_scope:
            platform_scope = translator.text(locale, "common-not-specified")
        lines = [
            translator.text(locale, "penalties-expires", expiry=expiry_text),
            translator.text(
                locale,
                "penalties-games-remaining",
                games=(
                    str(games_remaining)
                    if isinstance(games_remaining, int)
                    else translator.text(locale, "common-unknown")
                ),
            ),
            translator.text(
                locale,
                "penalties-platform-scope",
                scope=platform_scope,
            ),
            translator.text(
                locale,
                "penalties-effects",
                effects=", ".join(effect_names)
                or translator.text(locale, "common-none-listed"),
            ),
        ]
        warning_details = []
        warning_type = penalty.get("warning_type")
        if isinstance(warning_type, str):
            warning_details.append(warning_type)
        if isinstance(penalty.get("warning_tier"), int):
            warning_details.append(
                translator.text(
                    locale, "penalties-warning-tier", tier=penalty["warning_tier"]
                )
            )
        if warning_details:
            lines.append(
                translator.text(
                    locale, "penalties-warning", warning=", ".join(warning_details)
                )
            )
        card.add_field(
            name=str(
                penalty.get("infraction")
                or translator.text(locale, "penalties-unknown-infraction")
            )[:128],
            value="\n".join(lines)[:900],
            inline=False,
        )
    controls = None
    if page_count > 1:
        card.set_footer(
            text=translator.text(
                locale, "common-page-of", page=page + 1, pages=page_count
            )
        )
        controls = view(
            OwnedActionButton(
                "penalties_page",
                owner_id,
                f"{account.puuid},{page - 1}",
                label=translator.text(locale, "common-previous"),
                emoji="◀",
            ),
            OwnedActionButton(
                "penalties_page",
                owner_id,
                f"{account.puuid},{page + 1}",
                label=translator.text(locale, "common-next"),
                emoji="▶",
            ),
        )
    return card, controls


async def setup(bot: BotFraggBot) -> None:
    """Register the private matchmaking-penalties command."""
    await bot.add_cog(PenaltiesCog(bot))
