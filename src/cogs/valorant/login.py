"""Private Riot sign-in flow using an authorization link and callback modal."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...views import OwnedActionButton
from ...views.ui import embed, localized_embed, translated, unexpected_error, view


class LoginModal(discord.ui.Modal):
    """Collect the redirect URL returned after a user signs in with Riot."""

    def __init__(self, bot: BotFraggBot, locale: discord.Locale) -> None:
        """Set a five-minute timeout and retain the authentication service owner."""
        super().__init__(
            title=bot.translator.text(locale, "login-modal-title"), timeout=300
        )
        self.bot = bot
        self.callback_url: discord.ui.TextInput = discord.ui.TextInput(
            label=bot.translator.text(locale, "login-modal-label"),
            placeholder=bot.translator.text(locale, "login-modal-placeholder"),
            style=discord.TextStyle.paragraph,
            max_length=1800,
        )
        self.add_item(self.callback_url)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Redeem the submitted callback and privately report the login result."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.auth.redeem_callback(
            interaction.user.id, str(self.callback_url)
        )
        if not result.success or result.account is None:
            await interaction.followup.send(
                embed=embed(
                    translated(
                        interaction,
                        result.error_key or "login-failed",
                        **result.error_arguments,
                    )
                ),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=localized_embed(
                interaction,
                "login-success",
                description_args={"username": result.account.username},
            ),
            ephemeral=True,
        )

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item | None = None,
        /,
    ) -> None:
        """Report unexpected login-form failures without exposing their details."""
        await unexpected_error(interaction, error)


class LoginCog(commands.Cog):
    """Start Riot sign-in and open the callback URL entry modal."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the persistent login-modal action."""
        self.bot = bot
        bot.register_component("login_modal", self.login_modal)

    @app_commands.command(
        name=app_commands.locale_str("login", key="command-login-name"),
        description=app_commands.locale_str(
            "Log in to your Riot account via browser.",
            key="command-login-description",
        ),
    )
    async def login(self, interaction: discord.Interaction) -> None:
        """Start a nonce-bound login; account creation limits belong to auth."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        url = self.bot.auth.login_url(interaction.user.id)
        login_button: discord.ui.Button = discord.ui.Button(
            label=translated(interaction, "login-button"),
            url=url,
            style=discord.ButtonStyle.link,
        )
        paste_button = OwnedActionButton(
            "login_modal",
            interaction.user.id,
            label=translated(interaction, "login-paste-button"),
            style=discord.ButtonStyle.green,
        )
        instructions = "".join(
            translated(interaction, key) + separator
            for key, separator in (
                ("login-instructions", "\n\n"),
                ("login-instructions-step-1", "\n"),
                ("login-instructions-step-2", "\n"),
                ("login-instructions-step-3", "\n"),
                ("login-instructions-step-4", "\n\n"),
                ("login-security-notice", ""),
            )
        )
        await interaction.followup.send(
            embed=embed(
                instructions,
                title=translated(interaction, "login-instructions-title"),
            ),
            view=view(login_button, paste_button),
            ephemeral=True,
        )

    async def login_modal(self, interaction: discord.Interaction, _: str) -> None:
        """Open the modal where the caller pastes Riot's redirect URL."""
        await interaction.response.send_modal(LoginModal(self.bot, interaction.locale))


async def setup(bot: BotFraggBot) -> None:
    """Register the Riot login command and modal handler."""
    await bot.add_cog(LoginCog(bot))
