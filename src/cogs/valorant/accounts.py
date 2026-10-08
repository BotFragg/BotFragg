"""Slash commands for selecting, listing, and paging through linked accounts."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...localization import BotFraggTranslator
from ...models import Account
from ...services.accounts import (
    get_user,
    list_accounts,
    resolve_account,
    select_account,
)
from ...views import OwnedActionButton
from ...views.ui import (
    EmbedMessage,
    _account_display_name,
    account_autocomplete_choices,
    embed,
    error,
    translated,
    view,
)

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
        return account_autocomplete_choices(
            await list_accounts(interaction.user.id), current
        )

    @staticmethod
    def _accounts_embed(
        accounts: list[Account],
        current_account_id: str | None,
        translator: BotFraggTranslator,
        locale: discord.Locale,
        page: int = 0,
        *,
        hide_ign: bool = False,
    ) -> discord.Embed:
        """Render one bounded account page and mark the currently selected entry."""
        pages = max(1, (len(accounts) + ACCOUNTS_PER_PAGE - 1) // ACCOUNTS_PER_PAGE)
        page %= pages
        title = translator.text(locale, "accounts-title")
        start = page * ACCOUNTS_PER_PAGE
        entries = []
        for index, account in enumerate(
            accounts[start : start + ACCOUNTS_PER_PAGE], start + 1
        ):
            username = _account_display_name(
                account.username or translator.text(locale, "account-no-username"),
                hide_ign=hide_ign,
                translator=translator,
                locale=locale,
            )
            if account.puuid == current_account_id:
                username = f"**{username}**"
            entries.append(
                translator.text(
                    locale, "accounts-entry", number=index, username=username
                )
            )
        result = embed("\n".join(entries), title=title)
        if pages > 1:
            result.set_footer(
                text=translator.text(
                    locale, "accounts-page", page=page + 1, pages=pages
                )
            )
        return result

    @staticmethod
    def _accounts_view(
        user_id: int, account_count: int, page: int
    ) -> discord.ui.View | None:
        """Build owner-scoped previous and next controls when multiple pages exist."""
        pages = (account_count + ACCOUNTS_PER_PAGE - 1) // ACCOUNTS_PER_PAGE
        if pages < 2:
            return None
        return view(
            OwnedActionButton("accounts_page", user_id, str(page - 1), emoji="◀"),
            OwnedActionButton("accounts_page", user_id, str(page + 1), emoji="▶"),
        )

    @app_commands.command(
        name=app_commands.locale_str("account", key="command-account-name"),
        description=app_commands.locale_str(
            "Switch the VALORANT account you are currently using",
            key="command-account-description",
        ),
    )
    @app_commands.rename(
        account=app_commands.locale_str("account", key="option-account-account-name")
    )
    @app_commands.describe(
        account=app_commands.locale_str(
            "Linked VALORANT account to switch to",
            key="option-account-account-description",
        )
    )
    @app_commands.autocomplete(account=account_autocomplete)
    async def account(self, interaction: discord.Interaction, account: str) -> None:
        """Switch the caller's active account using an autocomplete selection."""
        await interaction.response.defer(thinking=True)
        accounts = await list_accounts(interaction.user.id)
        target = await resolve_account(interaction.user.id, account, accounts=accounts)
        if not accounts or not target:
            await error(
                interaction,
                "account-not-found",
            )
            return
        user = await get_user(interaction.user.id)
        if not user:
            await error(interaction, "error-not-registered")
            return
        already_selected = user.current_account_id == target.puuid
        if not already_selected:
            try:
                await select_account(interaction.user.id, target)
            except ValueError:
                await error(interaction, "account-not-found")
                return
        target = await target.persisted_row().select_related("user").get_or_none()
        if not target:
            await error(interaction, "account-not-found")
            return
        username = _account_display_name(
            target.username,
            hide_ign=target.user.hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        if already_selected:
            await error(interaction, "account-already-selected", username=username)
            return
        number = next(
            index
            for index, item in enumerate(accounts, 1)
            if item.puuid == target.puuid
        )
        await interaction.followup.send(
            embed=embed(
                translated(
                    interaction,
                    "account-switched",
                    number=number,
                    username=username,
                )
            )
        )

    @app_commands.command(
        name=app_commands.locale_str("accounts", key="command-accounts-name"),
        description=app_commands.locale_str(
            "Show all of your VALORANT accounts",
            key="command-accounts-description",
        ),
    )
    async def accounts(self, interaction: discord.Interaction) -> None:
        """Show the caller's accounts privately when their name-hiding preference is on."""
        user = await get_user(interaction.user.id)
        ephemeral = bool(user and user.hide_ign)
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        accounts = await list_accounts(interaction.user.id)
        user = await get_user(interaction.user.id)
        if not user or not accounts:
            await error(interaction, "error-not-registered")
            return
        controls = self._accounts_view(interaction.user.id, len(accounts), 0)
        kwargs: EmbedMessage = {
            "embed": self._accounts_embed(
                accounts,
                user.current_account_id,
                self.bot.translator,
                interaction.locale,
                # The first followup inherits the visibility accepted by defer.
                hide_ign=user.hide_ign and not ephemeral,
            ),
            "ephemeral": ephemeral,
        }
        if controls is not None:
            kwargs["view"] = controls
        await interaction.followup.send(**kwargs)

    async def accounts_page(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Refresh an account page privately when an old public list now hides names."""
        await interaction.response.defer()
        try:
            page = int(payload)
        except ValueError:
            await error(interaction, "accounts-page-invalid")
            return
        accounts = await list_accounts(interaction.user.id)
        user = await get_user(interaction.user.id)
        if not user or not accounts:
            await error(interaction, "accounts-none-left")
            return
        card = self._accounts_embed(
            accounts,
            user.current_account_id,
            self.bot.translator,
            interaction.locale,
            page,
        )
        controls = self._accounts_view(interaction.user.id, len(accounts), page)
        if user.hide_ign and (
            interaction.message is None or not interaction.message.flags.ephemeral
        ):
            kwargs: EmbedMessage = {"embed": card, "ephemeral": True}
            if controls is not None:
                kwargs["view"] = controls
            await interaction.followup.send(**kwargs)
        else:
            await interaction.edit_original_response(embed=card, view=controls)


async def setup(bot: BotFraggBot) -> None:
    """Register the linked-account commands and component handlers."""
    await bot.add_cog(AccountsCog(bot))
