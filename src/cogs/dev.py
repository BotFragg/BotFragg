"""Owner-only operational commands for notices, cache refreshes, and diagnostics."""

from __future__ import annotations

import logging
from time import monotonic

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..services.analytics import command_stats
from ..services.dev_notices import READ_ACTION
from ..views import timestamp
from ..views.ui import embed, error, translated

log = logging.getLogger(__name__)


class DevCog(commands.Cog):
    """Owner-only maintenance, announcement, cache, and diagnostic controls."""

    dev = app_commands.Group(
        name="dev", description="Owner-only BotFragg operational controls"
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the running bot and register the announcement read button."""
        self.bot = bot
        bot.register_component(READ_ACTION, self.announcement_read)

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        """Authorize the bot owner and privately reject all other callers."""
        if await self.bot.is_owner(interaction.user):
            return True
        await error(interaction, "staff-owner-only")
        return False

    @dev.command(
        name="maintenance",
        description="Enable or disable the private maintenance notice",
        extras={"owner_only": True},
    )
    @app_commands.describe(
        enabled="Whether maintenance mode blocks every interaction",
        reason="Optional explanation shown to blocked users",
    )
    async def maintenance(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        reason: app_commands.Range[str, 1, 500] | None = None,
    ) -> None:
        """Persist the maintenance state and reply with the new state."""
        if not await self._owner_only(interaction):
            return
        try:
            await self.bot.dev_notices.set_maintenance(
                enabled=enabled, reason=reason, updated_by=interaction.user.id
            )
        except Exception:
            log.exception("Could not persist the maintenance state")
            await error(interaction, "dev-write-failed")
            return
        card = embed(
            translated(
                interaction,
                "dev-maintenance-enabled" if enabled else "dev-maintenance-disabled",
            ),
            title=translated(interaction, "dev-maintenance-title"),
        )
        if enabled and reason:
            card.add_field(
                name=translated(interaction, "dev-maintenance-reason"),
                value=reason,
                inline=False,
            )
        await interaction.response.send_message(embed=card, ephemeral=True)

    @dev.command(
        name="announce",
        description="Publish an announcement to every user until it is read",
        extras={"owner_only": True},
    )
    @app_commands.describe(text="Announcement text delivered privately")
    async def announce(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 2000],
    ) -> None:
        """Publish an announcement and reply with its identifier."""
        if not await self._owner_only(interaction):
            return
        try:
            announcement = await self.bot.dev_notices.publish(
                text, created_by=interaction.user.id
            )
        except Exception:
            log.exception("Could not publish the dev announcement")
            await error(interaction, "dev-write-failed")
            return
        card = embed(
            translated(interaction, "dev-announcement-published", id=announcement.id),
            title=translated(interaction, "dev-announcement-title"),
        )
        await interaction.response.send_message(embed=card, ephemeral=True)

    @dev.command(
        name="sync-cache",
        description="Refresh the VALORANT catalog and clear shop caches",
        extras={"owner_only": True},
    )
    async def sync_cache(self, interaction: discord.Interaction) -> None:
        """Force a catalog refresh, clear cached storefronts, and report counts."""
        if not await self._owner_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        started = monotonic()
        try:
            await self.bot.catalog.refresh()
            cleared = await self.bot.shop.clear_all_cached_storefronts()
        except Exception:
            log.exception("Could not refresh the catalog or clear the shop caches")
            await error(interaction, "error-command-failed")
            return
        card = embed(
            translated(
                interaction,
                "dev-sync-complete",
                skins=len(self.bot.catalog.skins),
                bundles=len(self.bot.catalog.bundles),
                accounts=cleared,
                seconds=f"{monotonic() - started:.1f}",
            )
        )
        await interaction.followup.send(embed=card, ephemeral=True)

    @dev.command(
        name="inspect",
        description="Show retained BotFragg data for a user or server",
        extras={"owner_only": True},
    )
    @app_commands.describe(
        type="Whether the ID belongs to a user or a server",
        id="Discord snowflake ID",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="user", value="user"),
            app_commands.Choice(name="server", value="server"),
        ]
    )
    async def inspect(
        self, interaction: discord.Interaction, type: str, id: str
    ) -> None:
        """Render the same diagnostics the old user and server commands showed."""
        if not await self._owner_only(interaction):
            return
        if not id.isdecimal() or len(id) > 20:
            await error(interaction, "dev-inspect-id-invalid")
            return
        identifier = int(id)
        await interaction.response.defer(thinking=True, ephemeral=True)
        if type == "user":
            try:
                user = self.bot.get_user(identifier) or await self.bot.fetch_user(
                    identifier
                )
            except discord.HTTPException:
                user = None
            if user is None:
                await error(interaction, "dev-inspect-user-missing")
                return
            card = await self._user_card(user)
        else:
            server = self.bot.get_guild(identifier)
            if server is None:
                await error(interaction, "dev-inspect-server-missing")
                return
            card = await self._server_card(server)
        await interaction.followup.send(embed=card, ephemeral=True)

    async def _user_card(self, user: discord.User) -> discord.Embed:
        """Build the retained user diagnostics shown by inspect."""
        command_count, favorite = await command_stats(user_id=user.id)
        shared_guilds = 0
        owned_guilds = 0
        for guild in self.bot.guilds:
            if guild.owner_id == user.id:
                shared_guilds += 1
                owned_guilds += 1
            elif guild.get_member(user.id):
                shared_guilds += 1
        card = embed(title=f"User information: {user}", colour=0x9C84EF)
        card.description = "\n".join(
            (
                f"**Full username:** [{user}](https://discord.com/users/{user.id})",
                f"**ID:** {user.id}",
                f"**Avatar URL:** [Click here]({user.display_avatar.url})",
                f"**Shared servers (cached; may be incomplete):** {shared_guilds}",
                f"**Owned servers:** {owned_guilds}",
                f"**Commands used (retained):** {command_count}",
                f"**Most used command:** {favorite or 'None'}",
            )
        )
        card.set_thumbnail(url=user.display_avatar.url)
        return card

    async def _server_card(self, server: discord.Guild) -> discord.Embed:
        """Build the retained server diagnostics shown by inspect."""
        command_count, favorite = await command_stats(guild_id=server.id)
        members = server.member_count
        member_count = members if members is not None else "Unknown"
        card = embed(title="Server information", colour=discord.Color.blurple().value)
        card.add_field(
            name="Key details",
            value="\n".join(
                (
                    f"**Server name:** {server.name}",
                    f"**Server ID:** {server.id}",
                    f"**Members (cached; may be outdated):** {member_count}",
                    f"**Owner:** <@{server.owner_id}> ({server.owner_id})",
                )
            ),
            inline=False,
        )
        card.add_field(
            name="Additional details",
            value="\n".join(
                (
                    f"**Created:** {timestamp(server.created_at)}",
                    f"**Commands used (retained):** {command_count}",
                    f"**Most used command:** {favorite or 'None'}",
                    f"**Channels / roles:** {len(server.channels)} / {len(server.roles)}",
                )
            ),
            inline=False,
        )
        if server.icon:
            card.set_thumbnail(url=server.icon.url)
        return card

    async def announcement_read(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Record one read announcement and replace its message without the button."""
        try:
            await self.bot.dev_notices.mark_read(interaction.user.id, int(payload))
        except Exception:
            log.exception("Could not record the dev announcement as read")
            await error(interaction, "dev-write-failed")
            return
        await interaction.response.edit_message(
            embed=embed(
                translated(interaction, "dev-announcement-read"),
                title=translated(interaction, "dev-announcement-title"),
            ),
            view=None,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the owner-only operational controls with the bot."""
    await bot.add_cog(DevCog(bot))
