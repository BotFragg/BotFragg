"""Commands for clearing Riot credentials or deleting all stored user data."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import delete_user_data, list_accounts, resolve_account
from ._ui import account_autocomplete_choices, error, localized_embed


class LogoutCog(commands.Cog):
    """Let users disconnect Riot credentials or erase their BotFragg records."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's account, authentication, and storefront services."""
        self.bot = bot

    async def account_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Return the caller's linked accounts for the logout command."""
        return account_autocomplete_choices(
            await list_accounts(interaction.user.id), current
        )

    @app_commands.command(
        name=app_commands.locale_str("logout", key="command-logout-name"),
        description=app_commands.locale_str(
            "Delete credentials but keep alerts and settings.",
            key="command-logout-description",
        ),
    )
    @app_commands.autocomplete(account=account_autocomplete)
    async def logout(
        self, interaction: discord.Interaction, account: str | None = None
    ) -> None:
        """Clear Riot credentials for one linked account while preserving its settings."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        target = await resolve_account(interaction.user.id, account)
        if not target:
            await error(interaction, "logout-account-not-found")
            return
        await self.bot.auth.clear_credentials(target)
        await interaction.followup.send(
            embed=localized_embed(
                interaction,
                "logout-success",
                description_args={"username": target.username},
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name=app_commands.locale_str("deletedata", key="command-deletedata-name"),
        description=app_commands.locale_str(
            "Permanently delete your BotFragg account and data.",
            key="command-deletedata-description",
        ),
    )
    async def deletedata(self, interaction: discord.Interaction, confirm: bool) -> None:
        """Permanently delete the caller's records and clear cached storefronts."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not confirm:
            await error(
                interaction,
                "deletedata-confirm-required",
            )
            return
        account_ids = [
            account.puuid for account in await list_accounts(interaction.user.id)
        ]
        if not await delete_user_data(interaction.user.id):
            await error(interaction, "deletedata-no-data")
            return
        for account_id in account_ids:
            await self.bot.shop.clear_cached_storefront(account_id)
        await interaction.followup.send(
            embed=localized_embed(
                interaction,
                "deletedata-success",
            ),
            ephemeral=True,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the account logout and personal data deletion commands."""
    await bot.add_cog(LogoutCog(bot))
