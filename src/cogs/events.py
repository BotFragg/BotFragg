"""Discord event listeners for analytics, guild notifications, and shard logs."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..services.accounts import record_command_invocation
from ..views import timestamp
from .valorant._ui import embed

log = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    """Record successful commands and report configured Discord lifecycle events."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind event handlers to the running bot instance."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command | app_commands.ContextMenu,
    ) -> None:
        """Log completed app commands and persist their user, guild, and channel IDs."""
        log.info(
            "Application command completed",
            extra={
                "command": command.qualified_name,
                "context": "guild" if interaction.guild_id else "dm",
            },
        )
        try:
            await record_command_invocation(
                command=command.qualified_name,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
            )
        except Exception:
            log.exception("Could not record command analytics")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Send a summary to the channel configured for guild joins."""
        await self._log_guild_event(
            guild, self.bot.config.guild_join_log_channel_id, "I've joined a guild!"
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Send a summary to the channel configured for guild departures."""
        await self._log_guild_event(
            guild, self.bot.config.guild_leave_log_channel_id, "I've left a guild!"
        )

    async def _log_guild_event(
        self, guild: discord.Guild, channel_id: int | None, title: str
    ) -> None:
        """Resolve a configured messageable channel and send a guild summary."""
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning("Could not resolve guild event log channel")
                return
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("Guild event log channel is not messageable")
            return
        owner = (
            f"<@{guild.owner_id}> ({guild.owner_id})" if guild.owner_id else "Unknown"
        )
        card = embed(
            "\n".join(
                (
                    f"**Guild:** {guild.name} ({guild.id})",
                    f"**Owner:** {owner}",
                    f"**Created:** {timestamp(guild.created_at)}",
                    f"**Members:** {guild.member_count or 0}",
                    f"**Channels:** {len(guild.text_channels)} text / {len(guild.voice_channels)} voice",
                )
            ),
            title=title,
            colour=0x36393F,
        )
        if guild.icon:
            card.set_thumbnail(url=guild.icon.url)
        card.set_footer(text=f"I'm in {len(self.bot.guilds)} guilds now")
        try:
            await channel.send(embed=card)
        except discord.HTTPException:
            log.warning("Could not deliver guild event log")

    @commands.Cog.listener()
    async def on_shard_ready(self, shard_id: int) -> None:
        """Report that a Discord shard connected and became ready."""
        await self._log_shard_event(shard_id, "connected")

    @commands.Cog.listener()
    async def on_shard_disconnect(self, shard_id: int) -> None:
        """Report that a Discord shard disconnected."""
        await self._log_shard_event(shard_id, "disconnected")

    @commands.Cog.listener()
    async def on_shard_resumed(self, shard_id: int) -> None:
        """Report that a disconnected Discord shard resumed its session."""
        await self._log_shard_event(shard_id, "resumed")

    async def _log_shard_event(self, shard_id: int, state: str) -> None:
        """Post a shard state update to the optional logging webhook."""
        url = self.bot.config.shard_log_webhook_url
        session = self.bot.riot_http.session
        if not url or not session:
            return
        hook = discord.Webhook.from_url(url, session=session)
        try:
            await hook.send(
                content=f"Shard {shard_id} {state}. Total shards: {self.bot.shard_count}.",
                username="BotFragg Shard Manager",
            )
        except discord.HTTPException:
            log.warning("Could not deliver shard %s event", shard_id)


async def setup(bot: BotFraggBot) -> None:
    """Register the Discord event-listener cog with the bot."""
    await bot.add_cog(EventsCog(bot))
