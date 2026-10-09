# BotFragg API reference

This reference covers application modules, classes, module-level functions, and class methods. It is generated from application source docstrings; edit those docstrings and regenerate this page when behavior or signatures change.

## `main.py`

Support the repository's ``python main.py`` startup command.

## `src/__init__.py`

BotFragg bot package.

## `src/bot.py`

Discord client construction, command handling, service wiring, and shutdown.

### `def _command_error_embed(translator: BotFraggTranslator, locale: discord.Locale | str | None = 'en-US') -> discord.Embed`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L29)

Build the generic, user-safe response shown after an unhandled command error.

### `class BotFraggCommandTree(app_commands.CommandTree['BotFraggBot'])`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L39)

Application-command tree with shared context rules and error reporting.

### `def __init__(self, client: BotFraggBot) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L42)

Allow commands in servers and private contexts for guild and user installs.

### `async def _call(self, interaction: discord.Interaction[BotFraggBot]) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L52)

Record command executions while leaving autocomplete requests untraced.

### `def _command_name(data: Mapping[str, object]) -> str`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L63)

Return the dotted parent and subcommand path from Discord's payload.

### `async def on_error(self, interaction: discord.Interaction[BotFraggBot], error: app_commands.AppCommandError, /) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L82)

Log unhandled app-command errors and send a private generic response.

### `class BotFraggBot(commands.AutoShardedBot)`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L120)

Own Discord lifecycle and the shared Riot, database, and presentation services.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L123)

Configure the bot's prefix, minimal intents, and application services.

### `async def on_command_error(self, context: commands.Context, exception: commands.CommandError, /) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L149)

Log failed prefix commands and reply with a generic error message.

### `def register_component(self, action: str, handler: ComponentHandler) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L173)

Register a persistent component action, rejecting duplicate action names.

### `async def setup_hook(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L179)

Initialize shared resources, load extensions, and optionally sync commands.

### `async def on_ready(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L216)

Set the online activity and log the connected shard and guild counts.

### `async def close(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L229)

Close Discord, Riot HTTP, database, and monitoring resources in order.

## `src/cogs/__init__.py`

Discord command cogs.

## `src/cogs/events.py`

Discord event listeners for analytics, guild notifications, and shard logs.

### `class EventsCog(commands.Cog)`

**Scope:** `src/cogs/events.py` · `module`

[Source](../src/cogs/events.py#L19)

Record successful commands and report configured Discord lifecycle events.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L22)

Bind event handlers to the running bot instance.

### `async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L27)

Log completed app commands and persist their user, guild, and channel IDs.

### `async def on_guild_join(self, guild: discord.Guild) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L53)

Send a summary to the channel configured for guild joins.

### `async def on_guild_remove(self, guild: discord.Guild) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L60)

Send a summary to the channel configured for guild departures.

### `async def _log_guild_event(self, guild: discord.Guild, channel_id: int | None, title: str) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L66)

Resolve a configured messageable channel and send a guild summary.

### `async def on_shard_ready(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L107)

Report that a Discord shard connected and became ready.

### `async def on_shard_disconnect(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L112)

Report that a Discord shard disconnected.

### `async def on_shard_resumed(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L117)

Report that a disconnected Discord shard resumed its session.

### `async def _log_shard_event(self, shard_id: int, state: str) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L121)

Post a shard state update to the optional logging webhook.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/events.py` · `module`

[Source](../src/cogs/events.py#L137)

Register the Discord event-listener cog with the bot.

## `src/cogs/extra.py`

General BotFragg commands for status, links, help, and shard health.

### `class ExtraCog(commands.Cog)`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L38)

Provide public utility commands and the persistent shard-status message.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L41)

Store the bot and record when this cog started for the info command.

### `async def cog_load(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L59)

Start shard-status updates when their destination is configured.

### `async def cog_unload(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L64)

Cancel and await the shard-status task during extension shutdown.

### `async def ping(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L78)

Report Discord gateway latency and a live database probe duration.

### `async def botinfo(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L108)

Show recent public updates and BotFragg runtime information.

### `async def _latest_commit_summary(self, locale: discord.Locale) -> str`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L216)

Fetch and cache five public commits, formatting them per request locale.

### `def _public_links(self, user: discord.ClientUser, locale: discord.Locale) -> discord.ui.View`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L294)

Build link buttons for the configured public URLs.

### `def _help_category(command: app_commands.Command, translator: BotFraggTranslator, locale: discord.Locale) -> str`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L325)

Use each command's cog module to place it in a help category.

### `def _command_mentions(commands: list[app_commands.AppCommand]) -> dict[str, str]`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L346)

Return Discord-formatted mentions for all synced commands and subcommands.

### `async def help(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L373)

List registered slash commands by category in the embed description.

### `async def links(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L434)

Show an invite link and any configured support, vote, and website links.

### `async def shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L450)

Measure the shard-status job and preserve its existing retry behavior.

### `async def _update_shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L455)

Update or recreate the persistent embed containing per-shard health.

### `async def before_shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L492)

Wait for Discord readiness before the first shard-status update.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L497)

Register the general utility cog with the bot.

## `src/cogs/staff.py`

Owner-only Discord diagnostics for users, servers, and command analytics.

### `class StaffCog(commands.Cog)`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L16)

Owner-only operational diagnostics.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L19)

Bind the staff diagnostics to the running bot.

### `async def _owner_only(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L23)

Authorize the bot owner and privately reject all other callers.

### `async def userinfo(self, interaction: discord.Interaction, user: discord.User) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L36)

Show the owner's stored account statistics and shared-server details.

### `async def serverinfo(self, interaction: discord.Interaction, server_id: str) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L78)

Show analytics and Discord's cached membership count for a server.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L129)

Register the owner-only diagnostics cog with the bot.

## `src/cogs/suggestions.py`

Discord suggestion submission, following, and owner-only review commands.

### `class SuggestionsCog(commands.Cog)`

**Scope:** `src/cogs/suggestions.py` · `module`

[Source](../src/cogs/suggestions.py#L24)

Own the public suggestion workflow and its review notifications.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L35)

Bind suggestion commands to the running bot.

### `async def suggest(self, interaction: discord.Interaction, suggestion: app_commands.Range[str, 1, 1000]) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L57)

Persist a feature suggestion and publish it to the configured log channel.

### `async def track(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L130)

Follow a pending suggestion or privately show its existing review.

### `async def untrack(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L170)

Remove the caller's follow from another user's suggestion.

### `async def approve(self, interaction: discord.Interaction, id: int, reason: app_commands.Range[str, 1, 1000]) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L199)

Submit an owner-only approval review for the selected suggestion.

### `async def deny(self, interaction: discord.Interaction, id: int, reason: app_commands.Range[str, 1, 1000]) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L214)

Submit an owner-only denial review for the selected suggestion.

### `async def _review_suggestion(self, interaction: discord.Interaction, id: int, reason: str, status: Literal['approved', 'denied']) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L223)

Authorize a review, update its record, and notify its followers.

### `def _review_card(self, suggestion: Suggestion, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L262)

Render the localized review shared by follower DMs and completed tracking.

### `async def _update_suggestion_log(self, suggestion: Suggestion) -> None`

**Scope:** `src/cogs/suggestions.py` · `SuggestionsCog`

[Source](../src/cogs/suggestions.py#L280)

Edit the original suggestion post with the final status and review reason.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/suggestions.py` · `module`

[Source](../src/cogs/suggestions.py#L302)

Register suggestion commands and review handlers.

## `src/cogs/tasks.py`

Background loops for daily alerts, catalog refresh, and Discord log delivery.

### `class DiscordLogHandler(logging.Handler)`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L31)

Buffer privacy-filtered structured log lines for periodic Discord delivery.

### `def __init__(self) -> None`

**Scope:** `src/cogs/tasks.py` · `DiscordLogHandler`

[Source](../src/cogs/tasks.py#L34)

Create a bounded log buffer using BotFragg's privacy-aware formatter.

### `def emit(self, record: logging.LogRecord) -> None`

**Scope:** `src/cogs/tasks.py` · `DiscordLogHandler`

[Source](../src/cogs/tasks.py#L40)

Format a log record into the buffer or delegate failures to logging.

### `class TasksCog(commands.Cog)`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L48)

Own periodic application jobs and stop them cleanly when unloaded.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L51)

Set job intervals from settings and prepare the optional log handler.

### `async def cog_load(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L85)

Start background loops and attach the log handler when configured.

### `async def cog_unload(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L96)

Cancel and await all active loops, then detach the root log handler.

### `async def daily_alerts(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L119)

Run the daily shop and skin-alert job inside a monitoring transaction.

### `async def run_alerts(self) -> dict[str, int]`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L134)

Process eligible users' shops and return counts for the completed run.

### `async def _deliver_daily_alert_result(self, user_id: int, user: User | None, account: Account, shop: ShopData, matches: list[tuple[Alert, Offer]], send_daily_shop: bool) -> int`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L147)

Deliver matching alerts and the optional daily shop; count failed DMs.

### `async def _send_alert(self, user_id: int, alert: Alert, offer: Offer) -> bool`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L164)

DM an owner-scoped skin alert and report whether delivery succeeded.

### `async def _send_daily_shop(self, user: User, account: Account, shop: ShopData) -> bool`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L200)

DM the selected account's daily shop and report delivery success.

### `async def _credentials_expired(self, user_id: int) -> int`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L242)

Notify a user that credentials expired and return the delivery failure count.

### `async def version_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L258)

Refresh the Riot client version used in authenticated API requests.

### `async def catalog_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L267)

Refresh the VALORANT catalog when its upstream version changes.

### `async def log_flush(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L277)

Measure log delivery, preserving the queue after Discord failures.

### `async def _flush_logs(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L282)

Send buffered log lines to Discord and requeue them after HTTP failures.

### `async def health_watch(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L318)

Publish Discord, database, and scheduled-job health for Docker and operators.

### `async def before_jobs(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L369)

Wait for Discord readiness before starting any background job.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L374)

Register the background-task cog with the bot.

## `src/cogs/valorant/__init__.py`

Initial-release VALORANT command cogs.

## `src/cogs/valorant/accounts.py`

Slash commands for selecting, listing, and paging through linked accounts.

### `class AccountsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L32)

Present a user's linked Riot accounts and handle account selection.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L35)

Bind the bot and register the persistent account-page action.

### `async def account_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L40)

Return up to 25 of the caller's accounts matching the typed name.

### `def _accounts_embed(accounts: list[Account], current_account_id: str | None, translator: BotFraggTranslator, locale: discord.Locale, page: int = 0, *, hide_ign: bool = False) -> discord.Embed`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L49)

Render one bounded account page and mark the currently selected entry.

### `def _accounts_view(user_id: int, account_count: int, page: int) -> discord.ui.View | None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L90)

Build owner-scoped previous and next controls when multiple pages exist.

### `async def account(self, interaction: discord.Interaction, account: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L119)

Switch the caller's active account using an autocomplete selection.

### `async def accounts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L177)

Show the caller's accounts privately when their name-hiding preference is on.

### `async def accounts_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L203)

Refresh an account page privately when an old public list now hides names.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L237)

Register the linked-account commands and component handlers.

## `src/cogs/valorant/alerts.py`

Commands for creating, viewing, removing, and testing skin alerts.

### `class AlertsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L22)

Manage owner-scoped alert records and their persistent Discord controls.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L25)

Bind the bot and register persistent alert-management actions.

### `async def skin_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L31)

Return catalog skin matches suitable for Discord's autocomplete limit.

### `async def alert(self, interaction: discord.Interaction, skin: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L64)

Create a skin alert for the caller's active account and show a remove control.

### `async def alerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L111)

Show the caller's paginated alerts and owner-bound management controls.

### `def _created_embed(self, skin: Skin, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L125)

Build the confirmation card for a newly created skin alert.

### `def _skin_display_name(self, skin: Skin | None, locale: discord.Locale) -> str`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L137)

Return a skin name prefixed with its tier emoji, if one exists.

### `def _skin_emoji(self, skin: Skin | None) -> str | None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L147)

Return a button emoji for a skin tier when one is available.

### `async def manager_view(self, user_id: int, page: int, locale: discord.Locale) -> tuple[discord.Embed, discord.ui.View | None]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L153)

Render one alert page with per-alert removal and optional page controls.

### `async def remove_alert(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L217)

Remove the selected owner-scoped alert and refresh or dismiss its controls.

### `async def alert_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L256)

Validate a page payload and update the alert-management message.

### `async def testalerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L276)

Check login and shop availability, then send the caller a test alert DM.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L345)

Register the skin-alert commands and their persistent handlers.

## `src/cogs/valorant/battlepass.py`

Commands and embed builders for VALORANT battlepass and mission progress.

### `class BattlepassCog(commands.Cog)`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L40)

Display the caller's current battlepass level and mission progress.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L43)

Bind the bot's gameplay, account, and emoji services.

### `async def battlepass(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L53)

Fetch and display the active battlepass for the caller's selected account.

### `async def missions(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L96)

Show the selected account's daily and weekly mission progress privately.

### `def _missions_card(missions: list[MissionProgress], filled_bar: str = '█', empty_bar: str = '░', *, translator: BotFraggTranslator, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L123)

Group mission entries by type and expiry and render progress bars.

### `def _battlepass_card(player: str, data: BattlepassProgress, filled_bar: str = '█', empty_bar: str = '░', *, emoji_service: ApplicationEmojiService | None = None, translator: BotFraggTranslator, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L215)

Render the active act, current tier, next reward, and XP progress bar.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L289)

Register the battlepass and mission commands.

## `src/cogs/valorant/login.py`

Private Riot sign-in flow using an authorization link and callback modal.

### `class LoginModal(discord.ui.Modal)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L14)

Collect the redirect URL returned after a user signs in with Riot.

### `def __init__(self, bot: BotFraggBot, locale: discord.Locale) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L17)

Set a five-minute timeout and retain the authentication service owner.

### `async def on_submit(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L31)

Redeem the submitted callback and privately report the login result.

### `class LoginCog(commands.Cog)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L59)

Start Riot sign-in and open the callback URL entry modal.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L62)

Bind the bot and register the persistent login-modal action.

### `async def login(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L74)

Start a nonce-bound login; account creation limits belong to auth.

### `async def login_modal(self, interaction: discord.Interaction, _: str) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L109)

Open the modal where the caller pastes Riot's redirect URL.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L114)

Register the Riot login command and modal handler.

## `src/cogs/valorant/logout.py`

Commands for clearing Riot credentials or deleting all stored user data.

### `class LogoutCog(commands.Cog)`

**Scope:** `src/cogs/valorant/logout.py` · `module`

[Source](../src/cogs/valorant/logout.py#L14)

Let users disconnect Riot credentials or erase their BotFragg records.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L17)

Bind the bot's account, authentication, and storefront services.

### `async def account_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L21)

Return the caller's linked accounts for the logout command.

### `async def logout(self, interaction: discord.Interaction, account: str | None = None) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L46)

Clear Riot credentials for one linked account while preserving its settings.

### `async def deletedata(self, interaction: discord.Interaction, confirm: bool) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L81)

Permanently delete the caller's records and clear cached storefronts.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `module`

[Source](../src/cogs/valorant/logout.py#L109)

Register the account logout and personal data deletion commands.

## `src/cogs/valorant/penalties.py`

Private command for viewing Riot matchmaking penalties.

### `class PenaltiesCog(commands.Cog)`

**Scope:** `src/cogs/valorant/penalties.py` · `module`

[Source](../src/cogs/valorant/penalties.py#L23)

Display matchmaking penalties for the caller's selected VALORANT account.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/penalties.py` · `PenaltiesCog`

[Source](../src/cogs/valorant/penalties.py#L26)

Bind the gameplay service and register pagination handling.

### `async def penalties(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/penalties.py` · `PenaltiesCog`

[Source](../src/cogs/valorant/penalties.py#L38)

Show Riot penalties privately for the caller's selected account.

### `async def penalties_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/penalties.py` · `PenaltiesCog`

[Source](../src/cogs/valorant/penalties.py#L73)

Validate pagination data, reload its owned account, and edit the page.

### `def _penalties_page(owner_id: int, account: Account, player: str, penalties: list[Penalty], page: int, translator: BotFraggTranslator, locale: discord.Locale) -> tuple[discord.Embed, discord.ui.View | None]`

**Scope:** `src/cogs/valorant/penalties.py` · `module`

[Source](../src/cogs/valorant/penalties.py#L121)

Build one five-penalty embed page and owner-bound navigation controls.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/penalties.py` · `module`

[Source](../src/cogs/valorant/penalties.py#L238)

Register the private matchmaking-penalties command.

## `src/cogs/valorant/settings.py`

Private commands for viewing and changing user display and shop preferences.

### `class SettingsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/settings.py` · `module`

[Source](../src/cogs/valorant/settings.py#L24)

Present user preferences and handle their owner-scoped select menu.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L35)

Bind the bot and register the persistent preference-selection action.

### `async def settings_view(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L46)

Show the caller's saved preferences in an ephemeral response.

### `async def settings_set(self, interaction: discord.Interaction, setting: app_commands.Choice[str]) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L94)

Present Yes/No options for the caller's selected preference.

### `async def setting_selected(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L130)

Validate and persist a setting selection, then update its confirmation.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `module`

[Source](../src/cogs/valorant/settings.py#L158)

Register the user preference commands and selection handler.

## `src/cogs/valorant/shop.py`

Commands for skin shops, featured bundles, and balances.

### `class ShopCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L46)

Show shops and bundles for the caller's linked account.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L49)

Bind the bot and register persistent shop-mode and account actions.

### `async def shop(self, interaction: discord.Interaction, user: discord.User | None = None) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L73)

Show a shop after rechecking its original account and current privacy.

### `def shop_view(self, data: ShopData, username: str, owner_id: int, puuid: str, *, accounts: Sequence[Account], vp: str, hide_ign: bool = False, locale: discord.Locale) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L156)

Render daily shop cards and controls without further preparation waits.

### `async def bundles(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L242)

Show the selected account's current featured bundle offers and controls.

### `async def featured_bundles_view(self, data: ShopData, owner_id: int, puuid: str, *, locale: discord.Locale, selected_id: str | None = None, show_shop_button: bool = False) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L262)

Build current featured bundles with shop-style cards and controls.

### `def _bundle_metadata(self, offer: FeaturedBundle, locale: discord.Locale) -> Bundle`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L361)

Resolve static bundle metadata or provide a safe live-offer fallback.

### `def _featured_price(self, offer: FeaturedBundle, vp: str, locale: discord.Locale) -> str`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L375)

Format only Riot-supplied VP totals, retaining exact discount values.

### `async def _featured_item_embed(self, item: FeaturedBundleItem, vp: str, locale: discord.Locale) -> discord.Embed | None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L389)

Render one live bundle item in the shop's card, tier, and price style.

### `async def _featured_bundle_embeds(self, offer: FeaturedBundle, locale: discord.Locale) -> list[discord.Embed]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L449)

Render a bundle summary and up to nine shop-style item cards.

### `async def shop_mode(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L515)

Render the selected daily, Night Market, accessory, or bundle mode.

### `def _selection_values(interaction: discord.Interaction, custom_id: str) -> set[str]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L645)

Read the values actually offered by this message's matching select menu.

### `async def shop_bundle(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L659)

Revalidate a selected featured bundle against the caller's account and view.

### `def _video_options(skin: Skin, translator: BotFraggTranslator, locale: discord.Locale) -> list[discord.SelectOption]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L713)

List playable levels and chromas within Discord's select-menu limit.

### `async def shop_skin(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L746)

Open a private level/chroma menu for a skin offered in this message.

### `async def shop_variant(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L800)

Privately return a selected video only when it belongs to that skin.

### `async def shop_account(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L861)

Validate the selected account and reopen the corresponding shop mode.

### `class NightMarketCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L877)

Display discounted Night Market offers for the selected Riot account.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L880)

Bind the shared shop, account, and emoji services.

### `async def nightmarket(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L891)

Fetch and render Night Market offers or report that none are active.

### `class BalanceCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L935)

Display the selected account's three VALORANT wallet balances.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L938)

Bind the shared shop and user-preference services.

### `async def balance(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L949)

Fetch and display VP, Radianite, and Kingdom Credit balances.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L1004)

Register the shop, Night Market, and wallet-balance cogs.

## `src/config.py`

Environment-backed settings, validation helpers, and repository paths.

### `def _bool(name: str, default: bool) -> bool`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L20)

Parse a named environment variable as a strict boolean or use its default.

### `def _int(name: str, default: int, minimum: int = 0) -> int`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L33)

Parse an integer setting and reject values below its configured minimum.

### `def _sample_rate(name: str, default: float) -> float`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L41)

Parse a telemetry sample rate constrained to the inclusive range 0 to 1.

### `def _optional_int(name: str) -> int | None`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L49)

Return a positive optional integer setting, or ``None`` when it is blank.

### `def _optional_url(name: str) -> str | None`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L63)

Validate and return an optional absolute HTTP(S) URL without userinfo.

### `def _optional_webhook_url(name: str) -> str | None`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L89)

Validate an optional HTTPS Discord webhook URL and reject other hosts.

### `def _time(name: str, default: str) -> time`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L110)

Parse an HH:MM or HH:MM:SS setting as a UTC wall-clock time.

### `class Settings`

**Scope:** `src/config.py` · `module`

[Source](../src/config.py#L122)

Immutable runtime configuration populated from environment variables.

### `def from_env(cls, *, require_secrets: bool = True) -> Settings`

**Scope:** `src/config.py` · `Settings`

[Source](../src/config.py#L164)

Load settings, validate URLs and limits, and optionally require secrets.


**Args**
- **`require_secrets`** — Require the Discord token and Fernet encryption key.


**Returns**
  A validated settings instance for the current process.


**Raises**
- **`ValueError`** — If an environment value is malformed or required data is missing.

## `src/database.py`

Database URL normalization, Tortoise setup, and shard-status persistence.

### `def _database_url(url: str) -> str`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L28)

Resolve relative SQLite paths against the repository root.

### `def _tortoise_config(config: Settings) -> dict[str, object]`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L40)

Build the ORM configuration for the supplied application settings.

### `async def connect_database(config: Settings, *, generate_schemas: bool = False) -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L59)

Initialize Tortoise and optionally create missing development schemas.

### `async def ping_database() -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L66)

Run a minimal query against the default database connection.

### `async def close_database() -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L71)

Close all Tortoise database connections.

### `async def get_shard_status_message_id(channel_id: int) -> int | None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L76)

Return the saved status-message ID for a channel, if one exists.

### `async def save_shard_status_message(channel_id: int, message_id: int) -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L82)

Create or update the status-message reference for a channel.

## `src/health.py`

Background-job evidence and a local, credential-free container health check.

### `class JobHealth`

**Scope:** `src/health.py` · `module`

[Source](../src/health.py#L22)

Track actual completion, failures, and elapsed time for one scheduled job.

### `def failure(self, name: str) -> None`

**Scope:** `src/health.py` · `JobHealth`

[Source](../src/health.py#L32)

Record a failure, including one handled inside a job's retry logic.

### `def track(self, name: str) -> Iterator[None]`

**Scope:** `src/health.py` · `JobHealth`

[Source](../src/health.py#L41)

Measure one attempt; exceptions and cancellation never count as success.

### `def snapshot(self, *, running: bool, failed: bool, now: float) -> dict[str, object]`

**Scope:** `src/health.py` · `JobHealth`

[Source](../src/health.py#L65)

Report stopped, failed, or overdue work without exposing user data.

### `def write_health(snapshot: dict[str, object], path: Path = HEALTH_PATH) -> None`

**Scope:** `src/health.py` · `module`

[Source](../src/health.py#L90)

Replace the status file atomically so probes never read partial JSON.

### `def healthcheck(path: Path = HEALTH_PATH) -> bool`

**Scope:** `src/health.py` · `module`

[Source](../src/health.py#L104)

Require a fresh successful heartbeat; malformed or missing files fail closed.

## `src/localization.py`

Fluent catalogs for Discord command metadata and BotFragg messages.

### `class BotFraggTranslator(app_commands.Translator)`

**Scope:** `src/localization.py` · `module`

[Source](../src/localization.py#L17)

Translate Discord command metadata and runtime messages from Fluent files.

### `def __init__(self, locales_dir: Path = LOCALES_DIR) -> None`

**Scope:** `src/localization.py` · `BotFraggTranslator`

[Source](../src/localization.py#L20)

Load catalog files lazily and keep one fallback bundle per locale.

### `def _catalog(self, locale: str) -> FluentLocalization`

**Scope:** `src/localization.py` · `BotFraggTranslator`

[Source](../src/localization.py#L26)

Create and cache a locale bundle with English as a fallback.

### `def text(self, locale: discord.Locale | str | None, key: str, **arguments: object) -> str`

**Scope:** `src/localization.py` · `BotFraggTranslator`

[Source](../src/localization.py#L37)

Format a message, falling back to the English catalog when needed.

### `async def translate(self, string: app_commands.locale_str, locale: discord.Locale, context: app_commands.TranslationContext) -> str | None`

**Scope:** `src/localization.py` · `BotFraggTranslator`

[Source](../src/localization.py#L67)

Return a translated command string or defer to Discord's English source.

## `src/main.py`

Executable entry point that configures logging and starts BotFragg.

### `def main() -> None`

**Scope:** `src/main.py` · `module`

[Source](../src/main.py#L12)

Load settings, configure observability, and run the Discord client.

## `src/migrations/0001_initial.py`

Create the initial user, account, and alert tables.

### `class Migration(migrations.Migration)`

**Scope:** `src/migrations/0001_initial.py` · `module`

[Source](../src/migrations/0001_initial.py#L8)

Define the initial persisted BotFragg schema and ownership relations.

## `src/migrations/0002_add_command_analytics.py`

Add persistent command invocation analytics.

### `class Migration(migrations.Migration)`

**Scope:** `src/migrations/0002_add_command_analytics.py` · `module`

[Source](../src/migrations/0002_add_command_analytics.py#L7)

Add the nullable Discord scope fields used by command statistics.

## `src/migrations/0003_add_suggestions.py`

Add the suggestion and suggestion-follower tables.

### `class Migration(migrations.Migration)`

**Scope:** `src/migrations/0003_add_suggestions.py` · `module`

[Source](../src/migrations/0003_add_suggestions.py#L8)

Create suggestion records and their unique follower relationship.

## `src/migrations/0004_add_shard_status_message.py`

Add storage for reusing the shard-status message in each channel.

### `class Migration(migrations.Migration)`

**Scope:** `src/migrations/0004_add_shard_status_message.py` · `module`

[Source](../src/migrations/0004_add_shard_status_message.py#L7)

Create the channel-to-status-message mapping table.

## `src/migrations/__init__.py`

Tortoise migration package for the BotFragg database schema.

## `src/models/__init__.py`

Public model exports for application services and Discord cogs.

## `src/models/entities.py`

Tortoise ORM entities and database constraints for BotFragg data.

### `class User(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L10)

Store Discord preferences and the selected linked VALORANT account.

### `class Account(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L24)

Store a user's Riot identity and encrypted authentication payload.

### `def persisted_row(self) -> QuerySet[Account]`

**Scope:** `src/models/entities.py` · `Account`

[Source](../src/models/entities.py#L27)

Scope access to this account's original owner and creation time.

### `class Alert(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L48)

Store a skin alert belonging to one linked Riot account.

### `class Meta`

**Scope:** `src/models/entities.py` · `Alert`

[Source](../src/models/entities.py#L58)

Prevent duplicate alerts for the same account and skin.

### `class CommandInvocation(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L64)

Store a completed command and its optional guild and channel context.

### `class Suggestion(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L75)

Store a user's submitted idea and its review and delivery state.

### `class SuggestionFollower(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L90)

Link a Discord user to a suggestion whose review they want to follow.

### `class Meta`

**Scope:** `src/models/entities.py` · `SuggestionFollower`

[Source](../src/models/entities.py#L99)

Allow each user to follow a suggestion at most once.

### `class ShardStatusMessage(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L105)

Map each configured Discord channel to its persistent status message.

## `src/monitoring.py`

Structured logging and privacy filters for logs and GlitchTip events.

### `class StructuredFormatter(logging.Formatter)`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L64)

Format log records as JSON after filtering sensitive values.

### `def format(self, record: logging.LogRecord) -> str`

**Scope:** `src/monitoring.py` · `StructuredFormatter`

[Source](../src/monitoring.py#L67)

Serialize a scrubbed log record and its safe structured fields.

### `def _scrub(value: Any) -> Any`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L86)

Filter credentials and personal identifiers from nested event data.

### `def _breadcrumb(breadcrumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L115)

Drop network and unrelated log breadcrumbs, then scrub retained data.

### `def _scrub_event(event: Event) -> Event`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L129)

Remove request data and sensitive values from an error event.

### `def _scrub_transaction(event: Event, hint: dict[str, Any]) -> Event`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L136)

Remove request payloads and HTTP span details from a transaction.

### `def _scrub_log(log: Log, hint: dict[str, Any]) -> Log | None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L147)

Keep BotFragg logs and serious Discord errors after removing URL data.

### `def _release() -> str`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L161)

Return the installed BotFragg release label or an unknown fallback.

### `def configure_monitoring(config: Settings) -> None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L169)

Enable privacy-filtered GlitchTip telemetry when a DSN is configured.

### `def transaction(name: str, op: str)`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L199)

Start a GlitchTip transaction with the supplied name and operation.

### `def flush_monitoring() -> None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L204)

End the current monitoring session and flush queued telemetry.

## `src/services/__init__.py`

Domain and external-service adapters.

## `src/services/accounts.py`

Persistence operations for user preferences, Riot accounts, and personal-data deletion.

### `async def get_user(discord_id: int) -> User | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L23)

Return the stored BotFragg user for a Discord ID, if one exists.

### `async def count_registered_users() -> int`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L28)

Count users with a stored BotFragg profile.

### `async def daily_shop_user_ids() -> set[int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L33)

Return Discord IDs whose saved preference enables daily shop DMs.

### `async def account_for_user(discord_id: int, puuid: str) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L39)

Return a Riot account only when it belongs to the requested Discord user.

### `async def update_user_preference(discord_id: int, field: str, enabled: bool) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L44)

Update one allowlisted Boolean preference and refresh the user's timestamp.

### `async def selected_account(discord_id: int, *, user: User | None = None, accounts: Sequence[Account] | None = None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L54)

Return the active account, choosing the oldest account when none is selected.

A supplied user or account sequence avoids redundant queries; a supplied user
must belong to ``discord_id``. When choosing a default, the database update is
conditional so a concurrent selection is not overwritten.

### `async def list_accounts(discord_id: int) -> list[Account]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L124)

Return a user's Riot accounts in creation order.

### `async def resolve_account(discord_id: int, query: str | None, *, accounts: Sequence[Account] | None = None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L129)

Resolve an account by PUUID, case-insensitive name, or one-based position.

### `async def select_account(discord_id: int, account: Account) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L156)

Set a user's active account after verifying that the account is theirs.

### `async def delete_user_data(discord_id: int) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L182)

Delete the user's stored BotFragg records and all linked Riot accounts.

## `src/services/alerts.py`

Persistence and orchestration for alerts.

### `class AlertPage`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L29)

Hold one bounded page of alerts and its normalized pagination metadata.

### `async def create_alert(user_id: int, account: Account, skin_uuid: UUID) -> tuple[Alert, bool]`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L39)

Create an account-scoped skin alert or return the existing duplicate.

### `async def list_alerts_page(user_id: int, page: int, page_size: int) -> AlertPage`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L59)

Fetch an owner-scoped alert page, wrapping page indexes and bounding size.

### `async def remove_alert(user_id: int, alert_id: int) -> Alert | None`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L81)

Delete and return an alert only when it belongs to the requesting user.

### `async def first_alert(user_id: int) -> Alert | None`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L89)

Return a user's first alert with its linked account loaded.

### `async def user_ids_with_alerts() -> set[int]`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L96)

Return distinct Discord IDs that own at least one alert.

### `async def account_ids_with_alerts(account_ids: list[str]) -> set[str]`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L102)

Return only the supplied account IDs that currently have alerts.

### `async def matching_alerts_for_skins(account: Account, skin_uuids: list[str]) -> list[Alert]`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L113)

Fetch alerts matching one account and a bounded set of shop skin IDs.

### `async def _retry_lookup(operation: Callable[[], Awaitable[T]]) -> T`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L135)

Retry transient lookups up to three times without replaying deliveries.

### `async def run_daily_alerts(shop: ShopService, *, alert_concurrency: int, delay_between_alerts_seconds: float, dry_run: bool, on_shop: ShopOutcomeHandler, on_credentials_expired: CredentialsExpiredHandler) -> dict[str, int]`

**Scope:** `src/services/alerts.py` · `module`

[Source](../src/services/alerts.py#L150)

Check eligible accounts with bounded concurrency and report run totals.

``dry_run`` performs the lookups without sending notifications. The callbacks
handle successful shops and expired credentials and return delivery failure
counts. Totals distinguish expired credentials, shop and delivery failures;
``failures`` is their sum.

## `src/services/analytics.py`

Persistence and orchestration for analytics.

### `async def record_command_invocation(*, command: str, user_id: int, guild_id: int | None, channel_id: int | None) -> None`

**Scope:** `src/services/analytics.py` · `module`

[Source](../src/services/analytics.py#L12)

Persist a successful command invocation with its optional Discord scope.

### `async def command_stats(*, user_id: int | None = None, guild_id: int | None = None) -> tuple[int, str | None]`

**Scope:** `src/services/analytics.py` · `module`

[Source](../src/services/analytics.py#L28)

Return a scoped command-use count and the most-used command.

Exactly one of ``user_id`` or ``guild_id`` is required. Ties for the most-used
command are resolved alphabetically for stable results.

## `src/services/auth.py`

Riot OAuth callbacks, encrypted credentials, and refreshable auth headers.

### `class TokenData(TypedDict)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L30)

Riot token fields after trust-boundary validation.

### `class UserInfo(TypedDict)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L38)

Validated Riot identity fields used to display the linked account name.

### `class LoginCredentials(TypedDict)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L45)

Credential payload constructed from a validated login response.

### `class AuthResult`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L56)

Represent an authentication outcome and localized failure details.

### `class AuthService`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L65)

Manage Riot login, token refresh, entitlement repair, and account linking.

### `def __init__(self, config: Settings, http: HTTPClient, vault: AuthVault) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L68)

Bind validated settings, the shared HTTP client, and token vault.

### `def _credentials(self, account: Account) -> dict[str, Any]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L83)

Normalize unreadable credentials without overwriting the stored blob.

### `async def cancel_logins(self, discord_id: int) -> AsyncIterator[None]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L91)

Invalidate login attempts and serialize deletion with their database commits.

### `async def refresh_version(self) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L105)

Fetch Riot's current client version for authenticated request headers.

### `def riot_headers(self) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L124)

Return the platform and current client-version headers expected by Riot.

### `def login_url(self, discord_id: int) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L134)

Create a Riot authorization URL and retain a short-lived per-user nonce.

### `async def redeem_callback(self, discord_id: int, callback_url: str) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L149)

Exchange a callback code, verify its nonce, and securely link the account.

The callback nonce is single-use and expires after ten minutes. A Riot account
already owned by another Discord user, or a user at the account limit, is
rejected without replacing the existing owner.

### `async def ensure(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L291)

Serialize credential checks for an account and return its usable auth state.

### `async def _ensure_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L299)

Check token lifetime and repair or refresh credentials while holding its lock.

### `async def refresh(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L322)

Refresh one account's Riot tokens under its per-account lock.

### `async def _refresh_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L330)

Refresh tokens with version-checked persistence to protect concurrent updates.

### `async def clear_credentials(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L412)

Remove the selected account's Riot tokens while coordinating with refreshes.

### `async def _clear_credentials_locked(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L419)

Clear credentials only if the stored auth version still matches the caller.

### `async def auth_headers(self, account: Account) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L427)

Return fresh Riot authorization headers or raise when login is required.

### `async def _repair_entitlement(self, account: Account, auth: Mapping[str, Any], *, refresh_on_missing: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L449)

Fetch and persist an entitlement token, optionally refreshing on absence.

### `def prune_expired_nonces(self) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L488)

Release abandoned login attempts after their ten-minute lifetime.

### `async def _user_info(self, auth: Mapping[str, Any]) -> UserInfo | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L497)

Fetch the Riot game name and tag line associated with an access token.

### `async def _entitlement(self, auth: Mapping[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L514)

Request an entitlement token and surface transient Riot failures.

### `async def _region(self, auth: Mapping[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L539)

Resolve the VALORANT shard affinity associated with an ID token.

### `def _user_agent(self) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L561)

Build the Riot authentication user agent from the latest client build.

### `def _token_data(data: dict[str, Any]) -> TokenData`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L571)

Validate token response fields before using or persisting credentials.

### `def decode_jwt(token: str | None) -> dict[str, Any]`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L586)

Decode a JWT payload for claim lookup without performing signature validation.

### `def token_expiry(token: str | None) -> float`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L599)

Return the token's Unix expiry time, or zero when it cannot be decoded.

### `def riot_region(region: str | None) -> str`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L607)

Map missing and LATAM/Brazil affinities to Riot's North America API host.

### `class AuthenticationRequired(RuntimeError)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L612)

Raised when a Riot request cannot proceed without a new user login.

## `src/services/catalog.py`

VALORANT skin, bundle, accessory, and mission metadata with a local cache.

### `def localized_text(value: Any, locale: object | None = None) -> str`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L45)

Resolve VALORANT-API text for a Discord locale with English fallback.

### `def _localized_values(value: Any) -> dict[str, str]`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L64)

Normalize a localized string or locale map into nonempty values.

### `def _catalog_rows(value: Any, label: str) -> list[dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L77)

Validate upstream rows and the identifiers/media consumed by catalog views.

### `class Skin`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L103)

Hold normalized skin identity, display data, pricing, levels, and chromas.

### `def name_for(self, locale: object | None = None) -> str`

**Scope:** `src/services/catalog.py` · `Skin`

[Source](../src/services/catalog.py#L116)

Return this skin's localized or English name, or empty when missing.

### `class Bundle`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L124)

Hold static display metadata for a VALORANT bundle.

### `def name_for(self, locale: object | None = None) -> str`

**Scope:** `src/services/catalog.py` · `Bundle`

[Source](../src/services/catalog.py#L136)

Return this bundle's localized or English name, or empty when missing.

### `def subtitle_for(self, locale: object | None = None) -> str | None`

**Scope:** `src/services/catalog.py` · `Bundle`

[Source](../src/services/catalog.py#L142)

Return this bundle's localized subtitle, if available.

### `def description_for(self, locale: object | None = None) -> str | None`

**Scope:** `src/services/catalog.py` · `Bundle`

[Source](../src/services/catalog.py#L146)

Return this bundle's localized description, if available.

### `class Accessory`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L155)

Hold normalized display data for a non-skin cosmetic reward.

### `def name_for(self, locale: object | None = None) -> str`

**Scope:** `src/services/catalog.py` · `Accessory`

[Source](../src/services/catalog.py#L164)

Return this accessory's localized name, or empty when metadata is missing.

### `def title_text_for(self, locale: object | None = None) -> str | None`

**Scope:** `src/services/catalog.py` · `Accessory`

[Source](../src/services/catalog.py#L168)

Return localized accessory title text, if available.

### `class CatalogService`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L176)

Load, refresh, search, and cache VALORANT catalog data.

### `def __init__(self, http: HTTPClient) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L179)

Prepare in-memory indexes and the working-directory catalog snapshot.

### `async def load(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L201)

Load the saved catalog off the event loop or fetch a fresh snapshot.

### `async def refresh(self, *, check_version: bool = False) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L213)

Fetch the current weapon and bundle catalogs and save their snapshot.

When ``check_version`` is true, skip rebuilding only if the upstream version
and local cache format are current. A saved version change invalidates
accessory metadata, including requests that began before the refresh.
A failed save restores the previous catalog even during cancellation.

### `async def _fetch_data(self, kind: str) -> list[dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L297)

Fetch one catalog endpoint and return its validated data rows.

### `async def mission_metadata(self) -> dict[str, dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L309)

Return cached mission definitions, refreshing them at most every 30 minutes.

### `def _build(self, weapons: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L355)

Normalize weapon and bundle responses and rebuild lookup indexes.

### `def _reindex(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L410)

Index skins by their UUID, offer UUID, and level UUID aliases.

### `def get_skin(self, uuid: str) -> Skin | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L421)

Resolve a skin from any indexed base, offer, or level identifier.

### `def get_bundle(self, uuid: str) -> Bundle | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L425)

Resolve bundle metadata by its Riot UUID.

### `async def accessory(self, item_type: str, uuid: str) -> Accessory | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L430)

Fetch and cache a supported accessory using its Riot item type ID.

### `async def _buddy_accessory(self, uuid: str) -> Accessory | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L468)

Resolve a Riot bundle buddy by its buddy or level UUID.

### `def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L512)

Convert endpoint-specific Riot accessory data into a common display shape.

### `def search_skins(self, query: str, *, locale: object | None = None, limit: int = 25) -> list[Skin]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L538)

Search localized names first, retaining English-name fallback matches.

### `def update_prices(self, prices: dict[str, int]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L560)

Apply current store prices to catalog skins matched by offer identifier.

### `def _serialize(self) -> str`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L567)

Encode the current version, skins, and bundles as compact JSON.

### `def _save(self, snapshot: str) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L602)

Write a complete catalog snapshot through a temporary file replacement.

### `def _deserialize(self, raw: dict[str, Any]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L609)

Restore catalog records from a snapshot and rebuild lookup indexes.

## `src/services/crypto.py`

Authenticated encryption for persisted Riot credential payloads.

### `class AuthVault`

**Scope:** `src/services/crypto.py` · `module`

[Source](../src/services/crypto.py#L12)

Encrypt and decrypt credential mappings with the configured Fernet key.

### `def __init__(self, key: str) -> None`

**Scope:** `src/services/crypto.py` · `AuthVault`

[Source](../src/services/crypto.py#L15)

Validate the encryption key and prepare the Fernet cipher.

### `def encrypt(self, auth: Mapping[str, Any]) -> str`

**Scope:** `src/services/crypto.py` · `AuthVault`

[Source](../src/services/crypto.py#L24)

Serialize and authenticate a credential mapping as a Fernet token.

### `def decrypt(self, token: str | None) -> dict[str, Any]`

**Scope:** `src/services/crypto.py` · `AuthVault`

[Source](../src/services/crypto.py#L29)

Decode a stored token, returning an empty mapping when it is absent.

## `src/services/emojis.py`

Cache Discord application emojis and create them from bundled image assets.

### `class ApplicationEmojiService`

**Scope:** `src/services/emojis.py` · `module`

[Source](../src/services/emojis.py#L29)

Application emoji cache with safe text fallbacks.

### `def __init__(self, client: discord.Client) -> None`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L32)

Bind the Discord client and initialize the serialized emoji cache.

### `async def warm(self) -> None`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L38)

Load existing application emojis and create any bundled assets that are missing.

### `async def currency(self, kind: str) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L55)

Return the emoji for VP, Radianite, or Kingdom Credits, if available.

### `async def battlepass_bars(self) -> tuple[str, str]`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L60)

Return the filled and empty battlepass progress-bar emoji strings.

### `def skin_emoji(self, tier_uuid: str | None) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L67)

Return a cached application emoji for a skin tier, if available.

### `def skin_name(self, name: str, tier_uuid: str | None) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L75)

Prefix a skin name with its cached tier emoji when available.

### `async def _get_or_create(self, name: str, source: Path) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L80)

Resolve or create one application emoji, returning empty text on failure.

## `src/services/gameplay.py`

Fetch VALORANT progression and matchmaking penalties for linked accounts.

### `class Reward(TypedDict)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L15)

Validated display data for the next battlepass reward.

### `class BattlepassProgress(TypedDict)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L25)

The active battlepass and its account-specific progress.

### `class MissionTask(TypedDict)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L36)

One objective's known progress and target.

### `class MissionProgress(TypedDict)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L43)

Mission display data, including explicitly unavailable metadata.

### `class Penalty(TypedDict)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L55)

Normalized penalty data after validating its account identity.

### `class GameplayService`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L67)

Riot gameplay APIs used by battlepass, mission, and penalty commands.

### `def __init__(self, http: HTTPClient, auth: AuthService, catalog: CatalogService) -> None`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L70)

Bind the shared Riot client, authentication service, and catalog.

### `async def battlepass(self, account: Account, *, locale: str | None = None) -> BattlepassProgress`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L79)

Return the active battlepass level, XP, expiry, and next reward.

### `async def missions(self, account: Account, *, locale: str | None = None) -> list[MissionProgress]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L176)

Join the account's live mission progress with cached catalog definitions.

### `async def penalties(self, account: Account) -> list[Penalty]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L203)

Fetch and normalize an account's current Riot matchmaking penalties.

### `def _mission_progress(row: Any, definitions: dict[str, dict[str, Any]], locale: str | None) -> MissionProgress | None`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L306)

Normalize one Riot mission row and its objective progress for display.

### `async def _reward(self, levels: list[dict[str, Any]], level: int, locale: str | None) -> Reward`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L387)

Resolve the next battlepass reward to display data, including its icon.

### `def _api_data(value: Any) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L444)

Return validated API metadata rows.

### `def _rows(value: Any) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L449)

Reject malformed battlepass containers and rows at the API boundary.

### `class GameplayUnavailable(RuntimeError)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L456)

Riot did not return usable gameplay data.

### `def _nonnegative_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L460)

Convert a non-Boolean value to a nonnegative integer when possible.

### `def _positive_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L471)

Convert a value to a positive integer or return ``None``.

### `def _parse_datetime(value: Any) -> datetime | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L476)

Parse an ISO timestamp and attach UTC when the input has no timezone.

## `src/services/http.py`

Shared Riot HTTP transport with URL redaction and per-host rate-limit backoff.

### `def _safe_log_url(url: str) -> str`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L21)

Remove credentials, query data, and UUID path segments from a URL.

### `class HTTPResult`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L41)

Hold an HTTP response status and decoded body.

### `class HTTPClient`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L48)

Own a reusable aiohttp session and normalize transport failures.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L51)

Store request settings and initialize session and rate-limit state.

### `async def start(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L57)

Create the shared aiohttp session with configured timeout and pool limits.

### `async def close(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L63)

Close the shared session when it has been started and remains open.

### `async def request(self, method: str, url: str, *, headers: dict[str, str] | None = None, json: Any = None, data: Any = None) -> HTTPResult`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L68)

Send a request, decode its body, and apply per-host rate-limit backoff.


**Raises**
- **`RuntimeError`** — If the client has not been started.
- **`HTTPFailure`** — If the request is rate-limited, times out, fails at the
  transport layer, or its response body cannot be decoded.

### `def _retry_after(self, value: str | None) -> int`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L119)

Parse Retry-After seconds or an HTTP date and clamp the backoff.

### `class HTTPFailure(RuntimeError)`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L134)

Raised for rate limits, transport/decoding failures, and request timeouts.

### `class RateLimited(HTTPFailure)`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L138)

Expose the remaining host cooldown to callers that can defer a lookup.

### `def __init__(self, retry_after: float) -> None`

**Scope:** `src/services/http.py` · `RateLimited`

[Source](../src/services/http.py#L141)

Retain the failure message and a nonnegative retry delay.

## `src/services/shop.py`

Normalize authenticated VALORANT shop, featured bundle, and wallet data.

### `class Offer`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L23)

Represent a skin offer with its standard price and optional discount.

### `class AccessoryOffer`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L34)

Represent one accessory and its Kingdom Credit price.

### `class FeaturedBundleItem`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L42)

Represent one account-specific item and its exact bundle offer pricing.

### `class FeaturedBundle`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L53)

Represent one currently featured bundle from an account's storefront.

### `class ShopData`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L66)

Hold account-specific shop offers and separate display/cache expiries.

### `class ShopService`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L78)

Retrieve and normalize Riot storefronts and wallet balances.

### `def __init__(self, config: Settings, http: HTTPClient, auth: AuthService, catalog: CatalogService) -> None`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L81)

Bind dependencies and initialize storefront data and per-account locks.

### `def _account_lock(self, account_id: str) -> asyncio.Lock`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L96)

Return the shared in-process lock used for one account's shop requests.

### `async def clear_cached_storefront(self, account_id: str) -> None`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L100)

Remove an account's cached storefront after coordinating with active fetches.

### `def prune_expired(self) -> None`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L105)

Release expired storefronts, including accounts no longer queried.

### `async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L115)

Return a fresh or unexpired cached storefront for the linked account.

### `async def _fetch_storefront(self, account: Account, headers: dict[str, str]) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L135)

Fetch, repair claims, normalize all shop offers, and cache the result.

### `async def _storefront_request(self, account: Account, headers: dict[str, str]) -> HTTPResult`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L290)

Request one account's regional storefront.

### `async def wallet(self, account: Account) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L301)

Return VP, Radianite, and Kingdom Credit balances for an account.

### `async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L325)

Resolve the storefront's accessory rewards and their Kingdom Credit prices.

### `def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L352)

Extract the raw single-item store offers across Riot response shapes.

### `def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L359)

Build a skin-offer-to-VP-price lookup from the storefront payload.

### `class ShopUnavailable(RuntimeError)`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L376)

Raised when Riot does not return a usable storefront or wallet.

### `def _int_at_least(value: Any, minimum: int) -> int | None`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L380)

Parse an integer only when it meets the requested minimum.

### `def _mapping(value: Any) -> dict[str, Any]`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L391)

Treat malformed optional mappings as absent.

### `def _rows(value: Any) -> list[dict[str, Any]]`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L396)

Keep only mapping entries from an optional Riot list.

### `def _vp_price(value: Any, currency_uuid: str) -> int | None`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L405)

Return a price only when the source entry explicitly uses VALORANT Points.

## `src/services/suggestions.py`

Persistence and orchestration for suggestions.

### `async def create_suggestion(author_id: int, content: str, log_channel_id: int | None) -> Suggestion`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L19)

Create a pending suggestion and its author follow in one transaction.

### `async def record_suggestion_delivery(suggestion: Suggestion, message_id: int) -> Suggestion | None`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L31)

Record the posted message and return its current review, or None if deleted.

### `async def delete_suggestion(suggestion_id: int) -> None`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L40)

Delete a suggestion record by its database ID.

### `async def follow_suggestion(suggestion_id: int, user_id: int) -> bool | Suggestion | None`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L45)

Follow a pending suggestion or return its completed review; missing returns None.

Lock the suggestion until the follow commits so a concurrent review includes
this follower, or returns its final result without creating a late follow.

### `async def unfollow_suggestion(suggestion_id: int, user_id: int) -> UnfollowResult`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L70)

Remove a follow and report missing, own, removed, or absent-follow status.

### `async def review_suggestion(suggestion_id: int, status: ReviewStatus, reason: str) -> tuple[Suggestion, set[int]] | None`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L83)

Atomically review a pending suggestion and return its followers once.

A suggestion that is missing or already reviewed returns ``None``; a successful
review returns the updated record and the distinct follower IDs to notify.

### `async def count_suggestions_by_author(author_id: int) -> int`

**Scope:** `src/services/suggestions.py` · `module`

[Source](../src/services/suggestions.py#L108)

Count suggestions submitted by a Discord user.

## `src/views/__init__.py`

Public timestamp and owner-scoped Discord component exports.

## `src/views/common.py`

Shared Discord presentation helpers used across BotFragg cogs.

### `def timestamp(value: int | float | datetime, style: str = 'R') -> str`

**Scope:** `src/views/common.py` · `module`

[Source](../src/views/common.py#L8)

Format a timestamp as a Discord inline timestamp using the requested style.

## `src/views/components.py`

Persistent interactive controls scoped to the Discord user who created them.

### `class OwnedActionButton(discord.ui.DynamicItem[discord.ui.Button])`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L20)

Create a persistent button whose action can only be used by its owner.

### `def __init__(self, action: str, owner_id: int, payload: str = '', *, label: str | None = None, emoji: str | None = None, style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False) -> None`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L23)

Build a stable custom ID containing the action, owner, and payload.

### `async def from_custom_id(cls, interaction: discord.Interaction[Any], item: discord.ui.Item[Any], match: re.Match[str]) -> OwnedActionButton`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L49)

Reconstruct a persistent button from its custom ID and visible style.

### `async def interaction_check(self, interaction: discord.Interaction[Any]) -> bool`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L68)

Reject interactions from users other than the button's recorded owner.

### `async def callback(self, interaction: discord.Interaction[Any]) -> None`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L82)

Dispatch the button action to its registered handler inside a trace.

### `class OwnedSelect(discord.ui.DynamicItem[discord.ui.Select])`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L99)

Create a persistent select menu whose action is restricted to its owner.

### `def __init__(self, action: str, owner_id: int, payload: str = '', *, placeholder: str | None = None, options: list[discord.SelectOption] | None = None, empty_option_label: str | None = None) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L102)

Build a stable custom ID and a translated placeholder when options are empty.

### `async def from_custom_id(cls, interaction: discord.Interaction[Any], item: discord.ui.Item[Any], match: re.Match[str]) -> OwnedSelect`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L134)

Reconstruct a persistent select menu from its ID and current options.

### `async def interaction_check(self, interaction: discord.Interaction[Any]) -> bool`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L153)

Reject interactions from users other than the menu's recorded owner.

### `async def callback(self, interaction: discord.Interaction[Any]) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L167)

Dispatch the selected value with the menu payload to its registered handler.

### `def _error_embed(message: str) -> discord.Embed`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L185)

Build a compact red embed for an invalid or unavailable component action.

## `src/views/shop.py`

Shared shop presentation for slash commands and scheduled notifications.

### `def _price_line(currency: str, final_price: int, original_price: int | None = None, discount_percent: int | None = None) -> str`

**Scope:** `src/views/shop.py` · `module`

[Source](../src/views/shop.py#L29)

Format a current price and any original price discount on one line.

### `def offer_cards(header: str, offers: list[Offer], currency: str, *, link_item_image: bool, unknown_skin_name: str, emoji_service: ApplicationEmojiService | None = None, header_colour: int = 2105893, locale: object | None = None) -> list[discord.Embed]`

**Scope:** `src/views/shop.py` · `module`

[Source](../src/views/shop.py#L45)

Render a heading and one tier-coloured embed for each skin offer.

### `def add_skin_selector(controls: discord.ui.View, owner_id: int, offers: list[Offer], expires: int, emoji_service: ApplicationEmojiService, translator: BotFraggTranslator, locale: discord.Locale) -> None`

**Scope:** `src/views/shop.py` · `module`

[Source](../src/views/shop.py#L83)

Add a menu containing only the skin offers rendered beside it.

### `def add_account_selector(controls: discord.ui.View, owner_id: int, mode: str, current: str, *, accounts: Sequence[Account], hide_ign: bool = False, translator: BotFraggTranslator, locale: discord.Locale) -> None`

**Scope:** `src/views/shop.py` · `module`

[Source](../src/views/shop.py#L125)

Render an account selector from prepared accounts and current name privacy.

### `def night_market_view(bot: BotFraggBot, interaction: discord.Interaction, data: ShopData, username: str, puuid: str, *, accounts: Sequence[Account], vp: str, hide_ign: bool, mode: str) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/views/shop.py` · `module`

[Source](../src/views/shop.py#L161)

Render Night Market offers and controls without further preparation waits.

## `src/views/ui.py`

VALORANT cog presentation helpers for names, views, embeds, and errors.

### `class EmbedMessage(TypedDict)`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L15)

Keyword arguments for an embed response with optional controls.

### `def _account_display_name(username: str, *, hide_ign: bool, translator: BotFraggTranslator, locale: discord.Locale | str) -> str`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L28)

Return a generic account label when the user has chosen to hide their name.

### `def account_autocomplete_choices(accounts: list[Account], current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L41)

Format account-name matches for Discord's bounded autocomplete menu.

### `def view(*items: discord.ui.Item) -> discord.ui.View`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L52)

Create a persistent view containing the supplied Discord components.

### `def embed(message: str | None = None, *, colour: int = RED, title: str | None = None) -> discord.Embed`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L60)

Build a standard BotFragg embed with optional description, title, and colour.

### `def translated(interaction: discord.Interaction[Any], key: str, **arguments: object) -> str`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L67)

Format one message using the caller's Discord locale.

### `def localized_embed(interaction: discord.Interaction, description_key: str | None = None, *, title_key: str | None = None, colour: int = DARK, description_args: dict[str, object] | None = None, title_args: dict[str, object] | None = None) -> discord.Embed`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L74)

Build an embed from catalog message IDs and the caller's locale.

### `async def error(interaction: discord.Interaction, message: str | Exception, **arguments: object) -> None`

**Scope:** `src/views/ui.py` · `module`

[Source](../src/views/ui.py#L95)

Send a private error embed using the interaction's available response path.
