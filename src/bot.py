"""Discord client construction, command handling, service wiring, and shutdown."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from .config import Settings
from .database import close_database, connect_database
from .monitoring import flush_monitoring, transaction
from .services.auth import AuthService
from .services.catalog import CatalogService
from .services.crypto import AuthVault
from .services.emojis import ApplicationEmojiService
from .services.gameplay import GameplayService
from .services.http import HTTPClient
from .services.shop import ShopService
from .views import OwnedActionButton, OwnedSelect

log = logging.getLogger(__name__)
ComponentHandler = Callable[[discord.Interaction, str], Awaitable[None]]


def _command_error_embed() -> discord.Embed:
    """Build the generic, user-safe response shown after an unhandled command error."""
    return discord.Embed(
        description="Something went wrong while running that command. Please try again shortly.",
        colour=0xFD4553,
    )


class BotFraggCommandTree(app_commands.CommandTree):
    """Application-command tree with shared context rules and error reporting."""

    def __init__(self, client: discord.Client) -> None:
        """Allow commands in servers and private contexts for guild and user installs."""
        super().__init__(
            client,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )

    async def _call(self, interaction: discord.Interaction) -> None:
        """Record command executions while leaving autocomplete requests untraced."""
        if interaction.type is discord.InteractionType.autocomplete:
            await super()._call(interaction)
            return
        data = interaction.data or {}
        command_name = self._command_name(data)
        with transaction(f"discord.command.{command_name}", "discord.command"):
            await super()._call(interaction)

    @staticmethod
    def _command_name(data: dict[str, object]) -> str:
        """Return the dotted parent and subcommand path from Discord's payload."""
        parts = [str(data.get("name") or "unknown")]
        options = data.get("options")
        while isinstance(options, list):
            child = next(
                (
                    option
                    for option in options
                    if isinstance(option, dict) and option.get("type") in {1, 2}
                ),
                None,
            )
            if child is None:
                break
            parts.append(str(child.get("name") or "unknown"))
            options = child.get("options")
        return ".".join(parts)

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError, /
    ) -> None:
        """Log unhandled app-command errors and send a private generic response."""
        command = interaction.command
        if command is not None and command._has_any_error_handlers():
            return
        log.error(
            "Application command failed",
            exc_info=error,
            extra={
                "command": command.qualified_name
                if command is not None
                else self._command_name(interaction.data or {}),
            },
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=_command_error_embed(), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=_command_error_embed(), ephemeral=True
                )
        except discord.HTTPException:
            log.warning("Could not deliver application-command error response")


class BotFraggBot(commands.AutoShardedBot):
    """Own Discord lifecycle and the shared Riot, database, and presentation services."""

    def __init__(self, config: Settings) -> None:
        """Configure the bot's prefix, minimal intents, and application services."""
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("b!"),
            intents=intents,
            shard_count=config.shard_count,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False, replied_user=False
            ),
            tree_cls=BotFraggCommandTree,
        )
        self.config = config
        self.component_handlers: dict[str, ComponentHandler] = {}
        self.riot_http = HTTPClient(config)
        self.emoji_service = ApplicationEmojiService(self)
        self.vault = AuthVault(config.token_encryption_key)
        self.auth = AuthService(config, self.riot_http, self.vault)
        self.catalog = CatalogService(self.riot_http)
        self.shop = ShopService(config, self.riot_http, self.auth, self.catalog)
        self.gameplay = GameplayService(self.riot_http, self.auth, self.catalog)

    async def on_command_error(
        self,
        context: commands.Context[BotFraggBot],
        exception: commands.CommandError,
        /,
    ) -> None:
        """Log failed prefix commands and reply with a generic error message."""
        if isinstance(exception, commands.CommandNotFound):
            return
        command = context.command
        command_name = command.qualified_name if command else "unknown"
        log.error(
            "Prefix command failed",
            exc_info=exception,
            extra={"command": command_name},
        )
        try:
            await context.send(embed=_command_error_embed())
        except discord.HTTPException:
            log.warning(
                "Could not deliver prefix-command error response",
                extra={"command": command_name},
            )

    def register_component(self, action: str, handler: ComponentHandler) -> None:
        """Register a persistent component action, rejecting duplicate action names."""
        if action in self.component_handlers:
            raise RuntimeError(f"Component action already registered: {action}")
        self.component_handlers[action] = handler

    async def setup_hook(self) -> None:
        """Initialize shared resources, load extensions, and optionally sync commands."""
        await connect_database(
            self.config, generate_schemas=self.config.app_env != "production"
        )
        await self.riot_http.start()
        try:
            await self.auth.refresh_version()
        except Exception:
            log.exception("Could not fetch the current Riot client version")
        try:
            await self.catalog.load()
        except Exception:
            log.exception("Could not initialize the VALORANT catalog")
        await self.emoji_service.warm()
        self.add_dynamic_items(OwnedActionButton, OwnedSelect)
        await self.load_extension("jishaku")
        for extension in (
            "src.cogs.valorant.login",
            "src.cogs.valorant.logout",
            "src.cogs.valorant.accounts",
            "src.cogs.valorant.settings",
            "src.cogs.valorant.shop",
            "src.cogs.valorant.alerts",
            "src.cogs.valorant.battlepass",
            "src.cogs.valorant.penalties",
            "src.cogs.events",
            "src.cogs.extra",
            "src.cogs.staff",
            "src.cogs.tasks",
        ):
            await self.load_extension(extension)
        if self.config.auto_sync_commands:
            await self.tree.sync()

    async def on_ready(self) -> None:
        """Set the online activity and log the connected shard and guild counts."""
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="VALORANT"
            ),
        )
        log.info(
            "BotFragg is ready",
            extra={"shards": self.shard_count, "guilds": len(self.guilds)},
        )

    async def close(self) -> None:
        """Close Discord, Riot HTTP, database, and monitoring resources in order."""
        try:
            await super().close()
        finally:
            try:
                await self.riot_http.close()
            finally:
                try:
                    await close_database()
                finally:
                    flush_monitoring()
