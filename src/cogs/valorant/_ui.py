"""VALORANT cog presentation helpers for names, views, embeds, and errors."""

from __future__ import annotations

import discord
from discord import app_commands

from ...localization import BotFraggTranslator
from ...models import Account
from ...services.auth import AuthenticationRequired

RED = 0xFD4553
DARK = 0x202225


def _account_display_name(
    username: str,
    *,
    hide_ign: bool,
    translator: BotFraggTranslator | None = None,
    locale: discord.Locale | str | None = "en-US",
) -> str:
    """Return a generic account label when the user has chosen to hide their name."""
    if not hide_ign:
        return username
    return translator.text(locale, "account-hidden") if translator else "Account"


def account_autocomplete_choices(
    accounts: list[Account], current: str
) -> list[app_commands.Choice[str]]:
    """Format account-name matches for Discord's bounded autocomplete menu."""
    return [
        app_commands.Choice(name=f"{index}. {account.username}", value=account.puuid)
        for index, account in enumerate(accounts, 1)
        if current.casefold() in account.username.casefold()
    ][:25]


def view(*items: discord.ui.Item) -> discord.ui.View:
    """Create a persistent view containing the supplied Discord components."""
    result = discord.ui.View(timeout=None)
    for item in items:
        result.add_item(item)
    return result


def embed(
    message: str | None = None, *, colour: int = RED, title: str | None = None
) -> discord.Embed:
    """Build a standard BotFragg embed with optional description, title, and colour."""
    return discord.Embed(title=title, description=message, colour=colour)


def translated(interaction: discord.Interaction, key: str, **arguments: object) -> str:
    """Format one message using the caller's Discord locale."""
    return interaction.client.translator.text(interaction.locale, key, **arguments)


def localized_embed(
    interaction: discord.Interaction,
    description_key: str | None = None,
    *,
    title_key: str | None = None,
    colour: int = DARK,
    description_args: dict[str, object] | None = None,
    title_args: dict[str, object] | None = None,
) -> discord.Embed:
    """Build an embed from catalog message IDs and the caller's locale."""
    return embed(
        translated(interaction, description_key, **(description_args or {}))
        if description_key
        else None,
        title=translated(interaction, title_key, **(title_args or {}))
        if title_key
        else None,
        colour=colour,
    )


async def error(
    interaction: discord.Interaction, message: str | Exception, **arguments: object
) -> None:
    """Send a private error embed using the interaction's available response path."""
    if isinstance(message, AuthenticationRequired):
        message = "error-riot-login-expired"
    elif isinstance(message, Exception):
        message = "error-riot-services-unavailable"
    message = translated(interaction, message, **arguments)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed(message), ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed(message), ephemeral=True)
