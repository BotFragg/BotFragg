"""Owner-only Discord diagnostics for users, servers, and command analytics."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..services.accounts import command_stats, count_suggestions_by_author
from ..views import timestamp
from .valorant._ui import embed, error, translated


class StaffCog(commands.Cog):
    """Owner-only operational diagnostics."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the staff diagnostics to the running bot."""
        self.bot = bot

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        """Authorize the bot owner and privately reject all other callers."""
        if await self.bot.is_owner(interaction.user):
            return True
        await error(interaction, "staff-owner-only")
        return False

    @app_commands.command(
        name=app_commands.locale_str("userinfo", key="command-userinfo-name"),
        description=app_commands.locale_str(
            "Show BotFragg data for a user", key="command-userinfo-description"
        ),
    )
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
        card = embed(
            title=translated(interaction, "staff-userinfo-title", username=str(user)),
            colour=0x9C84EF,
        )
        card.description = "\n".join(
            (
                translated(
                    interaction,
                    "staff-userinfo-full-username",
                    username=f"[{user}](https://discord.com/users/{user.id})",
                ),
                translated(interaction, "staff-userinfo-id", value=str(user.id)),
                translated(
                    interaction,
                    "staff-userinfo-avatar",
                    link=f"[Click here]({user.display_avatar.url})",
                ),
                translated(
                    interaction, "staff-userinfo-shared-servers", count=shared_guilds
                ),
                translated(
                    interaction, "staff-userinfo-owned-servers", count=owned_guilds
                ),
                translated(interaction, "staff-userinfo-commands", count=command_count),
                translated(
                    interaction, "staff-userinfo-suggestions", count=suggestion_count
                ),
                translated(
                    interaction,
                    "staff-userinfo-favorite-command",
                    command=favorite or translated(interaction, "common-none"),
                ),
            )
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=card, ephemeral=True)

    @app_commands.command(
        name=app_commands.locale_str("serverinfo", key="command-serverinfo-name"),
        description=app_commands.locale_str(
            "Show BotFragg data for a server", key="command-serverinfo-description"
        ),
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
            await error(interaction, "staff-server-id-required")
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        command_count, favorite = await command_stats(guild_id=server.id)
        members = server.member_count
        member_count = (
            members
            if members is not None
            else translated(interaction, "common-unknown")
        )
        card = embed(
            title=translated(interaction, "staff-serverinfo-title"),
            colour=discord.Color.blurple().value,
        )
        card.add_field(
            name=translated(interaction, "staff-server-important-information"),
            value="\n".join(
                (
                    translated(interaction, "staff-server-name", name=server.name),
                    translated(interaction, "staff-server-id", value=str(server.id)),
                    translated(interaction, "staff-server-members", count=member_count),
                    translated(
                        interaction,
                        "staff-server-owner",
                        owner=f"<@{server.owner_id}> ({server.owner_id})",
                    ),
                )
            ),
            inline=False,
        )
        card.add_field(
            name=translated(interaction, "staff-server-other-information"),
            value="\n".join(
                (
                    translated(
                        interaction,
                        "staff-server-created",
                        timestamp=timestamp(server.created_at),
                    ),
                    translated(
                        interaction, "staff-server-commands", count=command_count
                    ),
                    translated(
                        interaction,
                        "staff-server-most-used-command",
                        command=favorite or translated(interaction, "common-none"),
                    ),
                    translated(
                        interaction,
                        "staff-server-channels-roles",
                        channels=len(server.channels),
                        roles=len(server.roles),
                    ),
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
