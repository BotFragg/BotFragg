"""Public VALORANT service status for a selected region."""

from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import selected_account
from ...services.valorant_status import (
    SUPPORTED_REGIONS,
    StatusEntry,
    StatusUnavailable,
)
from ...views.ui import DARK, embed, error, timestamp, translated

MAX_ENTRIES = 5
PLATFORM_NAMES = {"windows": "Windows", "ps5": "PlayStation 5", "xbox": "Xbox"}


def _entry_field(entry: StatusEntry) -> tuple[str, str]:
    """Format one status entry as an embed field name and value."""
    icon = "🛠" if entry.kind == "maintenance" else "⚠️"
    lines: list[str] = []
    if entry.body:
        lines.append(entry.body)
    if entry.updated:
        lines.append(f"🕓 {timestamp(entry.updated)}")
    if entry.platforms:
        platforms = " · ".join(
            PLATFORM_NAMES.get(platform, platform.title())
            for platform in entry.platforms
        )
        lines.append(f"-# {platforms}")
    return f"{icon} {entry.title}"[:256], ("\n".join(lines) or "—")[:1024]


class StatusCog(commands.Cog):
    """Show Riot's public VALORANT service status."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's status service."""
        self.bot = bot

    @app_commands.command(
        name=app_commands.locale_str("status", key="command-status-name"),
        description=app_commands.locale_str(
            "Show the VALORANT service status for a region",
            key="command-status-description",
        ),
    )
    @app_commands.rename(
        region=app_commands.locale_str("region", key="option-status-region-name")
    )
    @app_commands.describe(
        region=app_commands.locale_str(
            "Region to check (defaults to your account's region)",
            key="option-status-region-description",
        )
    )
    @app_commands.choices(
        region=[
            app_commands.Choice(name=code.upper(), value=code)
            for code in SUPPORTED_REGIONS
        ]
    )
    async def status(
        self, interaction: discord.Interaction, region: str | None = None
    ) -> None:
        """Show incidents and maintenance reported for one region."""
        await interaction.response.defer(thinking=True)
        chosen = region
        if chosen is None:
            account = await selected_account(interaction.user.id)
            chosen = account.region if account else None
        try:
            data = await self.bot.valorant_status.status(chosen, interaction.locale)
        except StatusUnavailable:
            await error(interaction, "error-riot-services-unavailable")
            return
        card = embed(
            title=translated(interaction, "status-title", region=data.region.upper()),
            colour=DARK,
        )
        hidden = len(data.entries) - MAX_ENTRIES
        if not data.entries:
            card.description = translated(interaction, "status-all-clear")
        elif hidden > 0:
            card.description = translated(interaction, "status-more", count=hidden)
        for entry in data.entries[:MAX_ENTRIES]:
            name, value = _entry_field(entry)
            card.add_field(name=name, value=value, inline=False)
        card.timestamp = datetime.now(UTC)
        await interaction.followup.send(embed=card)


async def setup(bot: BotFraggBot) -> None:
    """Register the public status command."""
    await bot.add_cog(StatusCog(bot))
