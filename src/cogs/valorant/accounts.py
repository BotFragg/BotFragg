"""Slash commands for selecting, listing, and paging through linked accounts."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...models import Account
from ...services.accounts import (
    get_user,
    list_accounts,
    resolve_account,
    select_account,
)
from ...views import OwnedActionButton
from ._ui import _account_display_name, embed, error

ACCOUNTS_PER_PAGE = 25


class AccountsCog(commands.Cog):
    """Present a user's linked Riot accounts and handle account selection."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the persistent account-page action."""
        self.bot = bot
        bot.register_component("accounts_page", self.accounts_page)

    async def account_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Return up to 25 of the caller's accounts matching the typed name."""
        return [
            app_commands.Choice(
                name=f"{index}. {account.username}", value=account.puuid
            )
            for index, account in enumerate(await list_accounts(interaction.user.id), 1)
            if current.casefold() in account.username.casefold()
        ][:25]

    @staticmethod
    def _accounts_embed(
        accounts: list[Account], current_account_id: str | None, page: int = 0
    ) -> discord.Embed:
        """Render one bounded account page and mark the currently selected entry."""
        pages = max(1, (len(accounts) + ACCOUNTS_PER_PAGE - 1) // ACCOUNTS_PER_PAGE)
        page %= pages
        title = "All your accounts with the bot:"
        start = page * ACCOUNTS_PER_PAGE
        entries = []
        for index, account in enumerate(
            accounts[start : start + ACCOUNTS_PER_PAGE], start + 1
        ):
            username = account.username or "[No username]"
            if account.puuid == current_account_id:
                username = f"**{username}**"
            entries.append(f"{index}. {username}")
        result = embed("\n".join(entries), title=title)
        if pages > 1:
            result.set_footer(text=f"Page {page + 1}/{pages}")
        return result

    @staticmethod
    def _accounts_view(
        user_id: int, account_count: int, page: int
    ) -> discord.ui.View | None:
        """Build owner-scoped previous and next controls when multiple pages exist."""
        pages = (account_count + ACCOUNTS_PER_PAGE - 1) // ACCOUNTS_PER_PAGE
        if pages < 2:
            return None
        view = discord.ui.View(timeout=None)
        view.add_item(
            OwnedActionButton("accounts_page", user_id, str(page - 1), emoji="◀")
        )
        view.add_item(
            OwnedActionButton("accounts_page", user_id, str(page + 1), emoji="▶")
        )
        return view

    @app_commands.command(
        name="account",
        description="Switch the VALORANT account you are currently using",
    )
    @app_commands.autocomplete(account=account_autocomplete)
    async def account(self, interaction: discord.Interaction, account: str) -> None:
        """Switch the caller's active account using an autocomplete selection."""
        await interaction.response.defer(thinking=True)
        accounts = await list_accounts(interaction.user.id)
        target = await resolve_account(interaction.user.id, account)
        if not accounts or not target:
            await error(
                interaction,
                "Couldn't find that account in your registered accounts. Try `/accounts`.",
            )
            return
        user = await get_user(interaction.user.id)
        if not user:
            await error(
                interaction, "You're not registered with the bot! Try `/login`."
            )
            return
        username = _account_display_name(target.username, hide_ign=user.hide_ign)
        if user.current_account_id == target.puuid:
            await error(interaction, f"**{username}** is already selected!")
            return
        await select_account(interaction.user.id, target)
        number = next(
            index
            for index, item in enumerate(accounts, 1)
            if item.puuid == target.puuid
        )
        await interaction.followup.send(
            embed=embed(f"Switched to account number **{number}. {username}**")
        )

    @app_commands.command(
        name="accounts", description="Show all of your VALORANT accounts"
    )
    async def accounts(self, interaction: discord.Interaction) -> None:
        """Show the caller's accounts privately when their name-hiding preference is on."""
        user = await get_user(interaction.user.id)
        accounts = await list_accounts(interaction.user.id)
        await interaction.response.defer(
            thinking=True, ephemeral=bool(user and user.hide_ign)
        )
        if not user or not accounts:
            await error(
                interaction, "You're not registered with the bot! Try `/login`."
            )
            return
        controls = self._accounts_view(interaction.user.id, len(accounts), 0)
        kwargs: dict[str, object] = {
            "embed": self._accounts_embed(accounts, user.current_account_id),
            "ephemeral": user.hide_ign,
        }
        if controls is not None:
            kwargs["view"] = controls
        await interaction.followup.send(**kwargs)

    async def accounts_page(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Handle a persistent account-page control and refresh its message."""
        await interaction.response.defer()
        try:
            page = int(payload)
        except ValueError:
            await error(interaction, "Invalid account page.")
            return
        user = await get_user(interaction.user.id)
        accounts = await list_accounts(interaction.user.id)
        if not user or not accounts:
            await error(interaction, "You no longer have any accounts.")
            return
        await interaction.edit_original_response(
            embed=self._accounts_embed(accounts, user.current_account_id, page),
            view=self._accounts_view(interaction.user.id, len(accounts), page),
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the linked-account commands and component handlers."""
    await bot.add_cog(AccountsCog(bot))
