"""Private commands for viewing and changing user display and shop preferences."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import get_user, update_user_preference
from ...views import OwnedSelect
from ...views.ui import DARK, embed, error, localized_embed, translated, view

SETTINGS = {
    "daily_shop_enabled": ("Send your shop every day by DM", "setting-daily-shop"),
    "hide_ign": ("Hide in-game name", "setting-hide-ign"),
    "others_can_view_shop": (
        "Allow others to use /shop with your account",
        "setting-share-shop",
    ),
}


class SettingsCog(commands.Cog):
    """Present user preferences and handle their owner-scoped select menu."""

    settings_group = app_commands.Group(
        name=app_commands.locale_str("settings", key="command-settings-name"),
        description=app_commands.locale_str(
            "Change or view your bot settings",
            key="command-settings-description",
        ),
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the persistent preference-selection action."""
        self.bot = bot
        bot.register_component("setting", self.setting_selected)

    @settings_group.command(
        name=app_commands.locale_str("view", key="command-settings-view-name"),
        description=app_commands.locale_str(
            "See your current settings", key="command-settings-view-description"
        ),
    )
    async def settings_view(self, interaction: discord.Interaction) -> None:
        """Show the caller's saved preferences in an ephemeral response."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        user = await get_user(interaction.user.id)
        if not user:
            await error(interaction, "error-not-registered")
            return
        result = localized_embed(
            interaction,
            "settings-view-description",
            title_key="settings-view-title",
        )
        for field, (_, label_key) in SETTINGS.items():
            result.add_field(
                name=translated(interaction, label_key),
                value=translated(
                    interaction,
                    "common-yes" if getattr(user, field) else "common-no",
                ),
                inline=True,
            )
        await interaction.followup.send(embed=result, ephemeral=True)

    @settings_group.command(
        name=app_commands.locale_str("set", key="command-settings-set-name"),
        description=app_commands.locale_str(
            "Change one of your bot settings",
            key="command-settings-set-description",
        ),
    )
    @app_commands.rename(
        setting=app_commands.locale_str(
            "setting", key="option-settings-set-setting-name"
        )
    )
    @app_commands.describe(
        setting=app_commands.locale_str(
            "Setting to change", key="option-settings-set-setting-description"
        )
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(
                name=app_commands.locale_str(label, key=label_key), value=field
            )
            for field, (label, label_key) in SETTINGS.items()
        ]
    )
    async def settings_set(
        self, interaction: discord.Interaction, setting: app_commands.Choice[str]
    ) -> None:
        """Present Yes/No options for the caller's selected preference."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not await get_user(interaction.user.id):
            await error(interaction, "error-not-registered")
            return
        choices = [
            discord.SelectOption(
                label=translated(interaction, "common-yes"), value="true"
            ),
            discord.SelectOption(
                label=translated(interaction, "common-no"), value="false"
            ),
        ]
        setting_label = translated(interaction, SETTINGS[setting.value][1])
        menu = OwnedSelect(
            "setting",
            interaction.user.id,
            setting.value,
            placeholder=translated(
                interaction, "settings-set-placeholder", setting=setting_label
            ),
            options=choices,
            empty_option_label=translated(interaction, "common-unavailable"),
        )
        await interaction.followup.send(
            embed=embed(
                translated(interaction, "settings-set-prompt", setting=setting_label),
                colour=DARK,
            ),
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
            await error(interaction, "settings-unknown-setting")
            return
        rendered = value == "true"
        if not await update_user_preference(interaction.user.id, field, rendered):
            await error(interaction, "error-not-registered")
            return
        await interaction.edit_original_response(
            embed=embed(
                translated(
                    interaction,
                    "settings-updated",
                    setting=translated(interaction, SETTINGS[field][1]),
                    value=translated(
                        interaction, "common-yes" if rendered else "common-no"
                    ),
                )
            ),
            view=None,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the user preference commands and selection handler."""
    await bot.add_cog(SettingsCog(bot))
