"""General BotFragg commands for status, links, suggestions, and shard health."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..bot import BotFraggBot
from ..database import (
    get_shard_status_message_id,
    ping_database,
    save_shard_status_message,
)
from ..models import Suggestion
from ..services.accounts import (
    count_registered_users,
    create_suggestion,
    delete_suggestion,
    follow_suggestion,
    record_suggestion_delivery,
    review_suggestion,
    unfollow_suggestion,
)
from .valorant._ui import embed, error, view


class ExtraCog(commands.Cog):
    """Provide public utility commands and owner-managed suggestion workflows."""

    suggestions = app_commands.Group(
        name="suggestion", description="Track or review feature suggestions"
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Store the bot and record when this cog started for the info command."""
        self.bot = bot
        self.started_at = datetime.now(UTC)

    async def cog_load(self) -> None:
        """Start shard-status updates when their destination is configured."""
        if self.bot.config.shard_status_channel_id:
            self.shard_status.start()

    async def cog_unload(self) -> None:
        """Cancel and await the shard-status task during extension shutdown."""
        task = self.shard_status.get_task()
        self.shard_status.cancel()
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)

    @app_commands.command(name="ping", description="Show BotFragg's current latency")
    @app_commands.guild_only()
    async def ping(self, interaction: discord.Interaction) -> None:
        """Report Discord gateway latency and a live database probe duration."""
        await interaction.response.defer(thinking=True)
        started = monotonic()
        await ping_database()
        database_ms = (monotonic() - started) * 1000
        shard = (
            self.bot.get_shard(interaction.guild.shard_id)
            if interaction.guild
            else None
        )
        websocket_ms = (shard.latency if shard else self.bot.latency) * 1000
        card = embed(title="🏓 Pong")
        card.add_field(name="Websocket latency", value=f"{websocket_ms:.0f}ms")
        card.add_field(name="Database latency", value=f"{database_ms:.0f}ms")
        await interaction.followup.send(embed=card)

    @app_commands.command(name="botinfo", description="Show information about BotFragg")
    @app_commands.guild_only()
    async def botinfo(self, interaction: discord.Interaction) -> None:
        """Show runtime, deployment, library, and registered-user information."""
        await interaction.response.defer(thinking=True)
        user = self.bot.user
        if not user:
            await error(
                interaction, "BotFragg is still starting up. Try again shortly."
            )
            return
        registered_users = await count_registered_users()
        members = sum(guild.member_count or 0 for guild in self.bot.guilds)
        card = embed(
            "BotFragg is a VALORANT companion for personal shops, balances, battlepass progress, and alerts.",
            title=f"About {user.name}",
        )
        card.add_field(name="Commands", value=str(len(self.bot.tree.get_commands())))
        card.add_field(name="Registered users", value=f"{registered_users:,}")
        card.add_field(name="Servers", value=f"{len(self.bot.guilds):,}")
        card.add_field(name="Members", value=f"{members:,}")
        card.add_field(name="Library", value=f"discord.py {discord.__version__}")
        card.add_field(
            name="Started", value=f"<t:{int(self.started_at.timestamp())}:R>"
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=card)

    @app_commands.command(name="links", description="Show BotFragg's public links")
    async def links(self, interaction: discord.Interaction) -> None:
        """Show an invite link and any configured support, vote, and website links."""
        await interaction.response.defer(thinking=True)
        user = self.bot.user
        if not user:
            await error(
                interaction, "BotFragg is still starting up. Try again shortly."
            )
            return
        invite_url = discord.utils.oauth_url(
            user.id,
            permissions=discord.Permissions.none(),
            scopes=("bot", "applications.commands"),
        )
        buttons = [
            discord.ui.Button(
                label="Invite BotFragg",
                url=invite_url,
                style=discord.ButtonStyle.link,
            )
        ]
        for label, url in (
            ("Support server", self.bot.config.support_url),
            ("Vote", self.bot.config.vote_url),
            ("Website", self.bot.config.website_url),
        ):
            if url:
                buttons.append(discord.ui.Button(label=label, url=url))
        card = embed("Use the buttons below to find BotFragg online.", title="🔗 Links")
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=card, view=view(*buttons))

    @app_commands.command(name="suggest", description="Suggest a feature for BotFragg")
    @app_commands.guild_only()
    async def suggest(
        self,
        interaction: discord.Interaction,
        suggestion: app_commands.Range[str, 1, 1000],
    ) -> None:
        """Persist a feature suggestion and publish it to the configured log channel."""
        await interaction.response.defer(thinking=True)
        channel_id = self.bot.config.suggestion_log_channel_id
        if not channel_id:
            await error(interaction, "Suggestions are not configured yet.")
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                await error(interaction, "The suggestion channel is unavailable.")
                return
        if not isinstance(channel, discord.abc.Messageable):
            await error(interaction, "The suggestion channel is not messageable.")
            return
        record = await create_suggestion(interaction.user.id, suggestion, channel_id)
        card = embed(f"> {suggestion}", title=f"Suggestion #{record.id}")
        card.set_author(
            name=str(interaction.user), icon_url=interaction.user.display_avatar.url
        )
        card.set_footer(
            text=interaction.guild.name if interaction.guild else "Direct message"
        )
        try:
            message = await channel.send(embed=card)
        except discord.HTTPException:
            await delete_suggestion(record.id)
            await error(
                interaction, "I couldn't deliver your suggestion. Try again later."
            )
            return
        await record_suggestion_delivery(record, message.id)
        await interaction.followup.send(
            embed=embed(
                f"Suggestion **#{record.id}** was submitted. You will receive a DM when it is reviewed."
            )
        )

    @suggestions.command(name="track", description="Follow a feature suggestion")
    @app_commands.guild_only()
    async def track(self, interaction: discord.Interaction, id: int) -> None:
        """Follow an existing suggestion so the caller receives its review result."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        created = await follow_suggestion(id, interaction.user.id)
        if created is None:
            await error(interaction, f"Suggestion **#{id}** does not exist.")
            return
        message = (
            f"You are now following suggestion **#{id}**."
            if created
            else f"You are already following suggestion **#{id}**."
        )
        await interaction.followup.send(embed=embed(message), ephemeral=True)

    @suggestions.command(
        name="untrack", description="Stop following a feature suggestion"
    )
    @app_commands.guild_only()
    async def untrack(self, interaction: discord.Interaction, id: int) -> None:
        """Remove the caller's follow from another user's suggestion."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await unfollow_suggestion(id, interaction.user.id)
        if result == "missing":
            await error(interaction, f"Suggestion **#{id}** does not exist.")
            return
        if result == "own":
            await error(interaction, "You cannot stop following your own suggestion.")
            return
        await interaction.followup.send(
            embed=embed(
                f"You stopped following suggestion **#{id}**."
                if result == "removed"
                else f"You were not following suggestion **#{id}**."
            ),
            ephemeral=True,
        )

    @suggestions.command(name="approve", description="Approve a feature suggestion")
    @app_commands.guild_only()
    async def approve(
        self, interaction: discord.Interaction, id: int, reason: str
    ) -> None:
        """Submit an owner-only approval review for the selected suggestion."""
        await self._review_suggestion(interaction, id, reason, "approved")

    @suggestions.command(name="deny", description="Deny a feature suggestion")
    @app_commands.guild_only()
    async def deny(
        self, interaction: discord.Interaction, id: int, reason: str
    ) -> None:
        """Submit an owner-only denial review for the selected suggestion."""
        await self._review_suggestion(interaction, id, reason, "denied")

    async def _review_suggestion(
        self,
        interaction: discord.Interaction,
        id: int,
        reason: str,
        status: Literal["approved", "denied"],
    ) -> None:
        """Authorize a review, update its record, and notify its followers."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            await error(interaction, "Only BotFragg's owner can review suggestions.")
            return
        result = await review_suggestion(id, status, reason)
        if result is None:
            await error(
                interaction,
                f"Suggestion **#{id}** is unavailable or already reviewed.",
            )
            return
        suggestion, recipient_ids = result
        await self._update_suggestion_log(suggestion)
        for user_id in recipient_ids:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                await user.send(
                    embed=embed(
                        f"Suggestion **#{id}** was **{status}**.\n\n**Reason:** {reason}\n\n> {suggestion.content}",
                        title="Suggestion update",
                    )
                )
            except discord.HTTPException:
                continue
        await interaction.followup.send(
            embed=embed(f"Suggestion **#{id}** was {status}."), ephemeral=True
        )

    async def _update_suggestion_log(self, suggestion: Suggestion) -> None:
        """Edit the original suggestion post with the final status and review reason."""
        if not suggestion.log_channel_id or not suggestion.log_message_id:
            return
        try:
            channel = self.bot.get_channel(
                suggestion.log_channel_id
            ) or await self.bot.fetch_channel(suggestion.log_channel_id)
            if isinstance(channel, discord.abc.Messageable):
                message = await channel.fetch_message(suggestion.log_message_id)
                await message.edit(
                    embed=embed(
                        f"> {suggestion.content}\n\n**{suggestion.status.title()} reason:** {suggestion.reason}",
                        title=f"Suggestion #{suggestion.id} — {suggestion.status.title()}",
                    )
                )
        except discord.HTTPException:
            return

    @tasks.loop(seconds=30)
    async def shard_status(self) -> None:
        """Update or recreate the persistent embed containing per-shard health."""
        channel_id = self.bot.config.shard_status_channel_id
        if not channel_id:
            return
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                channel_id
            )
            if not isinstance(channel, discord.abc.Messageable):
                return
            card = embed(title="Shard information")
            for shard_id in sorted(self.bot.shards)[:25]:
                shard = self.bot.get_shard(shard_id)
                latency = "N/A" if not shard else f"{shard.latency * 1000:.0f}ms"
                guilds = sum(guild.shard_id == shard_id for guild in self.bot.guilds)
                card.add_field(
                    name=f"Shard {shard_id}",
                    value=f"**Latency:** {latency}\n**Servers:** {guilds}",
                )
            card.timestamp = datetime.now(UTC)
            saved_message_id = await get_shard_status_message_id(channel_id)
            if saved_message_id:
                try:
                    message = await channel.fetch_message(saved_message_id)
                    await message.edit(embed=card)
                    return
                except discord.NotFound:
                    pass
            message = await channel.send(embed=card)
            await save_shard_status_message(channel_id, message.id)
        except discord.HTTPException:
            return

    @shard_status.before_loop
    async def before_shard_status(self) -> None:
        """Wait for Discord readiness before the first shard-status update."""
        await self.bot.wait_until_ready()


async def setup(bot: BotFraggBot) -> None:
    """Register the general utility and suggestion cog with the bot."""
    await bot.add_cog(ExtraCog(bot))
