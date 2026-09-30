"""Private commands for viewing and changing user display and shop preferences."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotfraggBot
from ...services.accounts import get_user, update_user_preference
from ...views import OwnedSelect
from ._ui import DARK, embed, error, view

SETTINGS = {
    "daily_shop_enabled": "Send your shop every day by DM",
    "hide_ign": "Hide in-game name",
    "others_can_view_shop": "Allow others to use /shop with your account",
}


class SettingsCog(commands.Cog):
    """Present user preferences and handle their owner-scoped select menu."""

    settings_group = app_commands.Group(
        name="settings", description="Change or view your bot settings"
    )

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the bot and register the persistent preference-selection action."""
        self.bot = bot
        bot.register_component("setting", self.setting_selected)

    @settings_group.command(name="view", description="See your current settings")
    async def settings_view(self, interaction: discord.Interaction) -> None:
        """Show the caller's saved preferences in an ephemeral response."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        user = await get_user(interaction.user.id)
        if not user:
            await error(
                interaction, "You're not registered with the bot! Try `/login`."
            )
            return
        result = embed(
            "Use `/settings set` to change them.",
            title="All your current settings:",
        )
        for field, label in SETTINGS.items():
            result.add_field(
                name=label, value="Yes" if getattr(user, field) else "No", inline=True
            )
        await interaction.followup.send(embed=result, ephemeral=True)

    @settings_group.command(name="set", description="Change one of your bot settings")
    @app_commands.choices(
        setting=[
            app_commands.Choice(name=label, value=field)
            for field, label in SETTINGS.items()
        ]
    )
    async def settings_set(
        self, interaction: discord.Interaction, setting: app_commands.Choice[str]
    ) -> None:
        """Present Yes/No options for the caller's selected preference."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not await get_user(interaction.user.id):
            await error(interaction, "You're not registered. Try `/login`.")
            return
        choices = [
            discord.SelectOption(label="Yes", value="true"),
            discord.SelectOption(label="No", value="false"),
        ]
        menu = OwnedSelect(
            "setting",
            interaction.user.id,
            setting.value,
            placeholder=f"Set {setting.name}",
            options=choices,
        )
        await interaction.followup.send(
            embed=embed(f"What do you want to set **{setting.name}** to?", colour=DARK),
            view=view(menu),
            ephemeral=True,
        )

    async def setting_selected(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Validate and persist a setting selection, then update its confirmation."""
        await interaction.response.defer()
        field, value = payload.split("|", 1)
        if field not in SETTINGS or value not in {"true", "false"}:
            await error(interaction, "Unknown setting.")
            return
        rendered = value == "true"
        if not await update_user_preference(interaction.user.id, field, rendered):
            await error(interaction, "You're not registered. Try `/login`.")
            return
        await interaction.edit_original_response(
            embed=embed(
                f"**{SETTINGS[field]}** is now set to **{'Yes' if rendered else 'No'}**."
            ),
            view=None,
        )


async def setup(bot: BotfraggBot) -> None:
    """Register the user preference commands and selection handler."""
    await bot.add_cog(SettingsCog(bot))
