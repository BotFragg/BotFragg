"""Commands for viewing and exporting the caller's VALORANT crosshairs."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...models import Account
from ...services.accounts import account_for_user, selected_account
from ...services.auth import AuthenticationRequired
from ...services.crosshair import CrosshairProfile, CrosshairUnavailable
from ...services.http import HTTPFailure
from ...views.ui import DARK, embed, error, translated

MAX_OPTIONS = 25
VIEW_TIMEOUT = 900


class CrosshairView(discord.ui.View):
    """Owner-scoped profile selector for one crosshair message."""

    def __init__(
        self,
        cog: CrosshairCog,
        interaction: discord.Interaction,
        account: Account,
        profiles: Sequence[CrosshairProfile],
        selected: CrosshairProfile,
    ) -> None:
        """Build the selector from the caller's profiles."""
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.owner_id = interaction.user.id
        self.account = account
        self.profiles = list(profiles)
        options = []
        for profile in self._visible(profiles):
            options.append(
                discord.SelectOption(
                    label=profile.name[:100],
                    value=str(profile.index),
                    description=(
                        translated(interaction, "crosshair-current-profile")
                        if profile.current
                        else None
                    ),
                    default=profile.index == selected.index,
                )
            )
        self.add_item(CrosshairSelect(interaction, options))

    @staticmethod
    def _visible(profiles: Sequence[CrosshairProfile]) -> list[CrosshairProfile]:
        """Keep the current profile first and cap the menu at Discord's limit."""
        if len(profiles) <= MAX_OPTIONS:
            return list(profiles)
        current = next(
            (profile for profile in profiles if profile.current), profiles[0]
        )
        rest = [profile for profile in profiles if profile is not current]
        return [current, *rest[: MAX_OPTIONS - 1]]

    async def profile_selected(
        self, interaction: discord.Interaction, index: int
    ) -> None:
        """Recheck ownership and edit the message with the chosen profile."""
        if interaction.user.id != self.owner_id:
            await error(interaction, "error-command-failed")
            return
        current = await account_for_user(interaction.user.id, self.account.puuid)
        if current is None or current.created_at != self.account.created_at:
            await error(interaction, "error-not-registered")
            return
        profile = next(
            (profile for profile in self.profiles if profile.index == index),
            None,
        )
        if profile is None:
            await error(interaction, "crosshair-unavailable")
            return
        try:
            card, file, controls = await self.cog.build_card(
                interaction, current, self.profiles, profile
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        await interaction.response.edit_message(
            embed=card, attachments=[file], view=controls
        )


class CrosshairSelect(discord.ui.Select):
    """Select one crosshair profile from the owner's saved profiles."""

    def __init__(
        self, interaction: discord.Interaction, options: list[discord.SelectOption]
    ) -> None:
        """Build the selector with the interaction's localized placeholder."""
        super().__init__(
            placeholder=translated(interaction, "crosshair-select-placeholder"),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Forward the selection to the owning view."""
        view = self.view
        if isinstance(view, CrosshairView):
            await view.profile_selected(interaction, int(self.values[0]))


class CrosshairCog(commands.Cog):
    """View and export the caller's VALORANT crosshair profiles."""

    crosshair_group = app_commands.Group(
        name=app_commands.locale_str("crosshair", key="command-crosshair-name"),
        description=app_commands.locale_str(
            "View and copy your in-game crosshairs",
            key="command-crosshair-description",
        ),
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's crosshair service."""
        self.bot = bot

    @crosshair_group.command(
        name=app_commands.locale_str("view", key="command-crosshair-view-name"),
        description=app_commands.locale_str(
            "Show your crosshair profile, export code, and preview",
            key="command-crosshair-view-description",
        ),
    )
    async def crosshair_view(self, interaction: discord.Interaction) -> None:
        """Show the caller's current crosshair, its code, and a profile menu."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            profiles = await self.bot.crosshair.profiles(account)
        except AuthenticationRequired as exc:
            await error(interaction, exc)
            return
        except CrosshairUnavailable, HTTPFailure:
            await error(interaction, "crosshair-unavailable")
            return
        current = next(
            (profile for profile in profiles if profile.current), profiles[0]
        )
        try:
            card, file, controls = await self.build_card(
                interaction, account, profiles, current
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        await interaction.followup.send(
            embed=card, file=file, view=controls, ephemeral=True
        )

    async def build_card(
        self,
        interaction: discord.Interaction,
        account: Account,
        profiles: Sequence[CrosshairProfile],
        profile: CrosshairProfile,
    ) -> tuple[discord.Embed, discord.File, CrosshairView]:
        """Render one profile into an embed, attachment, and selector view."""
        try:
            png = await asyncio.to_thread(self.bot.crosshair.render_png, profile)
        except ValueError:
            raise CrosshairUnavailable("The crosshair could not be rendered") from None
        card = embed(
            translated(interaction, "crosshair-code-block", code=profile.code),
            title=translated(
                interaction,
                "crosshair-title",
                name=discord.utils.escape_markdown(profile.name),
            ),
            colour=DARK,
        )
        card.set_image(url="attachment://crosshair.png")
        if len(profiles) > MAX_OPTIONS:
            card.set_footer(
                text=translated(
                    interaction,
                    "crosshair-more-profiles",
                    count=len(profiles) - MAX_OPTIONS,
                )
            )
        file = discord.File(io.BytesIO(png), filename="crosshair.png")
        controls = CrosshairView(self, interaction, account, list(profiles), profile)
        return card, file, controls


async def setup(bot: BotFraggBot) -> None:
    """Register the crosshair command group."""
    await bot.add_cog(CrosshairCog(bot))
