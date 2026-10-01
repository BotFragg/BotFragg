"""VALORANT cog presentation helpers for names, views, embeds, and errors."""

from __future__ import annotations

import discord
from discord import app_commands

from ...models import Account

RED = 0xFD4553
DARK = 0x202225


def _account_display_name(username: str, *, hide_ign: bool) -> str:
    """Return a generic account label when the user has chosen to hide their name."""
    return "Account" if hide_ign else username


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


async def error(interaction: discord.Interaction, message: str) -> None:
    """Send a private error embed using the interaction's available response path."""
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed(message), ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed(message), ephemeral=True)
