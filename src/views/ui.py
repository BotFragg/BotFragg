"""VALORANT cog presentation helpers for names, views, embeds, and errors."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, NotRequired, TypedDict

import discord
from discord import app_commands

from ..localization import BotFraggTranslator
from ..models import Account
from ..services.auth import AuthenticationRequired
from ..services.catalog import Accessory, Skin, localized_text
from ..services.http import DISCORD_HTTP_ERRORS, HTTPFailure


class EmbedMessage(TypedDict):
    """Keyword arguments for an embed response with optional controls."""

    embed: discord.Embed
    view: NotRequired[discord.ui.View]
    ephemeral: NotRequired[bool]
    allowed_mentions: NotRequired[discord.AllowedMentions]


RED = 0xFD4553
log = logging.getLogger(__name__)


def _account_display_name(
    username: str,
    *,
    hide_ign: bool,
    translator: BotFraggTranslator,
    locale: discord.Locale | str,
) -> str:
    """Return a generic account label when the user has chosen to hide their name."""
    if not hide_ign:
        return username
    return translator.text(locale, "account-hidden")


async def account_viewer(
    interaction: discord.Interaction[Any],
    account: Account,
    translator: BotFraggTranslator,
) -> tuple[Account, bool, str] | None:
    """Reload an owned account and return it with its hide flag and display label."""
    fresh = await account.persisted_row().select_related("user").get_or_none()
    if fresh is None:
        await error(interaction, "error-account-unavailable")
        return None
    hide_ign = fresh.user.hide_ign
    return (
        fresh,
        hide_ign,
        _account_display_name(
            fresh.username,
            hide_ign=hide_ign,
            translator=translator,
            locale=interaction.locale,
        ),
    )


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


def translated(
    interaction: discord.Interaction[Any], key: str, **arguments: object
) -> str:
    """Format one message using the caller's Discord locale."""
    return interaction.client.translator.text(interaction.locale, key, **arguments)


def localized_embed(
    interaction: discord.Interaction,
    description_key: str | None = None,
    *,
    title_key: str | None = None,
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


async def unexpected_error(
    interaction: discord.Interaction, exception: Exception
) -> None:
    """Log an unexpected interaction failure and send a private generic response."""
    log.error("Interaction failed", exc_info=exception)
    try:
        await error(interaction, "error-command-failed")
    except DISCORD_HTTP_ERRORS:
        log.warning("Could not deliver interaction error response", exc_info=True)


async def accessory(
    catalog: Any, item_type: str, identifier: str | None
) -> Accessory | None:
    """Resolve one equipped cosmetic, ignoring metadata failures."""
    if not identifier:
        return None
    try:
        return await catalog.accessory(item_type, identifier)
    except HTTPFailure:
        return None


def skin_video_options(
    skin: Skin, translator: BotFraggTranslator, locale: discord.Locale
) -> list[discord.SelectOption]:
    """List playable levels and chromas within Discord's select-menu limit."""
    options: list[discord.SelectOption] = []
    seen: set[str] = set()
    for kind, items in (
        (translator.text(locale, "skin-level"), skin.levels),
        (translator.text(locale, "skin-chroma"), skin.chromas),
    ):
        for item in items:
            uuid = str(item.get("uuid") or "")
            video = item.get("streamedVideo")
            if (
                not uuid
                or uuid in seen
                or not isinstance(video, str)
                or not video.startswith("https://")
            ):
                continue
            name = (
                localized_text(item.get("displayName"), locale)
                or skin.name_for(locale)
                or translator.text(locale, "common-unknown")
            )
            options.append(
                discord.SelectOption(label=f"{kind}: {name}"[:100], value=uuid)
            )
            seen.add(uuid)
            if len(options) == 25:
                return options
    return options


def skin_video(
    skin: Skin,
    variant_uuid: str,
    translator: BotFraggTranslator,
    locale: discord.Locale,
) -> tuple[str, str] | None:
    """Return the display name and inspect video for one level or chroma."""
    selected = next(
        (
            (kind, item)
            for kind, items in (
                ("level", skin.levels),
                ("chroma", skin.chromas),
            )
            for item in items
            if str(item.get("uuid") or "") == variant_uuid
        ),
        None,
    )
    if selected is None:
        return None
    kind, item = selected
    video = item.get("streamedVideo")
    if not isinstance(video, str) or not video.startswith("https://"):
        return None
    display_name = (
        skin.name_for(locale)
        if kind == "level"
        else localized_text(item.get("displayName"), locale) or skin.name_for(locale)
    ) or translator.text(locale, "common-unknown")
    # Variant names carry line breaks; links need a single line of text.
    return " ".join(display_name.split()), video


def timestamp(value: int | float | datetime, style: str = "R") -> str:
    """Format a timestamp as a Discord inline timestamp using the requested style."""
    seconds = int(value.timestamp()) if isinstance(value, datetime) else int(value)
    return f"<t:{seconds}:{style}>"
