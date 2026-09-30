"""Commands for clearing Riot credentials or deleting all stored user data."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotfraggBot
from ...services.accounts import delete_user_data, list_accounts, resolve_account
from ._ui import embed, error


class LogoutCog(commands.Cog):
    """Let users disconnect Riot credentials or erase their Botfragg records."""

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the bot's account, authentication, and storefront services."""
        self.bot = bot

    async def account_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Return the caller's linked accounts for the logout command."""
        return [
            app_commands.Choice(
                name=f"{index}. {account.username}", value=account.puuid
            )
            for index, account in enumerate(await list_accounts(interaction.user.id), 1)
            if current.casefold() in account.username.casefold()
        ][:25]

    @app_commands.command(
        name="logout", description="Delete credentials but keep alerts and settings."
    )
    @app_commands.autocomplete(account=account_autocomplete)
    async def logout(
        self, interaction: discord.Interaction, account: str | None = None
    ) -> None:
        """Clear Riot credentials for one linked account while preserving its settings."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        target = await resolve_account(interaction.user.id, account)
        if not target:
            await error(
                interaction, "Couldn't find that account in your registered accounts!"
            )
            return
        await self.bot.auth.clear_credentials(target)
        await interaction.followup.send(
            embed=embed(
                f"Credentials for **{target.username}** were removed. Alerts and settings were kept."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="deletedata",
        description="Permanently delete your Botfragg account and data.",
    )
    async def deletedata(self, interaction: discord.Interaction, confirm: bool) -> None:
        """Permanently delete the caller's records and clear cached storefronts."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not confirm:
            await error(
                interaction,
                "Set **confirm** to **True** to permanently delete your data.",
            )
            return
        account_ids = [
            account.puuid for account in await list_accounts(interaction.user.id)
        ]
        if not await delete_user_data(interaction.user.id):
            await error(interaction, "You do not have any Botfragg data to delete.")
            return
        for account_id in account_ids:
            await self.bot.shop.clear_cached_storefront(account_id)
        await interaction.followup.send(
            embed=embed(
                "Your linked accounts, encrypted credentials, alerts, settings, command analytics, and stored suggestions were permanently deleted."
            ),
            ephemeral=True,
        )


async def setup(bot: BotfraggBot) -> None:
    """Register the account logout and personal data deletion commands."""
    await bot.add_cog(LogoutCog(bot))
