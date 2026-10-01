"""Private Riot sign-in flow using an authorization link and callback modal."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import list_accounts
from ...views import OwnedActionButton
from ._ui import embed, error, view


class LoginModal(discord.ui.Modal, title="Paste your login URL"):
    """Collect the redirect URL returned after a user signs in with Riot."""

    callback_url = discord.ui.TextInput(
        label="Paste the URL from your browser here",
        placeholder="http://localhost/redirect?code=...",
        style=discord.TextStyle.paragraph,
        max_length=1800,
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Set a five-minute timeout and retain the authentication service owner."""
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Redeem the submitted callback and privately report the login result."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.auth.redeem_callback(
            interaction.user.id, str(self.callback_url)
        )
        if not result.success:
            await interaction.followup.send(
                embed=embed(result.error or "Login failed."), ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=embed(f"Successfully logged in as **{result.account.username}**."),
            ephemeral=True,
        )


class LoginCog(commands.Cog):
    """Start Riot sign-in and open the callback URL entry modal."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the persistent login-modal action."""
        self.bot = bot
        bot.register_component("login_modal", self.login_modal)

    @app_commands.command(
        name="login", description="Log in to your Riot account via browser."
    )
    async def login(self, interaction: discord.Interaction) -> None:
        """Start a nonce-bound Riot login when the caller has account capacity."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if (
            len(await list_accounts(interaction.user.id))
            >= self.bot.config.max_accounts_per_user
        ):
            await error(
                interaction,
                f"You can only have {self.bot.config.max_accounts_per_user} accounts. Log out of an existing account before adding another.",
            )
            return
        url = self.bot.auth.login_url(interaction.user.id)
        login_button = discord.ui.Button(
            label="Log in to Riot", url=url, style=discord.ButtonStyle.link
        )
        paste_button = OwnedActionButton(
            "login_modal",
            interaction.user.id,
            label="Paste URL",
            style=discord.ButtonStyle.green,
        )
        message = (
            "Connect a Riot account to view your personal VALORANT store, balances, "
            "battlepass progress, and alerts.\n\n"
            "**1.** Click **Log in to Riot** below and complete sign-in on Riot's website.\n"
            "**2.** After signing in, your browser may show a blank page, a connection "
            "error, or an error page. This is expected—keep that tab open.\n"
            "**3.** Copy the complete URL from your browser's address bar.\n"
            "**4.** Click **Paste URL** and paste the copied URL to finish connecting your account.\n\n"
            "Only paste the redirect URL—never share your Riot password, verification code, "
            "or recovery codes."
        )
        await interaction.followup.send(
            embed=embed(message, title="Login to your Riot account"),
            view=view(login_button, paste_button),
            ephemeral=True,
        )

    async def login_modal(self, interaction: discord.Interaction, _: str) -> None:
        """Open the modal where the caller pastes Riot's redirect URL."""
        await interaction.response.send_modal(LoginModal(self.bot))


async def setup(bot: BotFraggBot) -> None:
    """Register the Riot login command and modal handler."""
    await bot.add_cog(LoginCog(bot))
