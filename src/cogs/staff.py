"""Owner-only Discord diagnostics for users, servers, and command analytics."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..services.accounts import command_stats, count_suggestions_by_author
from ..views import timestamp
from .valorant._ui import embed, error


class StaffCog(commands.Cog):
    """Owner-only operational diagnostics."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the staff diagnostics to the running bot."""
        self.bot = bot

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        """Authorize the bot owner and privately reject all other callers."""
        if await self.bot.is_owner(interaction.user):
            return True
        await error(interaction, "Only BotFragg's owner can use this command.")
        return False

    @app_commands.command(name="userinfo", description="Show BotFragg data for a user")
    @app_commands.guild_only()
    async def userinfo(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        """Show the owner's stored account statistics and shared-server details."""
        if not await self._owner_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        command_count, favorite = await command_stats(user_id=user.id)
        suggestion_count = await count_suggestions_by_author(user.id)
        shared_guilds = 0
        owned_guilds = 0
        for guild in self.bot.guilds:
            if guild.owner_id == user.id:
                shared_guilds += 1
                owned_guilds += 1
            elif guild.get_member(user.id):
                shared_guilds += 1
        card = embed(title=f"{user}'s information", colour=0x9C84EF)
        card.description = "\n".join(
            (
                f"**Full username:** [{user}](https://discord.com/users/{user.id})",
                f"**ID:** {user.id}",
                f"**Avatar URL:** [Click here]({user.display_avatar.url})",
                f"**Shared servers (cached; may be incomplete):** {shared_guilds}",
                f"**Owned servers:** {owned_guilds}",
                f"**Commands used:** {command_count}",
                f"**Suggestions made:** {suggestion_count}",
                f"**Favorite command:** {favorite or 'None'}",
            )
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=card, ephemeral=True)

    @app_commands.command(
        name="serverinfo", description="Show BotFragg data for a server"
    )
    @app_commands.guild_only()
    async def serverinfo(
        self, interaction: discord.Interaction, server_id: str
    ) -> None:
        """Show analytics and Discord's cached membership count for a server."""
        if not await self._owner_only(interaction):
            return
        if not server_id.isdecimal() or not (
            server := self.bot.get_guild(int(server_id))
        ):
            await error(interaction, "Provide the ID of a server BotFragg is in.")
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        command_count, favorite = await command_stats(guild_id=server.id)
        members = server.member_count
        member_count = str(members) if members is not None else "Unknown"
        card = embed(title="Server information", colour=discord.Color.blurple().value)
        card.add_field(
            name="Important information",
            value="\n".join(
                (
                    f"**Server name:** {server.name}",
                    f"**Server ID:** {server.id}",
                    f"**Total members (cached; may be stale):** {member_count}",
                    f"**Server owner:** <@{server.owner_id}> ({server.owner_id})",
                )
            ),
            inline=False,
        )
        card.add_field(
            name="Other information",
            value="\n".join(
                (
                    f"**Created:** {timestamp(server.created_at)}",
                    f"**Commands used:** {command_count}",
                    f"**Most used command:** {favorite or 'None'}",
                    f"**Channels / roles:** {len(server.channels)} / {len(server.roles)}",
                )
            ),
            inline=False,
        )
        if server.icon:
            card.set_thumbnail(url=server.icon.url)
        await interaction.followup.send(embed=card, ephemeral=True)


async def setup(bot: BotFraggBot) -> None:
    """Register the owner-only diagnostics cog with the bot."""
    await bot.add_cog(StaffCog(bot))
