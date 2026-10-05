"""General BotFragg commands for status, links, suggestions, and shard health."""

from __future__ import annotations

import asyncio
import platform
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Literal

import discord
import psutil
from discord import app_commands
from discord.ext import commands, tasks

from ..bot import BotFraggBot
from ..config import ROOT
from ..database import (
    get_shard_status_message_id,
    ping_database,
    save_shard_status_message,
)
from ..localization import BotFraggTranslator
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
from ..services.http import HTTPFailure
from ..views import timestamp
from .valorant._ui import embed, error, translated, view

GITHUB_COMMITS_URL = "https://api.github.com/repos/BotFragg/BotFragg/commits?per_page=5"
GITHUB_REPOSITORY_URL = "https://github.com/BotFragg/BotFragg"
GITHUB_COMMIT_URL = f"{GITHUB_REPOSITORY_URL}/commit/{{}}"
GITHUB_CACHE_SECONDS = 1800
COMMIT_SHA = re.compile(r"[0-9a-f]{40,64}", re.IGNORECASE)


class ExtraCog(commands.Cog):
    """Provide public utility commands and owner-managed suggestion workflows."""

    suggestions = app_commands.Group(
        name=app_commands.locale_str("suggestion", key="group-suggestion-name"),
        description=app_commands.locale_str(
            "Track or review feature suggestions",
            key="group-suggestion-description",
        ),
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Store the bot and record when this cog started for the info command."""
        self.bot = bot
        self.started_at = datetime.now(UTC)
        self._latest_updates: list[tuple[str, str | None, str | None]] | None = None
        self._latest_updates_unavailable = True
        self._latest_updates_expires = 0.0
        self._latest_updates_lock = asyncio.Lock()
        try:
            self.source_line_count = sum(
                len(path.read_text(encoding="utf-8").splitlines())
                for path in (ROOT / "src").rglob("*.py")
            )
        except OSError:
            self.source_line_count = None

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

    @app_commands.command(
        name=app_commands.locale_str("ping", key="command-ping-name"),
        description=app_commands.locale_str(
            "Show BotFragg's current latency", key="command-ping-description"
        ),
    )
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
        card = embed(title=translated(interaction, "ping-title"))
        card.add_field(
            name=translated(interaction, "ping-websocket-latency"),
            value=f"{websocket_ms:.0f}ms",
        )
        card.add_field(
            name=translated(interaction, "ping-database-latency"),
            value=f"{database_ms:.0f}ms",
        )
        await interaction.followup.send(embed=card)

    @app_commands.command(
        name=app_commands.locale_str("botinfo", key="command-botinfo-name"),
        description=app_commands.locale_str(
            "Show information about BotFragg", key="command-botinfo-description"
        ),
    )
    @app_commands.guild_only()
    async def botinfo(self, interaction: discord.Interaction) -> None:
        """Show recent public updates and BotFragg runtime information."""
        await interaction.response.defer(thinking=True)
        user = self.bot.user
        if not user:
            await error(interaction, "error-bot-starting")
            return
        registered_users = await count_registered_users()
        members = sum(guild.member_count or 0 for guild in self.bot.guilds)
        channels = sum(len(guild.channels) for guild in self.bot.guilds)
        try:
            process = psutil.Process()
            cpu_percent = await asyncio.to_thread(process.cpu_percent, 0.1)
            memory_mb = process.memory_info().rss / (1024 * 1024)
            system_started = psutil.boot_time()
        except psutil.Error:
            cpu_percent = memory_mb = system_started = None
        source_lines = (
            f"{self.source_line_count:,}"
            if self.source_line_count is not None
            else translated(interaction, "common-unavailable")
        )
        system_uptime = (
            timestamp(system_started)
            if system_started is not None
            else translated(interaction, "common-unavailable")
        )
        cpu_usage = (
            f"{cpu_percent:.1f}%"
            if cpu_percent is not None
            else translated(interaction, "common-unavailable")
        )
        memory_usage = (
            f"{memory_mb:.2f} MB"
            if memory_mb is not None
            else translated(interaction, "common-unavailable")
        )
        card = embed(
            translated(interaction, "botinfo-description"),
            title=translated(interaction, "botinfo-title", name=user.name),
        )
        card.add_field(
            name=translated(interaction, "botinfo-recent-commits"),
            value=await self._latest_commit_summary(interaction.locale),
            inline=False,
        )
        card.add_field(
            name=translated(interaction, "botinfo-community"),
            value=(
                translated(interaction, "botinfo-servers", count=len(self.bot.guilds))
                + "\n"
                + translated(
                    interaction, "botinfo-registered-users", count=registered_users
                )
                + "\n"
                + translated(interaction, "botinfo-members", count=members)
                + "\n"
                + translated(interaction, "botinfo-channels", count=channels)
                + "\n"
                + translated(
                    interaction,
                    "botinfo-commands",
                    count=len(self.bot.tree.get_commands()),
                )
            ),
            inline=True,
        )
        card.add_field(
            name=translated(interaction, "botinfo-software"),
            value=(
                translated(interaction, "botinfo-source-lines", count=source_lines)
                + "\n"
                + translated(
                    interaction, "botinfo-python", version=platform.python_version()
                )
                + "\n"
                + translated(
                    interaction, "botinfo-discord-py", version=discord.__version__
                )
            ),
            inline=True,
        )
        card.add_field(
            name=translated(interaction, "botinfo-process"),
            value=(
                translated(interaction, "botinfo-os", name=platform.system())
                + "\n"
                + translated(
                    interaction,
                    "botinfo-bot-uptime",
                    timestamp=timestamp(self.started_at),
                )
                + "\n"
                + translated(
                    interaction, "botinfo-system-uptime", timestamp=system_uptime
                )
                + "\n"
                + translated(interaction, "botinfo-process-cpu", value=cpu_usage)
                + "\n"
                + translated(interaction, "botinfo-memory", value=memory_usage)
            ),
            inline=False,
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(
            embed=card, allowed_mentions=discord.AllowedMentions.none()
        )

    async def _latest_commit_summary(self, locale: discord.Locale) -> str:
        """Fetch and cache five public commits, formatting them per request locale."""
        if monotonic() >= self._latest_updates_expires:
            async with self._latest_updates_lock:
                if monotonic() >= self._latest_updates_expires:
                    self._latest_updates = None
                    self._latest_updates_unavailable = True
                    try:
                        response = await self.bot.riot_http.request(
                            "GET",
                            GITHUB_COMMITS_URL,
                            headers={
                                "Accept": "application/vnd.github+json",
                                "User-Agent": "BotFragg",
                                "X-GitHub-Api-Version": "2022-11-28",
                            },
                        )
                    except HTTPFailure:
                        response = None
                    if (
                        response
                        and response.status == 200
                        and isinstance(response.data, list)
                    ):
                        updates = []
                        for commit in response.data[:5]:
                            if not isinstance(commit, dict):
                                continue
                            sha = commit.get("sha")
                            details = commit.get("commit")
                            if (
                                not isinstance(sha, str)
                                or not COMMIT_SHA.fullmatch(sha)
                                or not isinstance(details, dict)
                            ):
                                continue
                            message = details.get("message")
                            subject = (
                                discord.utils.escape_markdown(
                                    message.splitlines()[0].strip()
                                )
                                if isinstance(message, str) and message.strip()
                                else None
                            )
                            if subject and len(subject) > 100:
                                subject = subject[:97] + "..."
                            author = details.get("author") or details.get("committer")
                            commit_date = (
                                author.get("date") if isinstance(author, dict) else None
                            )
                            updates.append((sha, subject, commit_date))
                        if updates or not response.data:
                            self._latest_updates = updates
                            self._latest_updates_unavailable = False
                    self._latest_updates_expires = monotonic() + GITHUB_CACHE_SECONDS

        if self._latest_updates_unavailable or self._latest_updates is None:
            return self.bot.translator.text(locale, "botinfo-commits-unavailable")
        if not self._latest_updates:
            return self.bot.translator.text(locale, "botinfo-no-commits")

        lines = []
        for sha, subject, commit_date in self._latest_updates:
            age = ""
            if isinstance(commit_date, str):
                try:
                    committed = datetime.fromisoformat(
                        commit_date.replace("Z", "+00:00")
                    )
                    age = " · " + self.bot.translator.text(
                        locale, "botinfo-commit-date", timestamp=timestamp(committed)
                    )
                except ValueError:
                    pass
            lines.append(
                f"[`{sha[:7]}`]({GITHUB_COMMIT_URL.format(sha)}) "
                f"{subject or self.bot.translator.text(locale, 'botinfo-commit')}{age}"
            )
        return "\n".join(lines)

    def _public_links(
        self, user: discord.ClientUser, locale: discord.Locale
    ) -> discord.ui.View:
        """Build link buttons for the configured public URLs."""
        invite_url = discord.utils.oauth_url(
            user.id,
            permissions=discord.Permissions.none(),
            scopes=("bot", "applications.commands"),
        )
        links = [("link-invite", invite_url)]
        links.extend(
            (label, url)
            for label, url in (
                ("link-support", self.bot.config.support_url),
                ("link-vote", self.bot.config.vote_url),
                ("link-website", self.bot.config.website_url),
                ("link-github", GITHUB_REPOSITORY_URL),
            )
            if url
        )
        return view(
            *(
                discord.ui.Button(
                    label=self.bot.translator.text(locale, key),
                    url=url,
                )
                for key, url in links
            )
        )

    @staticmethod
    def _help_category(
        command: app_commands.Command,
        translator: BotFraggTranslator,
        locale: discord.Locale,
    ) -> str:
        """Use each command's cog module to place it in a help category."""
        module = command.module or ""
        component = module.partition("src.cogs.")[2].split(".", 1)[0]
        category = {
            "extra": "help-category-misc",
            "valorant": "help-category-valorant",
        }.get(component, component.replace("_", " ").title() or "Other")
        category_name = (
            translator.text(locale, category)
            if category.startswith("help-category-")
            else category
        )
        return translator.text(locale, "help-category-commands", category=category_name)

    @staticmethod
    def _command_mentions(commands: list[discord.AppCommand]) -> dict[str, str]:
        """Return Discord-formatted mentions for all synced commands and subcommands."""
        mentions: dict[str, str] = {}
        pending: list[app_commands.AppCommandGroup] = []
        for command in commands:
            mentions[command.name] = command.mention
            pending.extend(
                option
                for option in command.options
                if isinstance(option, app_commands.AppCommandGroup)
            )
        while pending:
            command = pending.pop()
            mentions[command.qualified_name] = command.mention
            pending.extend(
                option
                for option in command.options
                if isinstance(option, app_commands.AppCommandGroup)
            )
        return mentions

    @app_commands.command(
        name=app_commands.locale_str("help", key="command-help-name"),
        description=app_commands.locale_str(
            "Show BotFragg's slash commands", key="command-help-description"
        ),
    )
    async def help(self, interaction: discord.Interaction) -> None:
        """List registered slash commands by category in the embed description."""
        await interaction.response.defer(thinking=True)
        user = self.bot.user
        if not user:
            await error(interaction, "error-bot-starting")
            return

        try:
            mentions = self._command_mentions(await self.bot.tree.fetch_commands())
        except discord.HTTPException:
            mentions = {}

        categories: dict[str, list[str]] = {}
        for command in self.bot.tree.walk_commands():
            if not isinstance(command, app_commands.Command):
                continue
            if command.extras.get("owner_only"):
                continue
            mention = mentions.get(command.qualified_name)
            command_name = mention or f"`/{command.qualified_name}`"
            description_key = (
                "command-" + command.qualified_name.replace(" ", "-") + "-description"
            )
            description = discord.utils.escape_markdown(
                self.bot.translator.text(interaction.locale, description_key)
            )
            category = self._help_category(
                command, self.bot.translator, interaction.locale
            )
            categories.setdefault(category, []).append(
                self.bot.translator.text(
                    interaction.locale,
                    "help-command-entry",
                    command=command_name,
                    description=description,
                )
            )

        description = [translated(interaction, "help-intro")]
        for category, entries in categories.items():
            description.extend(("", f"**{category}**", *entries))

        controls = self._public_links(user, interaction.locale)
        card = embed(
            "\n".join(description),
            title=translated(interaction, "help-title"),
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(
            embed=card,
            view=controls,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name=app_commands.locale_str("links", key="command-links-name"),
        description=app_commands.locale_str(
            "Show BotFragg's public links", key="command-links-description"
        ),
    )
    async def links(self, interaction: discord.Interaction) -> None:
        """Show an invite link and any configured support, vote, and website links."""
        await interaction.response.defer(thinking=True)
        user = self.bot.user
        if not user:
            await error(interaction, "error-bot-starting")
            return
        controls = self._public_links(user, interaction.locale)
        card = embed(
            translated(interaction, "links-description"),
            title=translated(interaction, "links-title"),
        )
        card.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=card, view=controls)

    @app_commands.command(
        name=app_commands.locale_str("suggest", key="command-suggest-name"),
        description=app_commands.locale_str(
            "Suggest a feature for BotFragg", key="command-suggest-description"
        ),
    )
    @app_commands.rename(
        suggestion=app_commands.locale_str(
            "suggestion", key="option-suggest-suggestion-name"
        )
    )
    @app_commands.describe(
        suggestion=app_commands.locale_str(
            "Describe the feature you want to suggest",
            key="option-suggest-suggestion-description",
        )
    )
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
            await error(interaction, "suggestions-not-configured")
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                await error(interaction, "suggestion-channel-unavailable")
                return
        if not isinstance(channel, discord.abc.Messageable):
            await error(interaction, "suggestion-channel-not-messageable")
            return
        record = await create_suggestion(interaction.user.id, suggestion, channel_id)
        log_locale = interaction.guild_locale or interaction.locale
        card = embed(
            f"> {suggestion}",
            title=self.bot.translator.text(
                log_locale, "suggestion-title", number=record.id
            ),
        )
        card.set_author(
            name=str(interaction.user), icon_url=interaction.user.display_avatar.url
        )
        card.set_footer(
            text=interaction.guild.name
            if interaction.guild
            else translated(interaction, "common-direct-message")
        )
        try:
            message = await channel.send(embed=card)
        except discord.HTTPException:
            await delete_suggestion(record.id)
            await error(interaction, "suggestion-delivery-failed")
            return
        await record_suggestion_delivery(record, message.id)
        await interaction.followup.send(
            embed=embed(
                translated(
                    interaction,
                    "suggestion-submitted",
                    number=record.id,
                )
            )
        )

    @suggestions.command(
        name=app_commands.locale_str("track", key="command-suggestion-track-name"),
        description=app_commands.locale_str(
            "Follow a feature suggestion",
            key="command-suggestion-track-description",
        ),
    )
    @app_commands.rename(
        id=app_commands.locale_str("id", key="option-suggestion-track-id-name")
    )
    @app_commands.describe(
        id=app_commands.locale_str(
            "ID of the suggestion to follow",
            key="option-suggestion-track-id-description",
        )
    )
    @app_commands.guild_only()
    async def track(self, interaction: discord.Interaction, id: int) -> None:
        """Follow an existing suggestion so the caller receives its review result."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        created = await follow_suggestion(id, interaction.user.id)
        if created is None:
            await error(interaction, "suggestion-not-found", number=id)
            return
        message = (
            self.bot.translator.text(
                interaction.locale, "suggestion-following", number=id
            )
            if created
            else self.bot.translator.text(
                interaction.locale, "suggestion-already-following", number=id
            )
        )
        await interaction.followup.send(embed=embed(message), ephemeral=True)

    @suggestions.command(
        name=app_commands.locale_str("untrack", key="command-suggestion-untrack-name"),
        description=app_commands.locale_str(
            "Stop following a feature suggestion",
            key="command-suggestion-untrack-description",
        ),
    )
    @app_commands.rename(
        id=app_commands.locale_str("id", key="option-suggestion-untrack-id-name")
    )
    @app_commands.describe(
        id=app_commands.locale_str(
            "ID of the suggestion to stop following",
            key="option-suggestion-untrack-id-description",
        )
    )
    @app_commands.guild_only()
    async def untrack(self, interaction: discord.Interaction, id: int) -> None:
        """Remove the caller's follow from another user's suggestion."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await unfollow_suggestion(id, interaction.user.id)
        if result == "missing":
            await error(interaction, "suggestion-not-found", number=id)
            return
        if result == "own":
            await error(interaction, "suggestion-cannot-unfollow-own")
            return
        await interaction.followup.send(
            embed=embed(
                self.bot.translator.text(
                    interaction.locale, "suggestion-unfollowed", number=id
                )
                if result == "removed"
                else self.bot.translator.text(
                    interaction.locale, "suggestion-not-following", number=id
                )
            ),
            ephemeral=True,
        )

    @suggestions.command(
        name="approve",
        description="Approve a feature suggestion",
        extras={"owner_only": True},
    )
    @app_commands.guild_only()
    async def approve(
        self, interaction: discord.Interaction, id: int, reason: str
    ) -> None:
        """Submit an owner-only approval review for the selected suggestion."""
        await self._review_suggestion(interaction, id, reason, "approved")

    @suggestions.command(
        name="deny",
        description="Deny a feature suggestion",
        extras={"owner_only": True},
    )
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
            await error(interaction, "suggestion-owner-only")
            return
        result = await review_suggestion(id, status, reason)
        if result is None:
            await interaction.followup.send(
                embed=embed(
                    f"Suggestion **#{id}** does not exist or has already been reviewed."
                ),
                ephemeral=True,
            )
            return
        suggestion, recipient_ids = result
        await self._update_suggestion_log(suggestion)
        for user_id in recipient_ids:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                user_locale = getattr(user, "locale", discord.Locale.american_english)
                await user.send(
                    embed=embed(
                        self.bot.translator.text(
                            user_locale,
                            "suggestion-review-dm",
                            number=id,
                            status=self.bot.translator.text(
                                user_locale, f"suggestion-status-{status}"
                            ),
                            reason=reason,
                            content=suggestion.content,
                        ),
                        title=self.bot.translator.text(
                            user_locale, "suggestion-update-title"
                        ),
                    )
                )
            except discord.HTTPException:
                continue
        await interaction.followup.send(
            embed=embed(f"Suggestion **#{id}** has been **{status}**."),
            ephemeral=True,
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
                status = suggestion.status.title()
                await message.edit(
                    embed=embed(
                        f"> {suggestion.content}\n\n"
                        f"**{status} reason:** {suggestion.reason}",
                        title=f"Suggestion #{suggestion.id} — {status}",
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
