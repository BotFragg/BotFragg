# Botfragg API reference

This reference covers every Python module, class, and named function in the application, tests, and documentation tools. It is generated from the source docstrings; edit those docstrings and regenerate this page when behavior or signatures change.

## `main.py`

Support the repository's ``python main.py`` startup command.

## `src/__init__.py`

Botfragg bot package.

## `src/bot.py`

Discord client construction, command handling, service wiring, and shutdown.

### `def _command_error_embed() -> discord.Embed`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L28)

Build the generic, user-safe response shown after an unhandled command error.

### `class BotfraggCommandTree(app_commands.CommandTree)`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L36)

Application-command tree with shared context rules and error reporting.

### `def __init__(self, client: discord.Client) -> None`

**Scope:** `src/bot.py` · `BotfraggCommandTree`

[Source](../src/bot.py#L39)

Allow commands in servers and private contexts for guild and user installs.

### `async def _call(self, interaction: discord.Interaction) -> None`

**Scope:** `src/bot.py` · `BotfraggCommandTree`

[Source](../src/bot.py#L49)

Record command executions while leaving autocomplete requests untraced.

### `def _command_name(data: dict[str, object]) -> str`

**Scope:** `src/bot.py` · `BotfraggCommandTree`

[Source](../src/bot.py#L60)

Return the dotted parent and subcommand path from Discord's payload.

### `async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError, /) -> None`

**Scope:** `src/bot.py` · `BotfraggCommandTree`

[Source](../src/bot.py#L79)

Log unhandled app-command errors and send a private generic response.

### `class BotfraggBot(commands.AutoShardedBot)`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L108)

Own Discord lifecycle and the shared Riot, database, and presentation services.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L111)

Configure the bot's prefix, minimal intents, and application services.

### `async def on_command_error(self, context: commands.Context[BotfraggBot], exception: commands.CommandError, /) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L136)

Log failed prefix commands and reply with a generic error message.

### `def register_component(self, action: str, handler: ComponentHandler) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L160)

Register a persistent component action, rejecting duplicate action names.

### `async def setup_hook(self) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L166)

Initialize shared resources, load extensions, and optionally sync commands.

### `async def on_ready(self) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L200)

Set the online activity and log the connected shard and guild counts.

### `async def close(self) -> None`

**Scope:** `src/bot.py` · `BotfraggBot`

[Source](../src/bot.py#L213)

Close Discord, Riot HTTP, database, and monitoring resources in order.

## `src/cogs/__init__.py`

Discord command cogs.

## `src/cogs/events.py`

Discord event listeners for analytics, guild notifications, and shard logs.

### `class EventsCog(commands.Cog)`

**Scope:** `src/cogs/events.py` · `module`

[Source](../src/cogs/events.py#L19)

Record successful commands and report configured Discord lifecycle events.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L22)

Bind event handlers to the running bot instance.

### `async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L27)

Log completed app commands and persist their user, guild, and channel IDs.

### `async def on_guild_join(self, guild: discord.Guild) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L51)

Send a summary to the channel configured for guild joins.

### `async def on_guild_remove(self, guild: discord.Guild) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L58)

Send a summary to the channel configured for guild departures.

### `async def _log_guild_event(self, guild: discord.Guild, channel_id: int | None, title: str) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L64)

Resolve a configured messageable channel and send a guild summary.

### `async def on_shard_ready(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L105)

Report that a Discord shard connected and became ready.

### `async def on_shard_disconnect(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L110)

Report that a Discord shard disconnected.

### `async def on_shard_resumed(self, shard_id: int) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L115)

Report that a disconnected Discord shard resumed its session.

### `async def _log_shard_event(self, shard_id: int, state: str) -> None`

**Scope:** `src/cogs/events.py` · `EventsCog`

[Source](../src/cogs/events.py#L119)

Post a shard state update to the optional logging webhook.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/events.py` · `module`

[Source](../src/cogs/events.py#L135)

Register the Discord event-listener cog with the bot.

## `src/cogs/extra.py`

General Botfragg commands for status, links, suggestions, and shard health.

### `class ExtraCog(commands.Cog)`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L33)

Provide public utility commands and owner-managed suggestion workflows.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L40)

Store the bot and record when this cog started for the info command.

### `async def cog_load(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L45)

Start shard-status updates when their destination is configured.

### `async def cog_unload(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L50)

Cancel and await the shard-status task during extension shutdown.

### `async def ping(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L59)

Report Discord gateway latency and a live database probe duration.

### `async def botinfo(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L78)

Show runtime, deployment, library, and registered-user information.

### `async def links(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L105)

Show an invite link and any configured support, vote, and website links.

### `async def suggest(self, interaction: discord.Interaction, suggestion: app_commands.Range[str, 1, 1000]) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L139)

Persist a feature suggestion and publish it to the configured log channel.

### `async def track(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L185)

Follow an existing suggestion so the caller receives its review result.

### `async def untrack(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L203)

Remove the caller's follow from another user's suggestion.

### `async def approve(self, interaction: discord.Interaction, id: int, reason: str) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L224)

Submit an owner-only approval review for the selected suggestion.

### `async def deny(self, interaction: discord.Interaction, id: int, reason: str) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L232)

Submit an owner-only denial review for the selected suggestion.

### `async def _review_suggestion(self, interaction: discord.Interaction, id: int, reason: str, status: Literal['approved', 'denied']) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L238)

Authorize a review, update its record, and notify its followers.

### `async def _update_suggestion_log(self, suggestion: Suggestion) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L274)

Edit the original suggestion post with the final status and review reason.

### `async def shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L294)

Update or recreate the persistent embed containing per-shard health.

### `async def before_shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L329)

Wait for Discord readiness before the first shard-status update.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L334)

Register the general utility and suggestion cog with the bot.

## `src/cogs/staff.py`

Owner-only Discord diagnostics for users, servers, and command analytics.

### `class StaffCog(commands.Cog)`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L15)

Owner-only operational diagnostics.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L18)

Bind the staff diagnostics to the running bot.

### `async def _owner_only(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L22)

Authorize the bot owner and privately reject all other callers.

### `async def userinfo(self, interaction: discord.Interaction, user: discord.User) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L31)

Show the owner's stored account statistics and shared-server details.

### `async def serverinfo(self, interaction: discord.Interaction, server_id: str) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L64)

Show analytics and membership details for a server Botfragg has joined.

### `async def _favorite_command(self, *, user_id: int | None = None, guild_id: int | None = None) -> str | None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L115)

Return the most-used command for exactly one user or server scope.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L123)

Register the owner-only diagnostics cog with the bot.

## `src/cogs/tasks.py`

Background loops for daily alerts, catalog refresh, and Discord log delivery.

### `class DiscordLogHandler(logging.Handler)`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L25)

Buffer privacy-filtered structured log lines for periodic Discord delivery.

### `def __init__(self) -> None`

**Scope:** `src/cogs/tasks.py` · `DiscordLogHandler`

[Source](../src/cogs/tasks.py#L28)

Create a bounded log buffer using Botfragg's privacy-aware formatter.

### `def emit(self, record: logging.LogRecord) -> None`

**Scope:** `src/cogs/tasks.py` · `DiscordLogHandler`

[Source](../src/cogs/tasks.py#L34)

Format a log record into the buffer or delegate failures to logging.

### `class TasksCog(commands.Cog)`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L42)

Own periodic application jobs and stop them cleanly when unloaded.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L45)

Set job intervals from settings and prepare the optional log handler.

### `async def cog_load(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L58)

Start background loops and attach the log handler when configured.

### `async def cog_unload(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L67)

Cancel and await all active loops, then detach the root log handler.

### `async def daily_alerts(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L88)

Run the daily shop and skin-alert job inside a monitoring transaction.

### `async def configure_daily_alerts(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L94)

Wait for Discord readiness before starting daily alert delivery.

### `async def run_alerts(self, *, dry_run: bool = False) -> dict[str, int]`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L98)

Process eligible users' shops and return counts for the completed run.

### `async def _deliver_daily_alert_result(self, user_id: int, user: User | None, account: Account, shop: ShopData, matches: list[tuple[Alert, Offer]], send_daily_shop: bool) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L111)

Deliver each matching skin alert and the user's optional daily shop.

### `async def _send_alert(self, user_id: int, alert: Alert, offer: Offer) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L126)

DM a matching skin alert with a control owned by the recipient.

### `async def _send_daily_shop(self, user: User, account: Account, shop: ShopData) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L155)

DM the selected account's daily shop as a set of offer embeds.

### `async def _credentials_expired(self, user_id: int) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L179)

Tell a user privately when their Riot login must be renewed.

### `async def version_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L190)

Refresh the Riot client version used in authenticated API requests.

### `async def before_version_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L196)

Wait for Discord readiness before the first version refresh.

### `async def catalog_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L201)

Refresh the VALORANT catalog when its upstream version changes.

### `async def before_catalog_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L207)

Wait for Discord readiness before the first catalog refresh.

### `async def log_flush(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L212)

Send buffered log lines to Discord and requeue them after HTTP failures.

### `async def before_log_flush(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L240)

Wait for Discord readiness before sending buffered logs.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L245)

Register the background-task cog with the bot.

## `src/cogs/valorant/__init__.py`

Initial-release VALORANT command cogs.

## `src/cogs/valorant/_ui.py`

VALORANT cog presentation helpers for names, views, embeds, and errors.

### `def _account_display_name(username: str, *, hide_ign: bool) -> str`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L11)

Return a generic account label when the user has chosen to hide their name.

### `def view(*items: discord.ui.Item) -> discord.ui.View`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L16)

Create a persistent view containing the supplied Discord components.

### `def embed(message: str | None = None, *, colour: int = RED, title: str | None = None) -> discord.Embed`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L24)

Build a standard Botfragg embed with optional description, title, and colour.

### `async def error(interaction: discord.Interaction, message: str) -> None`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L31)

Send a private error embed using the interaction's available response path.

## `src/cogs/valorant/accounts.py`

Slash commands for selecting, listing, and paging through linked accounts.

### `class AccountsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L23)

Present a user's linked Riot accounts and handle account selection.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L26)

Bind the bot and register the persistent account-page action.

### `async def account_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L31)

Return up to 25 of the caller's accounts matching the typed name.

### `def _accounts_embed(accounts: list[Account], current_account_id: str | None, page: int = 0) -> discord.Embed`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L44)

Render one bounded account page and mark the currently selected entry.

### `def _accounts_view(user_id: int, account_count: int, page: int) -> discord.ui.View | None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L66)

Build owner-scoped previous and next controls when multiple pages exist.

### `async def account(self, interaction: discord.Interaction, account: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L87)

Switch the caller's active account using an autocomplete selection.

### `async def accounts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L121)

Show the caller's accounts privately when their name-hiding preference is on.

### `async def accounts_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L142)

Handle a persistent account-page control and refresh its message.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L163)

Register the linked-account commands and component handlers.

## `src/cogs/valorant/alerts.py`

Commands for creating, viewing, removing, and testing skin alerts.

### `class AlertsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L27)

Manage owner-scoped alert records and their persistent Discord controls.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L30)

Bind the bot and register persistent alert-management actions.

### `async def skin_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L36)

Return catalog skin matches suitable for Discord's autocomplete limit.

### `async def alert(self, interaction: discord.Interaction, skin: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L47)

Create a skin alert for the caller's active account and show a remove control.

### `async def alerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L82)

Show the caller's paginated alerts and owner-bound management controls.

### `def _created_embed(self, skin: Skin) -> discord.Embed`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L94)

Build the confirmation card for a newly created skin alert.

### `def _skin_display_name(self, skin: Skin | None) -> str`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L104)

Return a skin name with its tier emoji when the emoji service is available.

### `def _skin_emoji(self, skin: Skin | None) -> str | None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L114)

Return a button emoji for a skin tier when one is available.

### `async def manager_view(self, user_id: int, page: int) -> tuple[discord.Embed, discord.ui.View | None]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L124)

Render one alert page with per-alert removal and optional page controls.

### `async def remove_alert(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L177)

Remove the selected owner-scoped alert and refresh or dismiss its controls.

### `async def alert_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L206)

Validate a page payload and update the alert-management message.

### `async def testalerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L220)

Check login and shop availability, then send the caller a test alert DM.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L283)

Register the skin-alert commands and their persistent handlers.

## `src/cogs/valorant/battlepass.py`

Commands and embed builders for VALORANT battlepass and mission progress.

### `class BattlepassCog(commands.Cog)`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L18)

Display the caller's current battlepass level and mission progress.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L21)

Bind the bot's gameplay, account, and emoji services.

### `async def battlepass(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L26)

Fetch and display the active battlepass for the caller's selected account.

### `async def missions(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L55)

Show the selected account's daily and weekly mission progress privately.

### `def _missions_card(missions: list[dict], filled_bar: str = '█', empty_bar: str = '░') -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L74)

Group mission entries by type and expiry and render progress bars.

### `def _battlepass_card(player: str, data: dict, filled_bar: str = '█', empty_bar: str = '░', *, emoji_service: ApplicationEmojiService | None = None) -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L130)

Render the active act, current tier, next reward, and XP progress bar.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L165)

Register the battlepass and mission commands.

## `src/cogs/valorant/login.py`

Private Riot sign-in flow using an authorization link and callback modal.

### `class LoginModal(discord.ui.Modal)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L15)

Collect the redirect URL returned after a user signs in with Riot.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L25)

Set a five-minute timeout and retain the authentication service owner.

### `async def on_submit(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L30)

Redeem the submitted callback and privately report the login result.

### `class LoginCog(commands.Cog)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L47)

Start Riot sign-in and open the callback URL entry modal.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L50)

Bind the bot and register the persistent login-modal action.

### `async def login(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L58)

Start a nonce-bound Riot login when the caller has account capacity.

### `async def login_modal(self, interaction: discord.Interaction, _: str) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L97)

Open the modal where the caller pastes Riot's redirect URL.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L102)

Register the Riot login command and modal handler.

## `src/cogs/valorant/logout.py`

Commands for clearing Riot credentials or deleting all stored user data.

### `class LogoutCog(commands.Cog)`

**Scope:** `src/cogs/valorant/logout.py` · `module`

[Source](../src/cogs/valorant/logout.py#L14)

Let users disconnect Riot credentials or erase their Botfragg records.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L17)

Bind the bot's account, authentication, and storefront services.

### `async def account_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L21)

Return the caller's linked accounts for the logout command.

### `async def logout(self, interaction: discord.Interaction, account: str | None = None) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L37)

Clear Riot credentials for one linked account while preserving its settings.

### `async def deletedata(self, interaction: discord.Interaction, confirm: bool) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L60)

Permanently delete the caller's records and clear cached storefronts.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `module`

[Source](../src/cogs/valorant/logout.py#L85)

Register the account logout and personal data deletion commands.

## `src/cogs/valorant/settings.py`

Private commands for viewing and changing user display and shop preferences.

### `class SettingsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/settings.py` · `module`

[Source](../src/cogs/valorant/settings.py#L21)

Present user preferences and handle their owner-scoped select menu.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L28)

Bind the bot and register the persistent preference-selection action.

### `async def settings_view(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L34)

Show the caller's saved preferences in an ephemeral response.

### `async def settings_set(self, interaction: discord.Interaction, setting: app_commands.Choice[str]) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L60)

Present Yes/No options for the caller's selected preference.

### `async def setting_selected(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L85)

Validate and persist a setting selection, then update its confirmation.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `module`

[Source](../src/cogs/valorant/settings.py#L106)

Register the user preference commands and selection handler.

## `src/cogs/valorant/shop.py`

Commands for daily, accessory, and Night Market shops and wallet balances.

### `def offer_cards(header: str, offers: list[Offer], currency: str, *, link_item_image: bool, emoji_service: ApplicationEmojiService | None = None) -> list[discord.Embed]`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L34)

Render a heading and one tier-coloured embed for each skin offer.

### `def add_skin_selector(controls: discord.ui.View, owner_id: int, offers: list[Offer], expires: int, emoji_service: ApplicationEmojiService) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L62)

Add a menu containing only the skin offers rendered beside it.

### `class ShopCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L95)

Show the caller's daily shop and handle its account and mode controls.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L98)

Bind the bot and register persistent shop-mode and account actions.

### `async def shop(self, interaction: discord.Interaction, user: discord.User | None = None) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L107)

Show the caller's shop or a shop another user has chosen to share.

### `async def shop_view(self, data: ShopData, username: str, owner_id: int, puuid: str, *, hide_ign: bool = False) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L161)

Build the daily shop embeds and controls for accessories and other accounts.

### `async def shop_mode(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L205)

Render the selected daily, Night Market, or accessory shop mode.

### `def _selection_values(interaction: discord.Interaction, custom_id: str) -> set[str]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L304)

Read the values actually offered by this message's matching select menu.

### `def _video_options(skin: Skin) -> list[discord.SelectOption]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L319)

List playable levels and chromas within Discord's select-menu limit.

### `async def shop_skin(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L343)

Open a private level/chroma menu for a skin offered in this message.

### `async def shop_variant(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L392)

Privately return a selected video only when it belongs to that skin.

### `async def _add_accounts(self, controls: discord.ui.View, owner_id: int, mode: str, current: str, *, hide_ign: bool = False) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L449)

Add a private account selector when the owner has multiple accounts.

### `async def shop_account(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L480)

Validate the selected account and reopen the corresponding shop mode.

### `class NightMarketCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L492)

Display discounted Night Market offers for the selected Riot account.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L495)

Bind the shared shop, account, and emoji services.

### `async def nightmarket(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L502)

Fetch and render Night Market offers or report that none are active.

### `class BalanceCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L553)

Display the selected account's three VALORANT wallet balances.

### `def __init__(self, bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L556)

Bind the shared shop and user-preference services.

### `async def balance(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L564)

Fetch and display VP, Radianite, and Kingdom Credit balances.

### `async def setup(bot: BotfraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L593)

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

[Source](../src/config.py#L163)

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

[Source](../src/database.py#L11)

Resolve relative SQLite paths against the repository root.

### `def _tortoise_config(config: Settings) -> dict[str, object]`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L23)

Build the ORM configuration for the supplied application settings.

### `async def connect_database(config: Settings, *, generate_schemas: bool = False) -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L42)

Initialize Tortoise and optionally create missing development schemas.

### `async def ping_database() -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L49)

Run a minimal query against the default database connection.

### `async def close_database() -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L54)

Close all Tortoise database connections.

### `async def get_shard_status_message_id(channel_id: int) -> int | None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L59)

Return the saved status-message ID for a channel, if one exists.

### `async def save_shard_status_message(channel_id: int, message_id: int) -> None`

**Scope:** `src/database.py` · `module`

[Source](../src/database.py#L65)

Create or update the status-message reference for a channel.

## `src/main.py`

Executable entry point that configures logging and starts Botfragg.

### `def main() -> None`

**Scope:** `src/main.py` · `module`

[Source](../src/main.py#L12)

Load settings, configure observability, and run the Discord client.

## `src/migrations/0001_initial.py`

Create the initial user, account, alert, and suggestion tables.

### `class Migration(migrations.Migration)`

**Scope:** `src/migrations/0001_initial.py` · `module`

[Source](../src/migrations/0001_initial.py#L8)

Define the initial persisted Botfragg schema and ownership relations.

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

Tortoise migration package for the Botfragg database schema.

## `src/models/__init__.py`

Public model exports for application services and Discord cogs.

## `src/models/entities.py`

Tortoise ORM entities and database constraints for Botfragg data.

### `class User(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L9)

Store Discord preferences and the selected linked VALORANT account.

### `class Account(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L23)

Store a user's Riot identity and encrypted authentication payload.

### `class Alert(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L40)

Store a skin alert belonging to one linked Riot account.

### `class Meta`

**Scope:** `src/models/entities.py` · `Alert`

[Source](../src/models/entities.py#L50)

Prevent duplicate alerts for the same account and skin.

### `class CommandInvocation(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L56)

Store a completed command and its optional guild and channel context.

### `class Suggestion(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L67)

Store a user's submitted idea and its review and delivery state.

### `class SuggestionFollower(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L82)

Link a Discord user to a suggestion whose review they want to follow.

### `class Meta`

**Scope:** `src/models/entities.py` · `SuggestionFollower`

[Source](../src/models/entities.py#L91)

Allow each user to follow a suggestion at most once.

### `class ShardStatusMessage(Model)`

**Scope:** `src/models/entities.py` · `module`

[Source](../src/models/entities.py#L97)

Map each configured Discord channel to its persistent status message.

## `src/monitoring.py`

Structured logging and privacy filters for logs and GlitchTip events.

### `class StructuredFormatter(logging.Formatter)`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L55)

Format log records as JSON after filtering sensitive values.

### `def format(self, record: logging.LogRecord) -> str`

**Scope:** `src/monitoring.py` · `StructuredFormatter`

[Source](../src/monitoring.py#L58)

Serialize a scrubbed log record and its safe structured fields.

### `def _scrub(value: Any) -> Any`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L77)

Filter credentials and personal identifiers from nested event data.

### `def _breadcrumb(breadcrumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L104)

Drop network and unrelated log breadcrumbs, then scrub retained data.

### `def _scrub_event(event: dict[str, Any]) -> dict[str, Any]`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L118)

Remove request data and sensitive values from an error event.

### `def _scrub_transaction(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L125)

Remove request payloads and HTTP span details from a transaction.

### `def _scrub_log(log: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L135)

Keep Botfragg logs and serious Discord errors after removing URL data.

### `def _release() -> str`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L149)

Return the installed Botfragg release label or an unknown fallback.

### `def configure_monitoring(config: Settings) -> None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L157)

Enable privacy-filtered GlitchTip telemetry when a DSN is configured.

### `def transaction(name: str, op: str)`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L187)

Start a GlitchTip transaction with the supplied name and operation.

### `def flush_monitoring() -> None`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L192)

End the current monitoring session and flush queued telemetry.

## `src/services/__init__.py`

Domain and external-service adapters.

## `src/services/accounts.py`

Persistence operations for users, Riot accounts, alerts, analytics, and ideas.

### `async def get_user(discord_id: int) -> User | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L33)

Return the stored Botfragg user for a Discord ID, if one exists.

### `async def count_registered_users() -> int`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L38)

Count users with a stored Botfragg profile.

### `async def daily_shop_user_ids() -> set[int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L43)

Return Discord IDs whose saved preference enables daily shop DMs.

### `async def account_for_user(discord_id: int, puuid: str) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L48)

Return a Riot account only when it belongs to the requested Discord user.

### `async def update_user_preference(discord_id: int, field: str, enabled: bool) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L53)

Update one allowlisted Boolean preference and refresh the user's timestamp.

### `async def selected_account(discord_id: int, *, user: User | None = None, accounts: Sequence[Account] | None = None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L63)

Return the active account, choosing the oldest account when none is selected.

A supplied user or account sequence avoids redundant queries; a supplied user
must belong to ``discord_id``. When choosing a default, the database update is
conditional so a concurrent selection is not overwritten.

### `async def list_accounts(discord_id: int) -> list[Account]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L119)

Return a user's Riot accounts in creation order.

### `async def resolve_account(discord_id: int, query: str | None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L124)

Resolve an account by PUUID, case-insensitive name, or one-based position.

### `async def select_account(discord_id: int, account: Account) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L140)

Set a user's active account after verifying that the account is theirs.

### `async def delete_user_data(discord_id: int) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L149)

Delete the user's stored Botfragg records and all linked Riot accounts.

### `class AlertPage`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L166)

Hold one bounded page of alerts and its normalized pagination metadata.

### `async def create_alert(user_id: int, account: Account, skin_uuid: UUID) -> tuple[Alert, bool]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L176)

Create an account-scoped skin alert or return the existing duplicate.

### `async def list_alerts_page(user_id: int, page: int, page_size: int) -> AlertPage`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L185)

Fetch an owner-scoped alert page, wrapping page indexes and bounding size.

### `async def remove_alert(user_id: int, alert_id: int) -> Alert | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L207)

Delete and return an alert only when it belongs to the requesting user.

### `async def first_alert(user_id: int) -> Alert | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L215)

Return a user's first alert with its linked account loaded.

### `async def user_ids_with_alerts() -> set[int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L222)

Return distinct Discord IDs that own at least one alert.

### `async def account_ids_with_alerts(account_ids: list[str]) -> set[str]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L227)

Return only the supplied account IDs that currently have alerts.

### `async def matching_alerts_for_skins(account_id: str, skin_uuids: list[str]) -> list[Alert]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L238)

Fetch alerts matching one account and a bounded set of shop skin IDs.

### `async def run_daily_alerts(shop: ShopService, *, alert_concurrency: int, delay_between_alerts_seconds: float, dry_run: bool, on_shop: ShopOutcomeHandler, on_credentials_expired: CredentialsExpiredHandler) -> dict[str, int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L256)

Check eligible accounts with bounded concurrency and report run totals.

``dry_run`` performs the lookups without sending notifications. The callbacks
handle successful shops and expired credentials; the returned counts include
users, fetched shops, matched alerts, and recoverable failures.

### `async def process(user_id: int) -> None`

**Scope:** `src/services/accounts.py` · `run_daily_alerts`

[Source](../src/services/accounts.py#L291)

Check one user's accounts and dispatch any matching shop results.

### `async def record_command_invocation(*, command: str, user_id: int, guild_id: int | None, channel_id: int | None) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L353)

Persist a successful command invocation with its optional Discord scope.

### `async def command_stats(*, user_id: int | None = None, guild_id: int | None = None) -> tuple[int, str | None]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L369)

Return a scoped command-use count and the most-used command.

Exactly one of ``user_id`` or ``guild_id`` is required. Ties for the most-used
command are resolved alphabetically for stable results.

### `async def create_suggestion(author_id: int, content: str, log_channel_id: int | None) -> Suggestion`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L401)

Create a pending suggestion with its author and optional delivery channel.

### `async def record_suggestion_delivery(suggestion: Suggestion, message_id: int) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L410)

Record the posted message and ensure the author follows the suggestion.

### `async def delete_suggestion(suggestion_id: int) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L419)

Delete a suggestion record by its database ID.

### `async def follow_suggestion(suggestion_id: int, user_id: int) -> bool | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L424)

Follow an existing suggestion, returning ``None`` when it does not exist.

### `async def unfollow_suggestion(suggestion_id: int, user_id: int) -> UnfollowResult`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L434)

Remove a follow and report missing, own, removed, or absent-follow status.

### `async def review_suggestion(suggestion_id: int, status: ReviewStatus, reason: str) -> tuple[Suggestion, set[int]] | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L447)

Atomically review a pending suggestion and return its followers once.

A suggestion that is missing or already reviewed returns ``None``; a successful
review returns the updated record and the distinct follower IDs to notify.

### `async def count_suggestions_by_author(author_id: int) -> int`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L470)

Count suggestions submitted by a Discord user.

## `src/services/auth.py`

Riot OAuth callbacks, encrypted credentials, and refreshable auth headers.

### `class AuthResult`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L29)

Represent an authentication outcome with its account or user-safe error.

### `class AuthService`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L37)

Manage Riot login, token refresh, entitlement repair, and account linking.

### `def __init__(self, config: Settings, http: HTTPClient, vault: AuthVault) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L40)

Bind validated settings, the shared HTTP client, and token vault.

### `async def refresh_version(self) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L50)

Fetch Riot's current client version for authenticated request headers.

### `def riot_headers(self) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L57)

Return the platform and current client-version headers expected by Riot.

### `def login_url(self, discord_id: int) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L67)

Create a Riot authorization URL and retain a short-lived per-user nonce.

### `async def redeem_callback(self, discord_id: int, callback_url: str) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L81)

Exchange a callback code, verify its nonce, and securely link the account.

The callback nonce is single-use and expires after ten minutes. A Riot account
already owned by another Discord user, or a user at the account limit, is
rejected without replacing the existing owner.

### `async def ensure(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L201)

Serialize credential checks for an account and return its usable auth state.

### `async def _ensure_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L209)

Check token lifetime and repair or refresh credentials while holding its lock.

### `async def refresh(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L227)

Refresh one account's Riot tokens under its per-account lock.

### `async def _refresh_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L235)

Refresh tokens with version-checked persistence to protect concurrent updates.

### `async def clear_credentials(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L303)

Remove the selected account's Riot tokens while coordinating with refreshes.

### `async def _clear_credentials_locked(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L310)

Clear credentials only if the stored auth version still matches the caller.

### `async def auth_headers(self, account: Account) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L316)

Return fresh Riot authorization headers or raise when login is required.

### `async def _repair_entitlement(self, account: Account, auth: dict[str, Any], *, refresh_on_missing: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L335)

Fetch and persist an entitlement token, optionally refreshing on absence.

### `async def _user_info(self, auth: dict[str, Any]) -> dict[str, str] | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L366)

Fetch the Riot game name and tag line associated with an access token.

### `async def _entitlement(self, auth: dict[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L380)

Request an entitlement token and surface transient Riot failures.

### `async def _region(self, auth: dict[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L398)

Resolve the VALORANT shard affinity associated with an ID token.

### `def _user_agent(self) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L413)

Build the Riot authentication user agent from the latest client build.

### `def decode_jwt(token: str | None) -> dict[str, Any]`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L423)

Decode a JWT payload for claim lookup without performing signature validation.

### `def token_expiry(token: str | None) -> float`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L436)

Return the token's Unix expiry time, or zero when it cannot be decoded.

### `def riot_region(region: str | None) -> str`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L444)

Map missing and LATAM/Brazil affinities to Riot's North America API host.

### `class AuthenticationRequired(RuntimeError)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L449)

Raised when a Riot request cannot proceed without a new user login.

## `src/services/catalog.py`

VALORANT skin, accessory, and mission metadata with a local catalog cache.

### `class Skin`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L27)

Hold normalized skin identity, display data, pricing, levels, and chromas.

### `class Accessory`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L41)

Hold normalized display data for a non-skin cosmetic reward.

### `class CatalogService`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L49)

Load, refresh, search, and cache VALORANT catalog data.

### `def __init__(self, http: HTTPClient) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L52)

Prepare in-memory indexes and the working-directory catalog snapshot.

### `async def load(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L70)

Load the saved catalog off the event loop or fetch a fresh snapshot.

### `async def refresh(self, *, check_version: bool = False) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L82)

Fetch the current weapon catalog and atomically save its snapshot.

When ``check_version`` is true, skip rebuilding only if the upstream version
and local cache format are current.

### `async def _fetch_data(self, kind: str) -> list[dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L143)

Fetch one catalog endpoint and return its validated data rows.

### `async def mission_metadata(self) -> dict[str, dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L155)

Return cached mission definitions, refreshing them at most every 30 minutes.

### `def _build(self, weapons: list[dict[str, Any]]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L201)

Normalize weapon responses into skins and rebuild identifier indexes.

### `def _reindex(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L227)

Index skins by their UUID, offer UUID, and level UUID aliases.

### `def get_skin(self, uuid: str) -> Skin | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L238)

Resolve a skin from any indexed base, offer, or level identifier.

### `async def accessory(self, item_type: str, uuid: str) -> Accessory | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L242)

Fetch and cache a supported accessory using its Riot item type ID.

### `def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L276)

Convert endpoint-specific Riot accessory data into a common display shape.

### `def search_skins(self, query: str, *, limit: int = 25) -> list[Skin]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L299)

Return fuzzy name matches whose weighted score is at least 35.

### `def update_prices(self, offers: list[dict[str, Any]]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L309)

Apply current store prices to catalog skins matched by offer identifier.

### `def _serialize(self) -> str`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L320)

Encode the current version and normalized skin list as compact JSON.

### `def _save(self, snapshot: str) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L341)

Write a complete catalog snapshot through a temporary file replacement.

### `def _deserialize(self, raw: dict[str, Any]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L348)

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

[Source](../src/services/emojis.py#L24)

Application emoji cache with safe text fallbacks.

### `def __init__(self, client: discord.Client) -> None`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L27)

Bind the Discord client and initialize the serialized emoji cache.

### `async def warm(self) -> None`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L33)

Load existing application emojis and create any bundled assets that are missing.

### `async def currency(self, kind: str) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L52)

Return the emoji for VP, Radianite, or Kingdom Credits, if available.

### `async def battlepass_bars(self) -> tuple[str, str]`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L62)

Return the filled and empty battlepass progress-bar emoji strings.

### `def skin_emoji(self, tier_uuid: str | None) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L69)

Return a cached application emoji for a skin tier, if available.

### `def skin_name(self, name: str, tier_uuid: str | None) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L77)

Prefix a skin name with its cached tier emoji when available.

### `async def _get_or_create(self, name: str, source: Path) -> str`

**Scope:** `src/services/emojis.py` · `ApplicationEmojiService`

[Source](../src/services/emojis.py#L82)

Resolve or create one application emoji, returning empty text on failure.

## `src/services/gameplay.py`

Fetch VALORANT battlepass and mission progression for linked accounts.

### `class GameplayService`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L15)

Riot progression API used by the initial-release battlepass command.

### `def __init__(self, http: HTTPClient, auth: AuthService, catalog: CatalogService) -> None`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L18)

Bind the shared Riot client, authentication service, and catalog.

### `async def battlepass(self, account: Account) -> dict[str, Any]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L27)

Return the active battlepass level, XP, expiry, and next reward.

### `async def missions(self, account: Account) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L102)

Join the account's live mission progress with cached catalog definitions.

### `def _mission_progress(row: Any, definitions: dict[str, dict[str, Any]]) -> dict[str, Any] | None`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L128)

Normalize one Riot mission row and its objective progress for display.

### `async def _reward(self, levels: list[dict[str, Any]], level: int) -> dict[str, Any]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L207)

Resolve the next battlepass reward to display data, including its icon.

### `def _api_data(value: Any) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L247)

Return a validated API response's data list or an empty list.

### `class GameplayUnavailable(RuntimeError)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L256)

Riot did not return usable battlepass data.

### `def _nonnegative_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L260)

Convert a non-Boolean value to a nonnegative integer when possible.

### `def _positive_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L271)

Convert a value to a positive integer or return ``None``.

### `def _parse_datetime(value: Any) -> datetime | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L277)

Parse an ISO timestamp and attach UTC when the input has no timezone.

## `src/services/http.py`

Shared Riot HTTP transport with URL redaction and per-host rate-limit backoff.

### `def _safe_log_url(url: str) -> str`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L19)

Remove credentials, query data, and UUID path segments from a URL.

### `class HTTPResult`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L39)

Hold an HTTP response status, decoded body, and response headers.

### `class HTTPClient`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L47)

Own a reusable aiohttp session and normalize transport failures.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L50)

Store request settings and initialize session and rate-limit state.

### `async def start(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L56)

Create the shared aiohttp session with configured timeout and pool limits.

### `async def close(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L62)

Close the shared session when it has been started and remains open.

### `async def request(self, method: str, url: str, *, headers: dict[str, str] | None = None, json: Any = None, data: Any = None) -> HTTPResult`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L67)

Send a request, decode its body, and apply per-host rate-limit backoff.


**Raises**
- **`RuntimeError`** — If the client has not been started.
- **`RateLimited`** — If the host is still in its retry window or responds with 429.
- **`HTTPFailure`** — If the request times out or fails at the transport layer.

### `def _retry_after(self, value: str | None) -> int`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L111)

Parse and clamp a Retry-After value to the configured backoff limit.

### `class HTTPFailure(RuntimeError)`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L120)

Raised for transport failures and bounded request timeouts.

### `class RateLimited(HTTPFailure)`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L124)

Signal that a host is inside a retry window and expose its delay.

### `def __init__(self, retry_after: float) -> None`

**Scope:** `src/services/http.py` · `RateLimited`

[Source](../src/services/http.py#L127)

Store the delay until the host can be called again.

## `src/services/shop.py`

Normalize authenticated VALORANT storefront, accessory, and wallet data.

### `class Offer`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L23)

Represent a skin offer with its standard price and optional discount.

### `class AccessoryOffer`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L34)

Represent one accessory and its Kingdom Credit price.

### `class ShopData`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L42)

Hold daily, accessory, and Night Market offers with their expiry times.

### `class ShopService`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L52)

Retrieve and normalize Riot storefronts and wallet balances.

### `def __init__(self, config: Settings, http: HTTPClient, auth: AuthService, catalog: CatalogService) -> None`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L55)

Bind dependencies and initialize storefront data and per-account locks.

### `def _account_lock(self, account_id: str) -> asyncio.Lock`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L70)

Return the shared in-process lock used for one account's shop requests.

### `async def clear_cached_storefront(self, account_id: str) -> None`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L78)

Remove an account's cached storefront after coordinating with active fetches.

### `async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L83)

Return a fresh or unexpired cached storefront for the linked account.

### `async def _fetch_storefront(self, account: Account, headers: dict[str, str]) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L98)

Fetch, repair claims when possible, normalize offers, and cache the result.

### `async def _storefront_request(self, account: Account, headers: dict[str, str]) -> HTTPResult`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L163)

Request one account's regional storefront and normalize transport failures.

### `async def wallet(self, account: Account) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L177)

Return VP, Radianite, and Kingdom Credit balances for an account.

### `async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L197)

Resolve the storefront's accessory rewards and their Kingdom Credit prices.

### `def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L213)

Extract the raw single-item store offers across Riot response shapes.

### `def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L220)

Build a skin-offer-to-VP-price lookup from the storefront payload.

### `class ShopUnavailable(RuntimeError)`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L236)

Raised when Riot does not return a usable storefront or wallet.

### `class Maintenance(ShopUnavailable)`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L240)

Raised when VALORANT reports scheduled downtime.

## `src/views/__init__.py`

Public timestamp and owner-scoped Discord component exports.

## `src/views/common.py`

Shared Discord presentation helpers used across Botfragg cogs.

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

### `async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item[Any], match: re.Match[str]) -> OwnedActionButton`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L49)

Reconstruct a persistent button from its custom ID and visible style.

### `async def interaction_check(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L68)

Reject interactions from users other than the button's recorded owner.

### `async def callback(self, interaction: discord.Interaction) -> None`

**Scope:** `src/views/components.py` · `OwnedActionButton`

[Source](../src/views/components.py#L80)

Dispatch the button action to its registered handler inside a trace.

### `class OwnedSelect(discord.ui.DynamicItem[discord.ui.Select])`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L93)

Create a persistent select menu whose action is restricted to its owner.

### `def __init__(self, action: str, owner_id: int, payload: str = '', *, placeholder: str | None = None, options: list[discord.SelectOption] | None = None) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L96)

Build a stable custom ID and provide a safe placeholder option if empty.

### `async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item[Any], match: re.Match[str]) -> OwnedSelect`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L119)

Reconstruct a persistent select menu from its ID and current options.

### `async def interaction_check(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L135)

Reject interactions from users other than the menu's recorded owner.

### `async def callback(self, interaction: discord.Interaction) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L144)

Dispatch the selected value with the menu payload to its registered handler.

### `def _error_embed(message: str) -> discord.Embed`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L157)

Build a compact red embed for an invalid or unavailable component action.

## `tests/conftest.py`

Shared asynchronous database fixtures for the test suite.

### `async def database()`

**Scope:** `tests/conftest.py` · `module`

[Source](../tests/conftest.py#L10)

Initialize the in-memory database for a test and close it afterward.

## `tests/test_alert_pagination.py`

Tests for alert-page ordering, wrapping, and concurrent deletion.

### `async def test_alert_manager_preserves_order_and_page_wrapping() -> None`

**Scope:** `tests/test_alert_pagination.py` · `module`

[Source](../tests/test_alert_pagination.py#L15)

Verify that alert manager preserves order and page wrapping.

### `async def test_alert_manager_handles_deletion_between_count_and_fetch(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_alert_pagination.py` · `module`

[Source](../tests/test_alert_pagination.py#L64)

Verify that alert manager handles deletion between count and fetch.

### `class Query`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch`

[Source](../tests/test_alert_pagination.py#L69)

Capture query filters and pagination bounds, including rows removed between count and fetch.

### `def __init__(self) -> None`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L72)

Seed a stale count before the page fetch returns no remaining rows.

### `def order_by(self, *_args: object) -> Query`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L76)

Record the requested ordering and return this query stub.

### `async def count(self) -> int`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L80)

Return the number of rows represented by this query stub.

### `def offset(self, _offset: int) -> Query`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L84)

Set the query offset and return this query stub.

### `def limit(self, _limit: int) -> Query`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L88)

Set the query limit and return this query stub.

### `def __await__(self)`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query`

[Source](../tests/test_alert_pagination.py#L92)

Make the query stub awaitable and yield its configured rows.

### `async def fetch() -> list[object]`

**Scope:** `tests/test_alert_pagination.py` · `test_alert_manager_handles_deletion_between_count_and_fetch.Query.__await__`

[Source](../tests/test_alert_pagination.py#L95)

Return the configured result from the fake query or HTTP client.

## `tests/test_alerts_service.py`

Tests for alert ownership, bounded queries, batching, and delivery behavior.

### `async def test_create_alert_returns_existing_record_for_duplicate() -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L32)

Verify that creating a duplicate alert returns the existing record.

### `async def test_remove_alert_is_scoped_to_owner() -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L56)

Verify that remove alert is scoped to owner.

### `async def test_alert_job_queries_are_bounded_to_users_accounts_and_skins() -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L70)

Verify that alert job queries are bounded to users accounts and skins.

### `async def test_alert_page_uses_a_bounded_owner_scoped_query(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L97)

Verify that alert page uses a bounded owner scoped query.

### `class Query`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query`

[Source](../tests/test_alerts_service.py#L104)

Capture query filters and pagination bounds, including rows removed between count and fetch.

### `def order_by(self, *_args: object) -> Query`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query`

[Source](../tests/test_alerts_service.py#L110)

Record the requested ordering and return this query stub.

### `async def count(self) -> int`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query`

[Source](../tests/test_alerts_service.py#L114)

Return the number of rows represented by this query stub.

### `def offset(self, value: int) -> Query`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query`

[Source](../tests/test_alerts_service.py#L118)

Set the query offset and return this query stub.

### `def limit(self, value: int) -> Query`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query`

[Source](../tests/test_alerts_service.py#L123)

Set the query limit and return this query stub.

### `def __await__(self)`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query`

[Source](../tests/test_alerts_service.py#L128)

Make the query stub awaitable and yield its configured rows.

### `async def fetch() -> list[object]`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query.Query.__await__`

[Source](../tests/test_alerts_service.py#L131)

Return the configured result from the fake query or HTTP client.

### `def filter_alerts(_cls, **query_filters)`

**Scope:** `tests/test_alerts_service.py` · `test_alert_page_uses_a_bounded_owner_scoped_query`

[Source](../tests/test_alerts_service.py#L139)

Filter the fake alert query by the requested accounts and skins.

### `def shop_data(*skin_uuids: str) -> ShopData`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L158)

Build a shop fixture containing offers for the supplied skin identifiers.

### `async def test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L177)

Verify that daily alert run preserves selection summary and batches alert presence.

### `def tracked_filter(cls, **filters)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence`

[Source](../tests/test_alerts_service.py#L207)

Capture filters used to select accounts that have alerts.

### `class Shop`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence`

[Source](../tests/test_alerts_service.py#L215)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `def __init__(self) -> None`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence.Shop`

[Source](../tests/test_alerts_service.py#L218)

Start storefront-call tracking before the alert job runs.

### `async def storefront(self, account, *, use_cache = True)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence.Shop`

[Source](../tests/test_alerts_service.py#L222)

Return the configured storefront fixture for the requested account.

### `async def on_shop(user_id, _user, account, _shop, alerts, send_daily_shop)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence`

[Source](../tests/test_alerts_service.py#L238)

Capture arguments passed to the daily-shop delivery callback.

### `async def on_credentials_expired(user_id)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence`

[Source](../tests/test_alerts_service.py#L250)

Capture expired-credential callback invocations.

### `async def test_daily_alert_run_cancels_and_awaits_sibling_users_on_failure() -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L309)

Verify that daily alert run cancels and awaits sibling users on failure.

### `class FailingShop`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_cancels_and_awaits_sibling_users_on_failure`

[Source](../tests/test_alerts_service.py#L321)

Fail one storefront lookup so the alert job can verify sibling-task cancellation.

### `async def storefront(self, account, *, use_cache = True)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_cancels_and_awaits_sibling_users_on_failure.FailingShop`

[Source](../tests/test_alerts_service.py#L324)

Return the configured storefront fixture for the requested account.

### `async def unused_callback(*_args)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_cancels_and_awaits_sibling_users_on_failure`

[Source](../tests/test_alerts_service.py#L336)

Fail the test if an unexpected notification callback is invoked.

### `async def test_daily_alert_run_keeps_send_and_delay_order(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L355)

Verify that daily alert run keeps send and delay order.

### `class Shop`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_keeps_send_and_delay_order`

[Source](../tests/test_alerts_service.py#L375)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `async def storefront(self, account, *, use_cache = True)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_keeps_send_and_delay_order.Shop`

[Source](../tests/test_alerts_service.py#L378)

Return the configured storefront fixture for the requested account.

### `async def on_shop(user_id, _user, account, _shop, _alerts, _send_daily_shop)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_keeps_send_and_delay_order`

[Source](../tests/test_alerts_service.py#L386)

Capture arguments passed to the daily-shop delivery callback.

### `async def on_credentials_expired(user_id)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_keeps_send_and_delay_order`

[Source](../tests/test_alerts_service.py#L390)

Capture expired-credential callback invocations.

### `async def record_delay(seconds: float) -> None`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_keeps_send_and_delay_order`

[Source](../tests/test_alerts_service.py#L394)

Record alert delays so delivery ordering can be asserted.

### `async def test_daily_alert_auth_http_5xx_does_not_request_relogin() -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L422)

Verify that daily alert auth HTTP 5xx does not request relogin.

### `class UnavailableHTTP`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_auth_http_5xx_does_not_request_relogin`

[Source](../tests/test_alerts_service.py#L437)

Return an upstream server error to verify temporary failures do not trigger relogin notices.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_auth_http_5xx_does_not_request_relogin.UnavailableHTTP`

[Source](../tests/test_alerts_service.py#L440)

Record request arguments and return the configured HTTP response.

### `async def unused_callback(*_args) -> None`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_auth_http_5xx_does_not_request_relogin`

[Source](../tests/test_alerts_service.py#L444)

Fail the test if an unexpected notification callback is invoked.

### `async def on_credentials_expired(user_id: int) -> None`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_auth_http_5xx_does_not_request_relogin`

[Source](../tests/test_alerts_service.py#L448)

Capture expired-credential callback invocations.

### `async def test_daily_alert_run_batches_user_and_alert_lookups(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_alerts_service.py` · `module`

[Source](../tests/test_alerts_service.py#L474)

Verify that daily alert run batches user and alert lookups.

### `async def count_user_get(cls, *args, **filters)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L500)

Count user-record lookups during the alert run.

### `async def count_account_get(cls, *args, **filters)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L505)

Count account-record lookups during the alert run.

### `def count_account_queries(cls, **filters)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L510)

Count account query executions during the alert run.

### `def count_alert_queries(cls, **filters)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L516)

Count alert query executions during the alert run.

### `class Shop`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L537)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `async def storefront(self, _account, *, use_cache = True)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups.Shop`

[Source](../tests/test_alerts_service.py#L540)

Return the configured storefront fixture for the requested account.

### `async def unused_callback(*_args)`

**Scope:** `tests/test_alerts_service.py` · `test_daily_alert_run_batches_user_and_alert_lookups`

[Source](../tests/test_alerts_service.py#L544)

Fail the test if an unexpected notification callback is invoked.

## `tests/test_analytics.py`

Tests for command invocation recording and scoped statistics.

### `async def test_record_command_invocation_preserves_dm_context() -> None`

**Scope:** `tests/test_analytics.py` · `module`

[Source](../tests/test_analytics.py#L12)

Verify that record command invocation preserves DM context.

### `async def test_command_stats_are_scoped_and_keep_alphabetical_ties() -> None`

**Scope:** `tests/test_analytics.py` · `module`

[Source](../tests/test_analytics.py#L23)

Verify that command stats are scoped and keep alphabetical ties.

### `async def test_command_stats_returns_empty_result_and_requires_one_scope() -> None`

**Scope:** `tests/test_analytics.py` · `module`

[Source](../tests/test_analytics.py#L45)

Verify that command stats returns empty result and requires one scope.

## `tests/test_config_crypto_monitoring.py`

Tests for settings validation, credential encryption, and privacy filters.

### `def _clear_optional_urls(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L30)

Clear optional URL variables so settings tests use a controlled environment.

### `def test_settings_choose_sqlite_for_development(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L37)

Verify that settings choose SQLite for development.

### `def test_settings_reject_invalid_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L50)

Verify that settings reject invalid token encryption key.

### `def test_settings_reject_non_positive_ids(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L69)

Verify that settings reject zero and negative IDs.

### `def test_settings_treat_blank_optional_urls_as_none(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L80)

Verify that blank optional URLs are treated as unset.

### `def test_settings_accept_http_links(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L100)

Verify that settings accept HTTP links.

### `def test_settings_reject_invalid_http_links_without_echoing_value(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L124)

Verify that settings reject invalid HTTP links without echoing value.

### `def test_settings_accept_webhook_urls_supported_by_discord_py(monkeypatch: pytest.MonkeyPatch, host: str) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L138)

Verify that settings accept webhook URLs supported by discord.py.

### `def test_settings_reject_invalid_webhook_urls_without_echoing_token(monkeypatch: pytest.MonkeyPatch, value: str) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L168)

Verify that settings reject invalid webhook urls without echoing token.

### `def test_settings_load_glitchtip_tracking(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L181)

Verify that settings load GlitchTip tracking.

### `def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L192)

Verify that production requires database URL.

### `def test_error_tracking_scrubs_riot_credentials() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L202)

Verify that error tracking scrubs Riot credentials.

### `def test_error_tracking_scrubs_compact_auth_fields_and_raw_tokens() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L212)

Verify that error tracking scrubs compact auth fields and raw tokens.

### `def test_error_tracking_scrubs_riot_puuids() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L248)

Verify that error tracking scrubs Riot PUUIDs.

### `def test_structured_logs_include_safe_extra_fields() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L259)

Verify that structured logs include safe extra fields.

### `def test_discord_log_handler_uses_the_scrubbed_structured_formatter() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L281)

Verify that Discord log handler uses the scrubbed structured formatter.

### `def test_http_log_urls_remove_account_ids_credentials_and_queries() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L303)

Verify that HTTP log urls remove account IDs credentials and queries.

### `def test_error_tracking_ignores_http_breadcrumbs_and_handles_null_category() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L317)

Verify that error tracking ignores HTTP breadcrumbs and handles null category.

### `def test_glitchtip_logs_keep_botfragg_events_and_drop_unrelated_or_url_data() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L326)

Verify that GlitchTip logs keep Botfragg events and drop unrelated or URL data.

### `def test_glitchtip_enables_supported_telemetry(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L364)

Verify that GlitchTip enables supported telemetry.

### `def test_transaction_tracking_removes_request_data() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L390)

Verify that transaction tracking removes request data.

### `def test_error_tracking_removes_request_data() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L402)

Verify that error tracking removes request data.

### `def test_error_tracking_flushes_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L417)

Verify that error tracking flushes on shutdown.

### `def test_auth_vault_round_trip_and_wrong_key() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L434)

Verify that credential encryption round-trips and rejects the wrong key.

### `def test_jwt_decode_and_expiry() -> None`

**Scope:** `tests/test_config_crypto_monitoring.py` · `module`

[Source](../tests/test_config_crypto_monitoring.py#L445)

Verify that JWT decode and expiry.

## `tests/test_migration.py`

Tests for schema migrations and database connection setup.

### `def test_sqlite_in_memory_url_is_preserved() -> None`

**Scope:** `tests/test_migration.py` · `module`

[Source](../tests/test_migration.py#L16)

Verify that the SQLite in-memory URL is preserved.

### `def test_native_initial_migration_matches_current_models() -> None`

**Scope:** `tests/test_migration.py` · `module`

[Source](../tests/test_migration.py#L21)

Verify that native initial migration matches current models.

### `async def test_connect_database_uses_passed_settings(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_migration.py` · `module`

[Source](../tests/test_migration.py#L90)

Verify that connect database uses passed settings.

### `class Runtime`

**Scope:** `tests/test_migration.py` · `test_connect_database_uses_passed_settings`

[Source](../tests/test_migration.py#L100)

Stub Tortoise's model registry and schema-generation call during database setup.

### `async def init(*, config: dict[str, object]) -> None`

**Scope:** `tests/test_migration.py` · `test_connect_database_uses_passed_settings.Runtime`

[Source](../tests/test_migration.py#L104)

Record the ORM configuration passed to database initialization.

### `async def generate_schemas(*, safe: bool) -> None`

**Scope:** `tests/test_migration.py` · `test_connect_database_uses_passed_settings.Runtime`

[Source](../tests/test_migration.py#L109)

Record whether schema generation was requested.

### `async def test_ping_database_queries_the_default_connection(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_migration.py` · `module`

[Source](../tests/test_migration.py#L123)

Verify that ping database queries the default connection.

### `class Connection`

**Scope:** `tests/test_migration.py` · `test_ping_database_queries_the_default_connection`

[Source](../tests/test_migration.py#L129)

Capture the health-check SQL sent to Tortoise's default database connection.

### `async def execute_query(self, query: str) -> None`

**Scope:** `tests/test_migration.py` · `test_ping_database_queries_the_default_connection.Connection`

[Source](../tests/test_migration.py#L132)

Record the query and return the configured fake database result.

### `def get_connection(alias: str) -> Connection`

**Scope:** `tests/test_migration.py` · `test_ping_database_queries_the_default_connection`

[Source](../tests/test_migration.py#L136)

Return the fake default database connection.

## `tests/test_models_services.py`

Tests for model invariants and account, authentication, shop, and catalog services.

### `def _fake_access_token(expires_in: int = 3600) -> str`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L58)

Create a JWT-shaped access token with the requested expiry.

### `def _fake_jwt(**claims: object) -> str`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L69)

Create a JWT-shaped token containing the supplied claims.

### `async def test_account_selection_preserves_invariant() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L76)

Verify that account selection preserves invariant.

### `async def test_selected_account_updates_user_timestamp() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L94)

Verify that selected account updates user timestamp.

### `async def test_user_preference_updates_user_timestamp() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L109)

Verify that user preference updates user timestamp.

### `async def test_select_account_updates_user_timestamp() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L123)

Verify that select account updates user timestamp.

### `async def test_user_preference_service_validates_and_updates_fields() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L138)

Verify that user preference service validates and updates fields.

### `async def test_selected_account_does_not_overwrite_concurrent_selection(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L154)

Verify that selected account does not overwrite concurrent selection.

### `async def paused_lookup(cls, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_selected_account_does_not_overwrite_concurrent_selection`

[Source](../tests/test_models_services.py#L168)

Pause account selection until the test releases its synchronization gate.

### `async def test_alert_unique_per_account_and_skin() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L194)

Verify that each account can have only one alert for a given skin.

### `async def test_command_analytics_keeps_dm_context_nullable() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L205)

Verify that command analytics keeps DM context nullable.

### `async def test_delete_user_data_removes_personal_records() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L217)

Verify that delete user data removes personal records.

### `async def test_suggestion_followers_are_unique_per_user() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L238)

Verify that suggestion followers are unique per user.

### `async def test_shard_status_message_is_reused_per_channel() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L247)

Verify that shard status message is reused per channel.

### `async def test_staff_favorite_command_uses_the_highest_count() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L260)

Verify that staff favorite command uses the highest count.

### `async def test_cached_shop_requires_active_credentials() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L272)

Verify that cached shop requires active credentials.

### `class LoggedOutAuth`

**Scope:** `tests/test_models_services.py` · `test_cached_shop_requires_active_credentials`

[Source](../tests/test_models_services.py#L275)

Simulate missing credentials to verify cached storefront data is not served after logout.

### `async def auth_headers(self, account)`

**Scope:** `tests/test_models_services.py` · `test_cached_shop_requires_active_credentials.LoggedOutAuth`

[Source](../tests/test_models_services.py#L278)

Return the test authorization headers for the fake account.

### `async def test_expired_shop_cache_entry_is_removed_when_refetch_fails() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L292)

Verify that expired shop cache entry is removed when refetch fails.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_expired_shop_cache_entry_is_removed_when_refetch_fails`

[Source](../tests/test_models_services.py#L295)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_expired_shop_cache_entry_is_removed_when_refetch_fails.Auth`

[Source](../tests/test_models_services.py#L298)

Return the test authorization headers for the fake account.

### `async def fail_fetch(_account, _headers)`

**Scope:** `tests/test_models_services.py` · `test_expired_shop_cache_entry_is_removed_when_refetch_fails`

[Source](../tests/test_models_services.py#L306)

Raise the configured failure on a storefront fetch.

### `async def test_expired_shop_cache_entry_is_removed_when_auth_fails() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L319)

Verify that expired shop cache entry is removed when auth fails.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_expired_shop_cache_entry_is_removed_when_auth_fails`

[Source](../tests/test_models_services.py#L322)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_expired_shop_cache_entry_is_removed_when_auth_fails.Auth`

[Source](../tests/test_models_services.py#L325)

Return the test authorization headers for the fake account.

### `async def test_shop_service_resolves_accessory_offer_data() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L340)

Verify that shop service resolves accessory offer data.

### `class Catalog`

**Scope:** `tests/test_models_services.py` · `test_shop_service_resolves_accessory_offer_data`

[Source](../tests/test_models_services.py#L344)

Provide controlled accessory metadata for storefront offer normalization.

### `async def accessory(self, item_type: str, item_id: str) -> Accessory | None`

**Scope:** `tests/test_models_services.py` · `test_shop_service_resolves_accessory_offer_data.Catalog`

[Source](../tests/test_models_services.py#L347)

Return the configured catalog accessory fixture.

### `async def test_concurrent_auth_ensure_serializes_entitlement_repair() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L376)

Verify that concurrent auth ensure serializes entitlement repair.

### `class RejectingHTTP`

**Scope:** `tests/test_models_services.py` · `test_concurrent_auth_ensure_serializes_entitlement_repair`

[Source](../tests/test_models_services.py#L389)

Reject entitlement requests to verify concurrent authentication checks serialize repair.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_concurrent_auth_ensure_serializes_entitlement_repair.RejectingHTTP`

[Source](../tests/test_models_services.py#L394)

Record request arguments and return the configured HTTP response.

### `async def entitlement(_auth) -> str | None`

**Scope:** `tests/test_models_services.py` · `test_concurrent_auth_ensure_serializes_entitlement_repair`

[Source](../tests/test_models_services.py#L409)

Return the configured fake entitlement response.

### `async def test_auth_refresh_transients_do_not_become_login_required(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L442)

Verify that auth refresh transients do not become login required.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_auth_refresh_transients_do_not_become_login_required`

[Source](../tests/test_models_services.py#L455)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_auth_refresh_transients_do_not_become_login_required.FailingHTTP`

[Source](../tests/test_models_services.py#L458)

Record request arguments and return the configured HTTP response.

### `async def test_entitlement_transients_do_not_become_login_required(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L479)

Verify that entitlement transients do not become login required.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_entitlement_transients_do_not_become_login_required`

[Source](../tests/test_models_services.py#L492)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_entitlement_transients_do_not_become_login_required.FailingHTTP`

[Source](../tests/test_models_services.py#L495)

Record request arguments and return the configured HTTP response.

### `async def test_auth_refresh_transient_status_does_not_become_login_required(status) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L514)

Verify that auth refresh transient status does not become login required.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_auth_refresh_transient_status_does_not_become_login_required`

[Source](../tests/test_models_services.py#L529)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_auth_refresh_transient_status_does_not_become_login_required.FailingHTTP`

[Source](../tests/test_models_services.py#L532)

Record request arguments and return the configured HTTP response.

### `async def test_entitlement_transient_status_does_not_become_login_required(status) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L548)

Verify that entitlement transient status does not become login required.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_entitlement_transient_status_does_not_become_login_required`

[Source](../tests/test_models_services.py#L563)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_entitlement_transient_status_does_not_become_login_required.FailingHTTP`

[Source](../tests/test_models_services.py#L566)

Record request arguments and return the configured HTTP response.

### `async def test_shop_wallet_normalizes_transient_auth_failures(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L583)

Verify that shop wallet normalizes transient auth failures.

### `class FailingAuth`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_auth_failures`

[Source](../tests/test_models_services.py#L586)

Raise controlled credential errors so dependent services can classify login failures.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_auth_failures.FailingAuth`

[Source](../tests/test_models_services.py#L589)

Return the test authorization headers for the fake account.

### `async def test_shop_wallet_normalizes_transient_http_failures(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L602)

Verify that shop wallet normalizes transient HTTP failures.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_http_failures`

[Source](../tests/test_models_services.py#L605)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_http_failures.Auth`

[Source](../tests/test_models_services.py#L608)

Return the test authorization headers for the fake account.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_http_failures`

[Source](../tests/test_models_services.py#L612)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_shop_wallet_normalizes_transient_http_failures.FailingHTTP`

[Source](../tests/test_models_services.py#L615)

Record request arguments and return the configured HTTP response.

### `async def test_gameplay_normalizes_transient_auth_failures(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L628)

Verify that gameplay normalizes transient auth failures.

### `class FailingAuth`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_auth_failures`

[Source](../tests/test_models_services.py#L631)

Raise controlled credential errors so dependent services can classify login failures.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_auth_failures.FailingAuth`

[Source](../tests/test_models_services.py#L634)

Return the test authorization headers for the fake account.

### `async def test_gameplay_normalizes_transient_http_failures(failure) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L647)

Verify that gameplay normalizes transient HTTP failures.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_http_failures`

[Source](../tests/test_models_services.py#L650)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_http_failures.Auth`

[Source](../tests/test_models_services.py#L653)

Return the test authorization headers for the fake account.

### `class FailingHTTP`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_http_failures`

[Source](../tests/test_models_services.py#L657)

Return controlled Riot API failures for retry and authentication-state assertions.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_gameplay_normalizes_transient_http_failures.FailingHTTP`

[Source](../tests/test_models_services.py#L660)

Record request arguments and return the configured HTTP response.

### `async def test_gameplay_missions_join_contract_progress_with_catalog_metadata() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L671)

Verify that gameplay missions join contract progress with catalog metadata.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_gameplay_missions_join_contract_progress_with_catalog_metadata`

[Source](../tests/test_models_services.py#L675)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_gameplay_missions_join_contract_progress_with_catalog_metadata.Auth`

[Source](../tests/test_models_services.py#L678)

Return the test authorization headers for the fake account.

### `class HTTP`

**Scope:** `tests/test_models_services.py` · `test_gameplay_missions_join_contract_progress_with_catalog_metadata`

[Source](../tests/test_models_services.py#L682)

Stub the shared Riot client so request handling and shutdown can be observed.

### `async def request(self, _method, url, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_gameplay_missions_join_contract_progress_with_catalog_metadata.HTTP`

[Source](../tests/test_models_services.py#L685)

Record request arguments and return the configured HTTP response.

### `async def test_concurrent_login_callbacks_respect_account_limit() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L740)

Verify that concurrent login callbacks respect account limit.

### `class LoginHTTP`

**Scope:** `tests/test_models_services.py` · `test_concurrent_login_callbacks_respect_account_limit`

[Source](../tests/test_models_services.py#L751)

Provide controlled OAuth responses for concurrent login and account-limit scenarios.

### `async def request(self, method, url, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_concurrent_login_callbacks_respect_account_limit.LoginHTTP`

[Source](../tests/test_models_services.py#L754)

Record request arguments and return the configured HTTP response.

### `async def test_logout_clears_credentials_saved_during_refresh() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L822)

Verify that logout clears credentials saved during refresh.

### `class RefreshHTTP`

**Scope:** `tests/test_models_services.py` · `test_logout_clears_credentials_saved_during_refresh`

[Source](../tests/test_models_services.py#L835)

Pause token refresh requests so logout can protect credentials updated concurrently.

### `async def request(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_logout_clears_credentials_saved_during_refresh.RefreshHTTP`

[Source](../tests/test_models_services.py#L838)

Record request arguments and return the configured HTTP response.

### `async def entitlement(_auth) -> str`

**Scope:** `tests/test_models_services.py` · `test_logout_clears_credentials_saved_during_refresh`

[Source](../tests/test_models_services.py#L852)

Return the configured fake entitlement response.

### `async def test_concurrent_storefront_requests_share_one_fetch() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L873)

Verify that concurrent storefront requests share one fetch.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_concurrent_storefront_requests_share_one_fetch`

[Source](../tests/test_models_services.py#L876)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_concurrent_storefront_requests_share_one_fetch.Auth`

[Source](../tests/test_models_services.py#L879)

Return the test authorization headers for the fake account.

### `async def fetch(_account, _headers) -> SimpleNamespace`

**Scope:** `tests/test_models_services.py` · `test_concurrent_storefront_requests_share_one_fetch`

[Source](../tests/test_models_services.py#L893)

Return the configured result from the fake query or HTTP client.

### `async def test_shop_service_releases_idle_account_locks() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L912)

Verify that shop service releases idle account locks.

### `class Auth`

**Scope:** `tests/test_models_services.py` · `test_shop_service_releases_idle_account_locks`

[Source](../tests/test_models_services.py#L915)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_models_services.py` · `test_shop_service_releases_idle_account_locks.Auth`

[Source](../tests/test_models_services.py#L918)

Return the test authorization headers for the fake account.

### `async def fetch(_account, _headers) -> SimpleNamespace`

**Scope:** `tests/test_models_services.py` · `test_shop_service_releases_idle_account_locks`

[Source](../tests/test_models_services.py#L925)

Return the configured result from the fake query or HTTP client.

### `async def test_catalog_load_reads_file_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L938)

Verify that catalog load reads file off event loop.

### `def track_read(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_catalog_load_reads_file_off_event_loop`

[Source](../tests/test_models_services.py#L960)

Record the worker thread used to read the catalog snapshot.

### `async def test_catalog_snapshot_round_trips_skin_chromas() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L972)

Verify skin chromas survive catalog build, save, and load.

### `class CatalogHTTP`

**Scope:** `tests/test_models_services.py` · `test_catalog_snapshot_round_trips_skin_chromas`

[Source](../tests/test_models_services.py#L977)

Provide deterministic version and skin catalog responses.

### `async def request(self, _method: str, url: str)`

**Scope:** `tests/test_models_services.py` · `test_catalog_snapshot_round_trips_skin_chromas.CatalogHTTP`

[Source](../tests/test_models_services.py#L980)

Return the manifest or skin response for the requested URL.

### `async def test_catalog_load_refreshes_legacy_snapshot_with_same_manifest() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1036)

Verify a legacy snapshot refreshes even when Riot's manifest matches.

### `class CatalogHTTP`

**Scope:** `tests/test_models_services.py` · `test_catalog_load_refreshes_legacy_snapshot_with_same_manifest`

[Source](../tests/test_models_services.py#L1059)

Provide manifest and upgraded catalog responses for the test.

### `async def request(self, _method: str, url: str)`

**Scope:** `tests/test_models_services.py` · `test_catalog_load_refreshes_legacy_snapshot_with_same_manifest.CatalogHTTP`

[Source](../tests/test_models_services.py#L1062)

Record requests and return the configured catalog response.

### `async def test_failed_catalog_upgrade_keeps_legacy_data_and_retries() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1098)

Verify failed upgrades preserve the old catalog and remain retryable.

### `class CatalogHTTP`

**Scope:** `tests/test_models_services.py` · `test_failed_catalog_upgrade_keeps_legacy_data_and_retries`

[Source](../tests/test_models_services.py#L1118)

Return catalog failures while tracking upgrade attempts.

### `async def request(self, _method: str, url: str)`

**Scope:** `tests/test_models_services.py` · `test_failed_catalog_upgrade_keeps_legacy_data_and_retries.CatalogHTTP`

[Source](../tests/test_models_services.py#L1123)

Return the manifest or a failure for the weapon catalog.

### `def test_catalog_data_file_uses_the_working_directory() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1146)

Verify that catalog data file uses the working directory.

### `async def test_concurrent_accessory_lookups_share_one_request() -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1152)

Verify that concurrent accessory lookups share one request.

### `class HTTP`

**Scope:** `tests/test_models_services.py` · `test_concurrent_accessory_lookups_share_one_request`

[Source](../tests/test_models_services.py#L1158)

Stub the shared Riot client so request handling and shutdown can be observed.

### `async def request(self, _method: str, _url: str)`

**Scope:** `tests/test_models_services.py` · `test_concurrent_accessory_lookups_share_one_request.HTTP`

[Source](../tests/test_models_services.py#L1161)

Record request arguments and return the configured HTTP response.

### `async def test_catalog_refresh_writes_a_stable_snapshot_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1193)

Verify that catalog refresh writes a stable snapshot off event loop.

### `class CatalogHTTP`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_writes_a_stable_snapshot_off_event_loop`

[Source](../tests/test_models_services.py#L1200)

Provide a fake version and weapons catalog response.

### `async def request(self, _method, url)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_writes_a_stable_snapshot_off_event_loop.CatalogHTTP`

[Source](../tests/test_models_services.py#L1203)

Return the matching version or weapon catalog fixture.

### `def track_write(self, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_writes_a_stable_snapshot_off_event_loop`

[Source](../tests/test_models_services.py#L1233)

Record the worker thread used to write the catalog snapshot.

### `async def delayed_to_thread(function, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_writes_a_stable_snapshot_off_event_loop`

[Source](../tests/test_models_services.py#L1238)

Wait for the test gate before invoking the worker-thread operation.

### `async def test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_models_services.py` · `module`

[Source](../tests/test_models_services.py#L1261)

Verify that catalog refresh waits for file worker after repeated cancellation.

### `class VersionHTTP`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation`

[Source](../tests/test_models_services.py#L1268)

Provide a stable game version to the catalog refresh test.

### `async def request(self, _method, _url)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation.VersionHTTP`

[Source](../tests/test_models_services.py#L1271)

Return the configured version response.

### `async def fetch_weapons(_kind)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation`

[Source](../tests/test_models_services.py#L1278)

Return the minimal weapon and skin data needed by catalog refresh.

### `async def delayed_to_thread(function, *args, **kwargs)`

**Scope:** `tests/test_models_services.py` · `test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation`

[Source](../tests/test_models_services.py#L1297)

Hold the file worker until cancellation behavior has been observed.

## `tests/test_shard_status_service.py`

Tests for persistent shard-status message reuse and replacement.

### `async def test_shard_status_message_can_be_reused_and_replaced() -> None`

**Scope:** `tests/test_shard_status_service.py` · `module`

[Source](../tests/test_shard_status_service.py#L14)

Verify that shard status message can be reused and replaced.

## `tests/test_suggestions_service.py`

Tests for suggestion persistence, following, and review transitions.

### `async def test_submission_persists_delivery_and_author_follow_atomically() -> None`

**Scope:** `tests/test_suggestions_service.py` · `module`

[Source](../tests/test_suggestions_service.py#L19)

Verify that submission persists delivery and author follow atomically.

### `async def test_follow_suggestion_is_idempotent_and_scoped() -> None`

**Scope:** `tests/test_suggestions_service.py` · `module`

[Source](../tests/test_suggestions_service.py#L33)

Verify that follow suggestion is idempotent and scoped.

### `async def test_unfollow_suggestion_reports_domain_outcomes() -> None`

**Scope:** `tests/test_suggestions_service.py` · `module`

[Source](../tests/test_suggestions_service.py#L44)

Verify that unfollow suggestion reports domain outcomes.

### `async def test_review_updates_pending_suggestion_once_and_returns_followers() -> None`

**Scope:** `tests/test_suggestions_service.py` · `module`

[Source](../tests/test_suggestions_service.py#L56)

Verify that review updates pending suggestion once and returns followers.

## `tests/test_views_commands.py`

Tests for Discord command responses, privacy, component controls, and lifecycle behavior.

### `def test_dynamic_component_ids_fit_discord_limit() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L41)

Verify that dynamic component IDs fit Discord limit.

### `async def test_unhandled_app_command_error_returns_ephemeral_response() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L67)

Verify that unhandled app command error returns ephemeral response.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_unhandled_app_command_error_returns_ephemeral_response`

[Source](../tests/test_views_commands.py#L71)

Capture whether an interaction was deferred and whether its initial response was private.

### `def is_done(self) -> bool`

**Scope:** `tests/test_views_commands.py` · `test_unhandled_app_command_error_returns_ephemeral_response.Response`

[Source](../tests/test_views_commands.py#L74)

Report whether the fake interaction response has been sent.

### `async def send_message(self, *, embed, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_unhandled_app_command_error_returns_ephemeral_response.Response`

[Source](../tests/test_views_commands.py#L78)

Record the initial message sent through the fake interaction.

### `async def test_unhandled_prefix_command_error_returns_generic_response() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L92)

Verify that unhandled prefix command error returns generic response.

### `async def send(*, embed: discord.Embed) -> None`

**Scope:** `tests/test_views_commands.py` · `test_unhandled_prefix_command_error_returns_generic_response`

[Source](../tests/test_views_commands.py#L96)

Record the follow-up message sent through the fake interaction.

### `async def test_links_invite_preserves_zero_permissions() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L113)

Verify that links invite preserves zero permissions.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_links_invite_preserves_zero_permissions`

[Source](../tests/test_views_commands.py#L117)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_links_invite_preserves_zero_permissions.Response`

[Source](../tests/test_views_commands.py#L120)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_links_invite_preserves_zero_permissions`

[Source](../tests/test_views_commands.py#L124)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_links_invite_preserves_zero_permissions.Followup`

[Source](../tests/test_views_commands.py#L127)

Record the follow-up message sent through the fake interaction.

### `async def test_accessory_shop_renders_catalog_item_without_changing_output(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L153)

Verify that accessory shop renders catalog item without changing output.

### `class Shop`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L175)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `async def storefront(self, _account)`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output.Shop`

[Source](../tests/test_views_commands.py#L178)

Return the configured storefront fixture for the requested account.

### `async def accessory_offers(self, shop_data)`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output.Shop`

[Source](../tests/test_views_commands.py#L182)

Return the configured accessory-shop offers.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L187)

Return deterministic currency and progress markers for embed assertions.

### `async def currency(self, key: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output.EmojiService`

[Source](../tests/test_views_commands.py#L190)

Return a stable currency marker for embed assertions.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L195)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output.Response`

[Source](../tests/test_views_commands.py#L198)

Record that the fake interaction response was deferred.

### `async def account_for_user(_owner_id: int, _puuid: str)`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L202)

Return the test account only for the matching user and PUUID.

### `async def get_user(_owner_id: int)`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L206)

Return the configured user fixture for the requested Discord ID.

### `async def list_accounts(_owner_id: int)`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L210)

Return the configured accounts for the requested Discord user.

### `async def edit_original_response(*, embeds, view) -> None`

**Scope:** `tests/test_views_commands.py` · `test_accessory_shop_renders_catalog_item_without_changing_output`

[Source](../tests/test_views_commands.py#L214)

Record edits to the fake interaction's original response.

### `def test_glitchtip_groups_subcommands_separately() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L249)

Verify that GlitchTip groups subcommands separately.

### `def test_shop_offer_layout_uses_tier_colour() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L259)

Verify that shop offer layout uses tier colour.

### `async def test_shop_skin_menu_selects_tiered_skin_and_returns_private_video() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L279)

Verify tier emoji options and private level/chroma video delivery.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video`

[Source](../tests/test_views_commands.py#L304)

Return stable tier emoji labels for the shop selector test.

### `def skin_emoji(self, _tier_uuid: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video.EmojiService`

[Source](../tests/test_views_commands.py#L307)

Return the fixture's tier emoji.

### `def skin_name(self, name: str, _tier_uuid: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video.EmojiService`

[Source](../tests/test_views_commands.py#L311)

Prefix the fixture's tier emoji to a displayed name.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video`

[Source](../tests/test_views_commands.py#L315)

Capture private interaction replies for response assertions.

### `def __init__(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video.Response`

[Source](../tests/test_views_commands.py#L318)

Initialize the captured response list.

### `async def send_message(self, content: str, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_skin_menu_selects_tiered_skin_and_returns_private_video.Response`

[Source](../tests/test_views_commands.py#L322)

Record a response's content and keyword arguments.

### `async def test_daily_shop_view_includes_only_its_offers_in_skin_menu(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L374)

Verify the standard daily shop view exposes its current offer choices.

### `async def list_accounts(_owner_id: int) -> list[object]`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_view_includes_only_its_offers_in_skin_menu`

[Source](../tests/test_views_commands.py#L380)

Return two accounts so selector ordering is visible in the view.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_view_includes_only_its_offers_in_skin_menu`

[Source](../tests/test_views_commands.py#L387)

Return stable currency and tier emoji markers for shop cards.

### `async def currency(self, _kind: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_view_includes_only_its_offers_in_skin_menu.EmojiService`

[Source](../tests/test_views_commands.py#L390)

Return the fixture currency marker.

### `def skin_name(self, name: str, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_view_includes_only_its_offers_in_skin_menu.EmojiService`

[Source](../tests/test_views_commands.py#L394)

Return skin names without a tier prefix for this fixture.

### `def skin_emoji(self, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_view_includes_only_its_offers_in_skin_menu.EmojiService`

[Source](../tests/test_views_commands.py#L398)

Report that no custom tier emoji is available.

### `async def test_shop_video_selector_rejects_forged_and_mismatched_values() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L438)

Verify menu values and cached skin ownership gate video delivery.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_shop_video_selector_rejects_forged_and_mismatched_values`

[Source](../tests/test_views_commands.py#L457)

Capture invalid selector messages for assertions.

### `def __init__(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_video_selector_rejects_forged_and_mismatched_values.Response`

[Source](../tests/test_views_commands.py#L460)

Initialize the response history.

### `async def send_message(self, content: str, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_video_selector_rejects_forged_and_mismatched_values.Response`

[Source](../tests/test_views_commands.py#L464)

Record a message and its response options.

### `async def test_nightmarket_command_includes_skin_video_menu(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L526)

Verify Night Market slash-command offers receive their selector.

### `async def selected_account(_owner_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L534)

Return the account fixture for the Night Market command.

### `async def get_user(_owner_id: int) -> None`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L538)

Report default visibility preferences for the fixture user.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L545)

Provide stable currency and tier emoji values for embeds.

### `async def currency(self, _kind: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L548)

Return the fixture's VP marker.

### `def skin_name(self, name: str, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L552)

Return a skin name without a tier marker.

### `def skin_emoji(self, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L556)

Report no custom tier emoji for the fixture skin.

### `class Shop`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L560)

Return the fixture storefront for command rendering.

### `async def storefront(self, _account: object) -> ShopData`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.Shop`

[Source](../tests/test_views_commands.py#L563)

Return the configured Night Market data.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L567)

Verify the command defers before sending its follow-up.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.Response`

[Source](../tests/test_views_commands.py#L570)

Assert that the command uses a thinking response.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L574)

Capture the Night Market message and its controls.

### `def __init__(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.Followup`

[Source](../tests/test_views_commands.py#L577)

Initialize the captured follow-up payload.

### `async def send(self, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_nightmarket_command_includes_skin_video_menu.Followup`

[Source](../tests/test_views_commands.py#L581)

Store the follow-up message arguments.

### `async def test_daily_shop_dm_includes_skin_video_menu() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L608)

Verify daily-shop notification DMs include the shared skin selector.

### `class Target`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L613)

Capture the daily-shop DM sent by the task notification.

### `async def send(self, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu.Target`

[Source](../tests/test_views_commands.py#L616)

Store the DM arguments.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu`

[Source](../tests/test_views_commands.py#L620)

Provide stable currency and tier emoji values for the DM.

### `async def currency(self, _kind: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L623)

Return the fixture's VP marker.

### `def skin_name(self, name: str, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L627)

Return a skin name without a tier marker.

### `def skin_emoji(self, _tier_uuid: str | None) -> str`

**Scope:** `tests/test_views_commands.py` · `test_daily_shop_dm_includes_skin_video_menu.EmojiService`

[Source](../tests/test_views_commands.py#L631)

Report no custom tier emoji for the fixture skin.

### `async def test_shop_account_selector_hides_names_when_requested(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L660)

Verify that shop account selector hides names when requested.

### `async def list_accounts(_: int) -> list[SimpleNamespace]`

**Scope:** `tests/test_views_commands.py` · `test_shop_account_selector_hides_names_when_requested`

[Source](../tests/test_views_commands.py#L669)

Return the configured accounts for the requested Discord user.

### `async def test_shop_hides_full_in_game_name_when_preference_enabled(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L686)

Verify that shop hides full in game name when preference enabled.

### `async def get_user(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L692)

Return the configured user fixture for the requested Discord ID.

### `async def selected_account(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L696)

Return the configured active account for the command under test.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L700)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled.Response`

[Source](../tests/test_views_commands.py#L703)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L707)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embeds: list[discord.Embed], view: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled.Followup`

[Source](../tests/test_views_commands.py#L710)

Record the follow-up message sent through the fake interaction.

### `class Shop`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L714)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `async def storefront(self, _account: object) -> ShopData`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled.Shop`

[Source](../tests/test_views_commands.py#L717)

Return the configured storefront fixture for the requested account.

### `async def shop_view(_data, username, _owner_id, _puuid, *, hide_ign = False)`

**Scope:** `tests/test_views_commands.py` · `test_shop_hides_full_in_game_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L730)

Return the expected shop embeds and interactive controls.

### `async def test_account_switch_hides_name_when_preference_enabled(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L749)

Verify that account switch hides name when preference enabled.

### `async def list_accounts(_user_id: int) -> list[SimpleNamespace]`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L757)

Return the configured accounts for the requested Discord user.

### `async def resolve_account(_user_id: int, _value: str) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L761)

Resolve the requested account from the fixture list.

### `async def get_user(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L765)

Return the configured user fixture for the requested Discord ID.

### `async def select_account(_user_id: int, _account: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L769)

Record the account selected by the command under test.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L773)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled.Response`

[Source](../tests/test_views_commands.py#L776)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L780)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed) -> None`

**Scope:** `tests/test_views_commands.py` · `test_account_switch_hides_name_when_preference_enabled.Followup`

[Source](../tests/test_views_commands.py#L783)

Record the follow-up message sent through the fake interaction.

### `async def test_battlepass_hides_name_when_preference_enabled(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L803)

Verify that battlepass hides name when preference enabled.

### `async def selected_account(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L818)

Return the configured active account for the command under test.

### `async def get_user(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L822)

Return the configured user fixture for the requested Discord ID.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L826)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled.Response`

[Source](../tests/test_views_commands.py#L829)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L833)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed) -> None`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled.Followup`

[Source](../tests/test_views_commands.py#L836)

Record the follow-up message sent through the fake interaction.

### `class Gameplay`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L840)

Return controlled battlepass or mission data without making Riot requests.

### `async def battlepass(self, _account: object) -> dict[str, object]`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled.Gameplay`

[Source](../tests/test_views_commands.py#L843)

Return the configured battlepass progression fixture.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled`

[Source](../tests/test_views_commands.py#L847)

Return deterministic currency and progress markers for embed assertions.

### `async def battlepass_bars(self) -> tuple[str, str]`

**Scope:** `tests/test_views_commands.py` · `test_battlepass_hides_name_when_preference_enabled.EmojiService`

[Source](../tests/test_views_commands.py#L850)

Return progress-bar markers used by embed assertions.

### `async def test_missions_command_shows_weekly_progress_privately(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L874)

Verify that missions command shows weekly progress privately.

### `async def selected_account(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately`

[Source](../tests/test_views_commands.py#L881)

Return the configured active account for the command under test.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately`

[Source](../tests/test_views_commands.py#L885)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately.Response`

[Source](../tests/test_views_commands.py#L888)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately`

[Source](../tests/test_views_commands.py#L892)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately.Followup`

[Source](../tests/test_views_commands.py#L895)

Record the follow-up message sent through the fake interaction.

### `class Gameplay`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately`

[Source](../tests/test_views_commands.py#L899)

Return controlled battlepass or mission data without making Riot requests.

### `async def missions(self, selected: object) -> list[dict[str, object]]`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately.Gameplay`

[Source](../tests/test_views_commands.py#L902)

Return the configured mission-progress fixture.

### `class EmojiService`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately`

[Source](../tests/test_views_commands.py#L958)

Return deterministic currency and progress markers for embed assertions.

### `async def battlepass_bars(self) -> tuple[str, str]`

**Scope:** `tests/test_views_commands.py` · `test_missions_command_shows_weekly_progress_privately.EmojiService`

[Source](../tests/test_views_commands.py#L961)

Return progress-bar markers used by embed assertions.

### `async def test_testalerts_reports_temporary_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1001)

Verify that testalerts reports temporary auth failure.

### `async def selected_account(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure`

[Source](../tests/test_views_commands.py#L1009)

Return the configured active account for the command under test.

### `async def first_alert(_user_id: int) -> SimpleNamespace`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure`

[Source](../tests/test_views_commands.py#L1013)

Return the alert fixture used by the command under test.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure`

[Source](../tests/test_views_commands.py#L1017)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure.Response`

[Source](../tests/test_views_commands.py#L1020)

Record that the fake interaction response was deferred.

### `def is_done(self) -> bool`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure.Response`

[Source](../tests/test_views_commands.py#L1024)

Report whether the fake interaction response has been sent.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure`

[Source](../tests/test_views_commands.py#L1028)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure.Followup`

[Source](../tests/test_views_commands.py#L1031)

Record the follow-up message sent through the fake interaction.

### `class Auth`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure`

[Source](../tests/test_views_commands.py#L1036)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def ensure(self, _account: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_testalerts_reports_temporary_auth_failure.Auth`

[Source](../tests/test_views_commands.py#L1039)

Return the configured fake authentication result.

### `def test_accounts_layout_marks_selected_account() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1057)

Verify that accounts layout marks selected account.

### `def test_accounts_paginate_after_discord_embed_field_limit() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1065)

Verify that accounts paginate after Discord embed field limit.

### `def test_battlepass_uses_qotix_progress_hierarchy() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1081)

Verify that battlepass uses Qotix progress hierarchy.

### `def test_alert_keeps_qotix_direct_skin_input() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1110)

Verify that alert keeps Qotix direct skin input.

### `def test_alert_removal_control_fits_a_persistent_dm() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1116)

Verify that alert removal control fits a persistent DM.

### `def test_bot_preserves_discord_http_client(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1122)

Verify that bot preserves Discord HTTP client.

### `async def test_bot_stops_extensions_before_closing_shared_resources(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1133)

Verify that bot stops extensions before closing shared resources.

### `class HTTP`

**Scope:** `tests/test_views_commands.py` · `test_bot_stops_extensions_before_closing_shared_resources`

[Source](../tests/test_views_commands.py#L1142)

Stub the shared Riot client so request handling and shutdown can be observed.

### `async def close(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_bot_stops_extensions_before_closing_shared_resources.HTTP`

[Source](../tests/test_views_commands.py#L1145)

Record that the fake client or database connection was closed.

### `async def close_database() -> None`

**Scope:** `tests/test_views_commands.py` · `test_bot_stops_extensions_before_closing_shared_resources`

[Source](../tests/test_views_commands.py#L1151)

Record database shutdown during bot cleanup.

### `async def close_discord(_bot) -> None`

**Scope:** `tests/test_views_commands.py` · `test_bot_stops_extensions_before_closing_shared_resources`

[Source](../tests/test_views_commands.py#L1155)

Record Discord client shutdown during bot cleanup.

### `async def test_deletedata_clears_cached_shops_after_database_delete(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1169)

Verify that deletedata clears cached shops after database delete.

### `async def list_accounts(user_id: int) -> list[SimpleNamespace]`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete`

[Source](../tests/test_views_commands.py#L1176)

Return the configured accounts for the requested Discord user.

### `async def delete_user_data(user_id: int) -> bool`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete`

[Source](../tests/test_views_commands.py#L1181)

Record deletion of the user's stored data.

### `class Shop`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete`

[Source](../tests/test_views_commands.py#L1186)

Return deterministic storefront data and record account lookups for alert and command assertions.

### `async def clear_cached_storefront(self, account_id: str) -> None`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete.Shop`

[Source](../tests/test_views_commands.py#L1189)

Record removal of the account's cached storefront.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete`

[Source](../tests/test_views_commands.py#L1193)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete.Response`

[Source](../tests/test_views_commands.py#L1196)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete`

[Source](../tests/test_views_commands.py#L1200)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_deletedata_clears_cached_shops_after_database_delete.Followup`

[Source](../tests/test_views_commands.py#L1203)

Record the follow-up message sent through the fake interaction.

### `async def test_shop_deletion_cleanup_waits_for_storefront_headers_in_flight() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1226)

Verify that shop deletion cleanup waits for storefront headers in flight.

### `class Auth`

**Scope:** `tests/test_views_commands.py` · `test_shop_deletion_cleanup_waits_for_storefront_headers_in_flight`

[Source](../tests/test_views_commands.py#L1231)

Stub authentication with controlled Riot credentials and login outcomes for service tests.

### `async def auth_headers(self, _account) -> dict[str, str]`

**Scope:** `tests/test_views_commands.py` · `test_shop_deletion_cleanup_waits_for_storefront_headers_in_flight.Auth`

[Source](../tests/test_views_commands.py#L1234)

Return the test authorization headers for the fake account.

### `async def fetch(_account, _headers)`

**Scope:** `tests/test_views_commands.py` · `test_shop_deletion_cleanup_waits_for_storefront_headers_in_flight`

[Source](../tests/test_views_commands.py#L1244)

Return the configured result from the fake query or HTTP client.

### `async def test_tasks_cog_awaits_cancelled_background_loops() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1264)

Verify that tasks cog awaits cancelled background loops.

### `async def worker() -> None`

**Scope:** `tests/test_views_commands.py` · `test_tasks_cog_awaits_cancelled_background_loops`

[Source](../tests/test_views_commands.py#L1268)

Simulate the cancellable background task used by the test.

### `class Loop`

**Scope:** `tests/test_views_commands.py` · `test_tasks_cog_awaits_cancelled_background_loops`

[Source](../tests/test_views_commands.py#L1276)

Expose a running task and record cancellation for cog-shutdown assertions.

### `def __init__(self, task: asyncio.Task[None]) -> None`

**Scope:** `tests/test_views_commands.py` · `test_tasks_cog_awaits_cancelled_background_loops.Loop`

[Source](../tests/test_views_commands.py#L1279)

Retain the worker task whose shutdown and cancellation are asserted.

### `def get_task(self) -> asyncio.Task[None]`

**Scope:** `tests/test_views_commands.py` · `test_tasks_cog_awaits_cancelled_background_loops.Loop`

[Source](../tests/test_views_commands.py#L1283)

Return the fake background loop's current task.

### `def cancel(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_tasks_cog_awaits_cancelled_background_loops.Loop`

[Source](../tests/test_views_commands.py#L1287)

Cancel the fake task and record the cancellation.

### `async def test_task_notifications_handle_http_errors_while_fetching_user(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1308)

Verify that task notifications handle HTTP errors while fetching user.

### `async def fetch_user(user_id: int) -> None`

**Scope:** `tests/test_views_commands.py` · `test_task_notifications_handle_http_errors_while_fetching_user`

[Source](../tests/test_views_commands.py#L1314)

Return the configured Discord user fixture.

### `async def currency(_name: str) -> str`

**Scope:** `tests/test_views_commands.py` · `test_task_notifications_handle_http_errors_while_fetching_user`

[Source](../tests/test_views_commands.py#L1321)

Return a stable currency marker for embed assertions.

### `async def test_extra_cog_awaits_cancelled_background_loop() -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1357)

Verify that extra cog awaits cancelled background loop.

### `async def worker() -> None`

**Scope:** `tests/test_views_commands.py` · `test_extra_cog_awaits_cancelled_background_loop`

[Source](../tests/test_views_commands.py#L1361)

Simulate the cancellable background task used by the test.

### `class Loop`

**Scope:** `tests/test_views_commands.py` · `test_extra_cog_awaits_cancelled_background_loop`

[Source](../tests/test_views_commands.py#L1371)

Expose a running task and record cancellation for cog-shutdown assertions.

### `def get_task(self) -> asyncio.Task[None]`

**Scope:** `tests/test_views_commands.py` · `test_extra_cog_awaits_cancelled_background_loop.Loop`

[Source](../tests/test_views_commands.py#L1374)

Return the fake background loop's current task.

### `def cancel(self) -> None`

**Scope:** `tests/test_views_commands.py` · `test_extra_cog_awaits_cancelled_background_loop.Loop`

[Source](../tests/test_views_commands.py#L1378)

Cancel the fake task and record the cancellation.

### `async def test_initial_release_command_contract(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1389)

Verify that the initial release command groups remain available.

### `async def test_ping_uses_database_probe_and_keeps_latency_embed(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1437)

Verify that ping uses database probe and keeps latency embed.

### `class Response`

**Scope:** `tests/test_views_commands.py` · `test_ping_uses_database_probe_and_keeps_latency_embed`

[Source](../tests/test_views_commands.py#L1444)

Capture whether an interaction was deferred and whether its initial response was private.

### `async def defer(self, *, thinking: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_ping_uses_database_probe_and_keeps_latency_embed.Response`

[Source](../tests/test_views_commands.py#L1447)

Record that the fake interaction response was deferred.

### `class Followup`

**Scope:** `tests/test_views_commands.py` · `test_ping_uses_database_probe_and_keeps_latency_embed`

[Source](../tests/test_views_commands.py#L1451)

Capture outgoing embeds and privacy flags sent after an interaction's initial response.

### `async def send(self, *, embed: discord.Embed) -> None`

**Scope:** `tests/test_views_commands.py` · `test_ping_uses_database_probe_and_keeps_latency_embed.Followup`

[Source](../tests/test_views_commands.py#L1454)

Record the follow-up message sent through the fake interaction.

### `async def ping_database() -> None`

**Scope:** `tests/test_views_commands.py` · `test_ping_uses_database_probe_and_keeps_latency_embed`

[Source](../tests/test_views_commands.py#L1458)

Stub and record the database health check.

### `async def test_setup_hook_passes_bot_settings_to_database(monkeypatch: pytest.MonkeyPatch) -> None`

**Scope:** `tests/test_views_commands.py` · `module`

[Source](../tests/test_views_commands.py#L1488)

Verify that setup hook passes bot settings to database.

### `async def connect_database(settings: Settings, *, generate_schemas: bool) -> None`

**Scope:** `tests/test_views_commands.py` · `test_setup_hook_passes_bot_settings_to_database`

[Source](../tests/test_views_commands.py#L1498)

Capture the settings passed to database initialization.

### `async def no_op(*args: object, **kwargs: object) -> None`

**Scope:** `tests/test_views_commands.py` · `test_setup_hook_passes_bot_settings_to_database`

[Source](../tests/test_views_commands.py#L1503)

Provide an intentionally empty callback for this test.

## `tools/generate_api_reference.py`

Generate a browsable API reference from the repository's Python docstrings.

### `def _python_files() -> list[Path]`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L26)

Return application, test, and documentation-tool modules in stable order.

### `def _definitions(node: ast.AST, scope: tuple[str, ...] = ())`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L34)

Yield each named class and function, including definitions nested in callables.

### `def _argument_text(argument: ast.arg) -> str`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L49)

Render one parameter name and its declared type without evaluating defaults.

### `def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef, qualified_name: str) -> str`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L56)

Render a callable's complete annotated signature for Markdown display.

### `def _render_docstring(docstring: str) -> list[str]`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L96)

Format a cleaned Python docstring as readable Markdown prose and lists.

### `def render_reference() -> str`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L119)

Build the complete module, class, and callable reference from source files.

### `def main() -> int`

**Scope:** `tools/generate_api_reference.py` · `module`

[Source](../tools/generate_api_reference.py#L171)

Write the API reference or verify it matches the current source docstrings.
