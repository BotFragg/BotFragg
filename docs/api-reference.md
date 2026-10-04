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

### `class BotFraggCommandTree(app_commands.CommandTree)`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L39)

Application-command tree with shared context rules and error reporting.

### `def __init__(self, client: discord.Client) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L42)

Allow commands in servers and private contexts for guild and user installs.

### `async def _call(self, interaction: discord.Interaction) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L52)

Record command executions while leaving autocomplete requests untraced.

### `def _command_name(data: dict[str, object]) -> str`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L63)

Return the dotted parent and subcommand path from Discord's payload.

### `async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError, /) -> None`

**Scope:** `src/bot.py` · `BotFraggCommandTree`

[Source](../src/bot.py#L82)

Log unhandled app-command errors and send a private generic response.

### `class BotFraggBot(commands.AutoShardedBot)`

**Scope:** `src/bot.py` · `module`

[Source](../src/bot.py#L117)

Own Discord lifecycle and the shared Riot, database, and presentation services.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L120)

Configure the bot's prefix, minimal intents, and application services.

### `async def on_command_error(self, context: commands.Context[BotFraggBot], exception: commands.CommandError, /) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L146)

Log failed prefix commands and reply with a generic error message.

### `def register_component(self, action: str, handler: ComponentHandler) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L170)

Register a persistent component action, rejecting duplicate action names.

### `async def setup_hook(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L176)

Initialize shared resources, load extensions, and optionally sync commands.

### `async def on_ready(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L212)

Set the online activity and log the connected shard and guild counts.

### `async def close(self) -> None`

**Scope:** `src/bot.py` · `BotFraggBot`

[Source](../src/bot.py#L225)

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

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/events.py` · `module`

[Source](../src/cogs/events.py#L135)

Register the Discord event-listener cog with the bot.

## `src/cogs/extra.py`

General BotFragg commands for status, links, suggestions, and shard health.

### `class ExtraCog(commands.Cog)`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L46)

Provide public utility commands and owner-managed suggestion workflows.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L57)

Store the bot and record when this cog started for the info command.

### `async def cog_load(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L73)

Start shard-status updates when their destination is configured.

### `async def cog_unload(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L78)

Cancel and await the shard-status task during extension shutdown.

### `async def ping(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L92)

Report Discord gateway latency and a live database probe duration.

### `async def botinfo(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L122)

Show recent public updates and BotFragg runtime information.

### `async def _latest_commit_summary(self, locale: discord.Locale) -> str`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L230)

Fetch and cache five public commits, formatting them per request locale.

### `def _public_links(self, user: discord.ClientUser, locale: discord.Locale) -> discord.ui.View`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L310)

Build link buttons for the configured public URLs.

### `def _help_category(command: app_commands.Command, translator: BotFraggTranslator, locale: discord.Locale) -> str`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L343)

Use each command's cog module to place it in a help category.

### `def _command_mentions(commands: list[discord.AppCommand]) -> dict[str, str]`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L363)

Return Discord-formatted mentions for all synced commands and subcommands.

### `async def help(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L390)

List registered slash commands by category in the embed description.

### `async def links(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L449)

Show an invite link and any configured support, vote, and website links.

### `async def suggest(self, interaction: discord.Interaction, suggestion: app_commands.Range[str, 1, 1000]) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L471)

Persist a feature suggestion and publish it to the configured log channel.

### `async def track(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L530)

Follow an existing suggestion so the caller receives its review result.

### `async def untrack(self, interaction: discord.Interaction, id: int) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L556)

Remove the caller's follow from another user's suggestion.

### `async def approve(self, interaction: discord.Interaction, id: int, reason: str) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L587)

Submit an owner-only approval review for the selected suggestion.

### `async def deny(self, interaction: discord.Interaction, id: int, reason: str) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L600)

Submit an owner-only denial review for the selected suggestion.

### `async def _review_suggestion(self, interaction: discord.Interaction, id: int, reason: str, status: Literal['approved', 'denied']) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L606)

Authorize a review, update its record, and notify its followers.

### `async def _update_suggestion_log(self, suggestion: Suggestion) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L663)

Edit the original suggestion post with the final status and review reason.

### `async def shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L683)

Update or recreate the persistent embed containing per-shard health.

### `async def before_shard_status(self) -> None`

**Scope:** `src/cogs/extra.py` · `ExtraCog`

[Source](../src/cogs/extra.py#L718)

Wait for Discord readiness before the first shard-status update.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/extra.py` · `module`

[Source](../src/cogs/extra.py#L723)

Register the general utility and suggestion cog with the bot.

## `src/cogs/staff.py`

Owner-only Discord diagnostics for users, servers, and command analytics.

### `class StaffCog(commands.Cog)`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L15)

Owner-only operational diagnostics.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L18)

Bind the staff diagnostics to the running bot.

### `async def _owner_only(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L22)

Authorize the bot owner and privately reject all other callers.

### `async def userinfo(self, interaction: discord.Interaction, user: discord.User) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L36)

Show the owner's stored account statistics and shared-server details.

### `async def serverinfo(self, interaction: discord.Interaction, server_id: str) -> None`

**Scope:** `src/cogs/staff.py` · `StaffCog`

[Source](../src/cogs/staff.py#L97)

Show analytics and Discord's cached membership count for a server.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/staff.py` · `module`

[Source](../src/cogs/staff.py#L168)

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

Create a bounded log buffer using BotFragg's privacy-aware formatter.

### `def emit(self, record: logging.LogRecord) -> None`

**Scope:** `src/cogs/tasks.py` · `DiscordLogHandler`

[Source](../src/cogs/tasks.py#L34)

Format a log record into the buffer or delegate failures to logging.

### `class TasksCog(commands.Cog)`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L42)

Own periodic application jobs and stop them cleanly when unloaded.

### `def __init__(self, bot: BotFraggBot) -> None`

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

[Source](../src/cogs/tasks.py#L157)

DM the selected account's daily shop as a set of offer embeds.

### `async def _credentials_expired(self, user_id: int) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L192)

Tell a user privately when their Riot login must be renewed.

### `async def version_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L207)

Refresh the Riot client version used in authenticated API requests.

### `async def before_version_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L213)

Wait for Discord readiness before the first version refresh.

### `async def catalog_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L218)

Refresh the VALORANT catalog when its upstream version changes.

### `async def before_catalog_refresh(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L224)

Wait for Discord readiness before the first catalog refresh.

### `async def log_flush(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L229)

Send buffered log lines to Discord and requeue them after HTTP failures.

### `async def before_log_flush(self) -> None`

**Scope:** `src/cogs/tasks.py` · `TasksCog`

[Source](../src/cogs/tasks.py#L257)

Wait for Discord readiness before sending buffered logs.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/tasks.py` · `module`

[Source](../src/cogs/tasks.py#L262)

Register the background-task cog with the bot.

## `src/cogs/valorant/__init__.py`

Initial-release VALORANT command cogs.

## `src/cogs/valorant/_ui.py`

VALORANT cog presentation helpers for names, views, embeds, and errors.

### `def _account_display_name(username: str, *, hide_ign: bool, translator: BotFraggTranslator | None = None, locale: discord.Locale | str | None = 'en-US') -> str`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L16)

Return a generic account label when the user has chosen to hide their name.

### `def account_autocomplete_choices(accounts: list[Account], current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L29)

Format account-name matches for Discord's bounded autocomplete menu.

### `def view(*items: discord.ui.Item) -> discord.ui.View`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L40)

Create a persistent view containing the supplied Discord components.

### `def embed(message: str | None = None, *, colour: int = RED, title: str | None = None) -> discord.Embed`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L48)

Build a standard BotFragg embed with optional description, title, and colour.

### `def translated(interaction: discord.Interaction, key: str, **arguments: object) -> str`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L55)

Format one message using the caller's Discord locale.

### `def localized_embed(interaction: discord.Interaction, description_key: str | None = None, *, title_key: str | None = None, colour: int = DARK, description_args: dict[str, object] | None = None, title_args: dict[str, object] | None = None) -> discord.Embed`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L60)

Build an embed from catalog message IDs and the caller's locale.

### `async def error(interaction: discord.Interaction, message: str | Exception, **arguments: object) -> None`

**Scope:** `src/cogs/valorant/_ui.py` · `module`

[Source](../src/cogs/valorant/_ui.py#L81)

Send a private error embed using the interaction's available response path.

## `src/cogs/valorant/accounts.py`

Slash commands for selecting, listing, and paging through linked accounts.

### `class AccountsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L31)

Present a user's linked Riot accounts and handle account selection.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L34)

Bind the bot and register the persistent account-page action.

### `async def account_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L39)

Return up to 25 of the caller's accounts matching the typed name.

### `def _accounts_embed(accounts: list[Account], current_account_id: str | None, translator: BotFraggTranslator, locale: discord.Locale, page: int = 0) -> discord.Embed`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L48)

Render one bounded account page and mark the currently selected entry.

### `def _accounts_view(user_id: int, account_count: int, page: int) -> discord.ui.View | None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L84)

Build owner-scoped previous and next controls when multiple pages exist.

### `async def account(self, interaction: discord.Interaction, account: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L104)

Switch the caller's active account using an autocomplete selection.

### `async def accounts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L152)

Show the caller's accounts privately when their name-hiding preference is on.

### `async def accounts_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `AccountsCog`

[Source](../src/cogs/valorant/accounts.py#L176)

Handle a persistent account-page control and refresh its message.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/accounts.py` · `module`

[Source](../src/cogs/valorant/accounts.py#L203)

Register the linked-account commands and component handlers.

## `src/cogs/valorant/alerts.py`

Commands for creating, viewing, removing, and testing skin alerts.

### `class AlertsCog(commands.Cog)`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L27)

Manage owner-scoped alert records and their persistent Discord controls.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L30)

Bind the bot and register persistent alert-management actions.

### `async def skin_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L36)

Return catalog skin matches suitable for Discord's autocomplete limit.

### `async def alert(self, interaction: discord.Interaction, skin: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L52)

Create a skin alert for the caller's active account and show a remove control.

### `async def alerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L93)

Show the caller's paginated alerts and owner-bound management controls.

### `def _created_embed(self, skin: Skin, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L107)

Build the confirmation card for a newly created skin alert.

### `def _skin_display_name(self, skin: Skin | None, locale: discord.Locale) -> str`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L119)

Return a skin name prefixed with its tier emoji, if one exists.

### `def _skin_emoji(self, skin: Skin | None) -> str | None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L125)

Return a button emoji for a skin tier when one is available.

### `async def manager_view(self, user_id: int, page: int, locale: discord.Locale) -> tuple[discord.Embed, discord.ui.View | None]`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L131)

Render one alert page with per-alert removal and optional page controls.

### `async def remove_alert(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L195)

Remove the selected owner-scoped alert and refresh or dismiss its controls.

### `async def alert_page(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L234)

Validate a page payload and update the alert-management message.

### `async def testalerts(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `AlertsCog`

[Source](../src/cogs/valorant/alerts.py#L254)

Check login and shop availability, then send the caller a test alert DM.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/alerts.py` · `module`

[Source](../src/cogs/valorant/alerts.py#L323)

Register the skin-alert commands and their persistent handlers.

## `src/cogs/valorant/battlepass.py`

Commands and embed builders for VALORANT battlepass and mission progress.

### `class BattlepassCog(commands.Cog)`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L19)

Display the caller's current battlepass level and mission progress.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L22)

Bind the bot's gameplay, account, and emoji services.

### `async def battlepass(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L32)

Fetch and display the active battlepass for the caller's selected account.

### `async def missions(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L70)

Show the selected account's daily and weekly mission progress privately.

### `def _missions_card(missions: list[dict], filled_bar: str = '█', empty_bar: str = '░', *, translator: BotFraggTranslator, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L95)

Group mission entries by type and expiry and render progress bars.

### `def _battlepass_card(player: str, data: dict, filled_bar: str = '█', empty_bar: str = '░', *, emoji_service: ApplicationEmojiService | None = None, translator: BotFraggTranslator, locale: discord.Locale) -> discord.Embed`

**Scope:** `src/cogs/valorant/battlepass.py` · `BattlepassCog`

[Source](../src/cogs/valorant/battlepass.py#L182)

Render the active act, current tier, next reward, and XP progress bar.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/battlepass.py` · `module`

[Source](../src/cogs/valorant/battlepass.py#L242)

Register the battlepass and mission commands.

## `src/cogs/valorant/login.py`

Private Riot sign-in flow using an authorization link and callback modal.

### `class LoginModal(discord.ui.Modal)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L15)

Collect the redirect URL returned after a user signs in with Riot.

### `def __init__(self, bot: BotFraggBot, locale: discord.Locale) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L18)

Set a five-minute timeout and retain the authentication service owner.

### `async def on_submit(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginModal`

[Source](../src/cogs/valorant/login.py#L32)

Redeem the submitted callback and privately report the login result.

### `class LoginCog(commands.Cog)`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L60)

Start Riot sign-in and open the callback URL entry modal.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L63)

Bind the bot and register the persistent login-modal action.

### `async def login(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L75)

Start a nonce-bound Riot login when the caller has account capacity.

### `async def login_modal(self, interaction: discord.Interaction, _: str) -> None`

**Scope:** `src/cogs/valorant/login.py` · `LoginCog`

[Source](../src/cogs/valorant/login.py#L120)

Open the modal where the caller pastes Riot's redirect URL.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/login.py` · `module`

[Source](../src/cogs/valorant/login.py#L125)

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

[Source](../src/cogs/valorant/logout.py#L37)

Clear Riot credentials for one linked account while preserving its settings.

### `async def deletedata(self, interaction: discord.Interaction, confirm: bool) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `LogoutCog`

[Source](../src/cogs/valorant/logout.py#L63)

Permanently delete the caller's records and clear cached storefronts.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/logout.py` · `module`

[Source](../src/cogs/valorant/logout.py#L89)

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

### `def _penalties_page(owner_id: int, account: Account, player: str, penalties: list[dict], page: int, translator: BotFraggTranslator, locale: discord.Locale) -> tuple[discord.Embed, discord.ui.View | None]`

**Scope:** `src/cogs/valorant/penalties.py` · `module`

[Source](../src/cogs/valorant/penalties.py#L121)

Build one five-penalty embed page and owner-bound navigation controls.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/penalties.py` · `module`

[Source](../src/cogs/valorant/penalties.py#L237)

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

[Source](../src/cogs/valorant/settings.py#L84)

Present Yes/No options for the caller's selected preference.

### `async def setting_selected(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `SettingsCog`

[Source](../src/cogs/valorant/settings.py#L118)

Validate and persist a setting selection, then update its confirmation.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/settings.py` · `module`

[Source](../src/cogs/valorant/settings.py#L146)

Register the user preference commands and selection handler.

## `src/cogs/valorant/shop.py`

Commands for skin shops, featured bundles, and balances.

### `def _price_line(currency: str, final_price: int, original_price: int | None = None, discount_percent: int | None = None) -> str`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L45)

Format a current price and any original price discount on one line.

### `def offer_cards(header: str, offers: list[Offer], currency: str, *, link_item_image: bool, emoji_service: ApplicationEmojiService | None = None, header_colour: int = 2105893) -> list[discord.Embed]`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L61)

Render a heading and one tier-coloured embed for each skin offer.

### `def add_skin_selector(controls: discord.ui.View, owner_id: int, offers: list[Offer], expires: int, emoji_service: ApplicationEmojiService, translator: BotFraggTranslator, locale: discord.Locale) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L96)

Add a menu containing only the skin offers rendered beside it.

### `async def add_account_selector(controls: discord.ui.View, owner_id: int, mode: str, current: str, *, hide_ign: bool = False, translator: BotFraggTranslator, locale: discord.Locale) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L131)

Add a private account selector when the owner has multiple accounts.

### `class ShopCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L166)

Show shops and bundles for the caller's linked account.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L169)

Bind the bot and register persistent shop-mode and account actions.

### `async def shop(self, interaction: discord.Interaction, user: discord.User | None = None) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L184)

Show the caller's shop or a shop another user has chosen to share.

### `async def shop_view(self, data: ShopData, username: str, owner_id: int, puuid: str, *, hide_ign: bool = False, locale: discord.Locale) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L249)

Build daily shop embeds, owned selectors, and available shop controls.

### `async def bundles(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L331)

Show the selected account's current featured bundle offers and controls.

### `async def featured_bundles_view(self, data: ShopData, owner_id: int, puuid: str, *, locale: discord.Locale, selected_id: str | None = None, show_shop_button: bool = False) -> tuple[list[discord.Embed], discord.ui.View]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L348)

Build current featured bundles with shop-style cards and controls.

### `def _bundle_metadata(self, offer: FeaturedBundle, locale: discord.Locale) -> Bundle`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L430)

Resolve static bundle metadata or provide a safe live-offer fallback.

### `def _featured_price(self, offer: FeaturedBundle, vp: str, locale: discord.Locale) -> str`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L444)

Format only Riot-supplied VP totals, retaining exact discount values.

### `async def _featured_item_embed(self, item: FeaturedBundleItem, vp: str, locale: discord.Locale) -> discord.Embed | None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L458)

Render one live bundle item in the shop's card, tier, and price style.

### `async def _featured_bundle_embeds(self, offer: FeaturedBundle, locale: discord.Locale) -> list[discord.Embed]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L512)

Render a bundle summary and up to nine shop-style item cards.

### `async def shop_mode(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L572)

Render the selected daily, Night Market, accessory, or bundle mode.

### `def _selection_values(interaction: discord.Interaction, custom_id: str) -> set[str]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L712)

Read the values actually offered by this message's matching select menu.

### `async def shop_bundle(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L726)

Revalidate a selected featured bundle against the caller's account and view.

### `def _video_options(skin: Skin, translator: BotFraggTranslator, locale: discord.Locale) -> list[discord.SelectOption]`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L777)

List playable levels and chromas within Discord's select-menu limit.

### `async def shop_skin(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L806)

Open a private level/chroma menu for a skin offered in this message.

### `async def shop_variant(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L855)

Privately return a selected video only when it belongs to that skin.

### `async def shop_account(self, interaction: discord.Interaction, payload: str) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `ShopCog`

[Source](../src/cogs/valorant/shop.py#L912)

Validate the selected account and reopen the corresponding shop mode.

### `class NightMarketCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L928)

Display discounted Night Market offers for the selected Riot account.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L931)

Bind the shared shop, account, and emoji services.

### `async def nightmarket(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `NightMarketCog`

[Source](../src/cogs/valorant/shop.py#L942)

Fetch and render Night Market offers or report that none are active.

### `class BalanceCog(commands.Cog)`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L1005)

Display the selected account's three VALORANT wallet balances.

### `def __init__(self, bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L1008)

Bind the shared shop and user-preference services.

### `async def balance(self, interaction: discord.Interaction) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `BalanceCog`

[Source](../src/cogs/valorant/shop.py#L1019)

Fetch and display VP, Radianite, and Kingdom Credit balances.

### `async def setup(bot: BotFraggBot) -> None`

**Scope:** `src/cogs/valorant/shop.py` · `module`

[Source](../src/cogs/valorant/shop.py#L1068)

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

Create the initial user, account, alert, and suggestion tables.

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

Keep BotFragg logs and serious Discord errors after removing URL data.

### `def _release() -> str`

**Scope:** `src/monitoring.py` · `module`

[Source](../src/monitoring.py#L149)

Return the installed BotFragg release label or an unknown fallback.

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

[Source](../src/services/accounts.py#L32)

Return the stored BotFragg user for a Discord ID, if one exists.

### `async def count_registered_users() -> int`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L37)

Count users with a stored BotFragg profile.

### `async def daily_shop_user_ids() -> set[int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L42)

Return Discord IDs whose saved preference enables daily shop DMs.

### `async def account_for_user(discord_id: int, puuid: str) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L47)

Return a Riot account only when it belongs to the requested Discord user.

### `async def update_user_preference(discord_id: int, field: str, enabled: bool) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L52)

Update one allowlisted Boolean preference and refresh the user's timestamp.

### `async def selected_account(discord_id: int, *, user: User | None = None, accounts: Sequence[Account] | None = None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L62)

Return the active account, choosing the oldest account when none is selected.

A supplied user or account sequence avoids redundant queries; a supplied user
must belong to ``discord_id``. When choosing a default, the database update is
conditional so a concurrent selection is not overwritten.

### `async def list_accounts(discord_id: int) -> list[Account]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L118)

Return a user's Riot accounts in creation order.

### `async def resolve_account(discord_id: int, query: str | None) -> Account | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L123)

Resolve an account by PUUID, case-insensitive name, or one-based position.

### `async def select_account(discord_id: int, account: Account) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L139)

Set a user's active account after verifying that the account is theirs.

### `async def delete_user_data(discord_id: int) -> bool`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L148)

Delete the user's stored BotFragg records and all linked Riot accounts.

### `class AlertPage`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L165)

Hold one bounded page of alerts and its normalized pagination metadata.

### `async def create_alert(user_id: int, account: Account, skin_uuid: UUID) -> tuple[Alert, bool]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L175)

Create an account-scoped skin alert or return the existing duplicate.

### `async def list_alerts_page(user_id: int, page: int, page_size: int) -> AlertPage`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L184)

Fetch an owner-scoped alert page, wrapping page indexes and bounding size.

### `async def remove_alert(user_id: int, alert_id: int) -> Alert | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L206)

Delete and return an alert only when it belongs to the requesting user.

### `async def first_alert(user_id: int) -> Alert | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L214)

Return a user's first alert with its linked account loaded.

### `async def user_ids_with_alerts() -> set[int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L221)

Return distinct Discord IDs that own at least one alert.

### `async def account_ids_with_alerts(account_ids: list[str]) -> set[str]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L226)

Return only the supplied account IDs that currently have alerts.

### `async def matching_alerts_for_skins(account_id: str, skin_uuids: list[str]) -> list[Alert]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L237)

Fetch alerts matching one account and a bounded set of shop skin IDs.

### `async def run_daily_alerts(shop: ShopService, *, alert_concurrency: int, delay_between_alerts_seconds: float, dry_run: bool, on_shop: ShopOutcomeHandler, on_credentials_expired: CredentialsExpiredHandler) -> dict[str, int]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L255)

Check eligible accounts with bounded concurrency and report run totals.

``dry_run`` performs the lookups without sending notifications. The callbacks
handle successful shops and expired credentials; the returned counts include
users, fetched shops, matched alerts, and recoverable failures.

### `async def record_command_invocation(*, command: str, user_id: int, guild_id: int | None, channel_id: int | None) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L356)

Persist a successful command invocation with its optional Discord scope.

### `async def command_stats(*, user_id: int | None = None, guild_id: int | None = None) -> tuple[int, str | None]`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L372)

Return a scoped command-use count and the most-used command.

Exactly one of ``user_id`` or ``guild_id`` is required. Ties for the most-used
command are resolved alphabetically for stable results.

### `async def create_suggestion(author_id: int, content: str, log_channel_id: int | None) -> Suggestion`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L404)

Create a pending suggestion with its author and optional delivery channel.

### `async def record_suggestion_delivery(suggestion: Suggestion, message_id: int) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L413)

Record the posted message and ensure the author follows the suggestion.

### `async def delete_suggestion(suggestion_id: int) -> None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L422)

Delete a suggestion record by its database ID.

### `async def follow_suggestion(suggestion_id: int, user_id: int) -> bool | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L427)

Follow an existing suggestion, returning ``None`` when it does not exist.

### `async def unfollow_suggestion(suggestion_id: int, user_id: int) -> UnfollowResult`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L437)

Remove a follow and report missing, own, removed, or absent-follow status.

### `async def review_suggestion(suggestion_id: int, status: ReviewStatus, reason: str) -> tuple[Suggestion, set[int]] | None`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L450)

Atomically review a pending suggestion and return its followers once.

A suggestion that is missing or already reviewed returns ``None``; a successful
review returns the updated record and the distinct follower IDs to notify.

### `async def count_suggestions_by_author(author_id: int) -> int`

**Scope:** `src/services/accounts.py` · `module`

[Source](../src/services/accounts.py#L473)

Count suggestions submitted by a Discord user.

## `src/services/auth.py`

Riot OAuth callbacks, encrypted credentials, and refreshable auth headers.

### `class AuthResult`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L29)

Represent an authentication outcome with legacy and translated error data.

### `class AuthService`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L39)

Manage Riot login, token refresh, entitlement repair, and account linking.

### `def __init__(self, config: Settings, http: HTTPClient, vault: AuthVault) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L42)

Bind validated settings, the shared HTTP client, and token vault.

### `async def refresh_version(self) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L52)

Fetch Riot's current client version for authenticated request headers.

### `def riot_headers(self) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L59)

Return the platform and current client-version headers expected by Riot.

### `def login_url(self, discord_id: int) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L69)

Create a Riot authorization URL and retain a short-lived per-user nonce.

### `async def redeem_callback(self, discord_id: int, callback_url: str) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L83)

Exchange a callback code, verify its nonce, and securely link the account.

The callback nonce is single-use and expires after ten minutes. A Riot account
already owned by another Discord user, or a user at the account limit, is
rejected without replacing the existing owner.

### `async def ensure(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L224)

Serialize credential checks for an account and return its usable auth state.

### `async def _ensure_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L232)

Check token lifetime and repair or refresh credentials while holding its lock.

### `async def refresh(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L250)

Refresh one account's Riot tokens under its per-account lock.

### `async def _refresh_locked(self, account: Account, *, force: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L258)

Refresh tokens with version-checked persistence to protect concurrent updates.

### `async def clear_credentials(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L326)

Remove the selected account's Riot tokens while coordinating with refreshes.

### `async def _clear_credentials_locked(self, account: Account) -> None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L333)

Clear credentials only if the stored auth version still matches the caller.

### `async def auth_headers(self, account: Account) -> dict[str, str]`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L339)

Return fresh Riot authorization headers or raise when login is required.

### `async def _repair_entitlement(self, account: Account, auth: dict[str, Any], *, refresh_on_missing: bool = False) -> AuthResult`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L358)

Fetch and persist an entitlement token, optionally refreshing on absence.

### `async def _user_info(self, auth: dict[str, Any]) -> dict[str, str] | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L389)

Fetch the Riot game name and tag line associated with an access token.

### `async def _entitlement(self, auth: dict[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L403)

Request an entitlement token and surface transient Riot failures.

### `async def _region(self, auth: dict[str, Any]) -> str | None`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L421)

Resolve the VALORANT shard affinity associated with an ID token.

### `def _user_agent(self) -> str`

**Scope:** `src/services/auth.py` · `AuthService`

[Source](../src/services/auth.py#L436)

Build the Riot authentication user agent from the latest client build.

### `def decode_jwt(token: str | None) -> dict[str, Any]`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L446)

Decode a JWT payload for claim lookup without performing signature validation.

### `def token_expiry(token: str | None) -> float`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L459)

Return the token's Unix expiry time, or zero when it cannot be decoded.

### `def riot_region(region: str | None) -> str`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L467)

Map missing and LATAM/Brazil affinities to Riot's North America API host.

### `class AuthenticationRequired(RuntimeError)`

**Scope:** `src/services/auth.py` · `module`

[Source](../src/services/auth.py#L472)

Raised when a Riot request cannot proceed without a new user login.

## `src/services/catalog.py`

VALORANT skin, bundle, accessory, and mission metadata with a local cache.

### `class Skin`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L28)

Hold normalized skin identity, display data, pricing, levels, and chromas.

### `class Bundle`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L42)

Hold static display metadata for a VALORANT bundle.

### `class Accessory`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L53)

Hold normalized display data for a non-skin cosmetic reward.

### `class CatalogService`

**Scope:** `src/services/catalog.py` · `module`

[Source](../src/services/catalog.py#L61)

Load, refresh, search, and cache VALORANT catalog data.

### `def __init__(self, http: HTTPClient) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L64)

Prepare in-memory indexes and the working-directory catalog snapshot.

### `async def load(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L85)

Load the saved catalog off the event loop or fetch a fresh snapshot.

### `async def refresh(self, *, check_version: bool = False) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L97)

Fetch the current weapon and bundle catalogs and save their snapshot.

When ``check_version`` is true, skip rebuilding only if the upstream version
and local cache format are current.

### `async def _fetch_data(self, kind: str) -> list[dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L163)

Fetch one catalog endpoint and return its validated data rows.

### `async def mission_metadata(self) -> dict[str, dict[str, Any]]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L175)

Return cached mission definitions, refreshing them at most every 30 minutes.

### `def _build(self, weapons: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L221)

Normalize weapon and bundle responses and rebuild lookup indexes.

### `def _reindex(self) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L262)

Index skins by their UUID, offer UUID, and level UUID aliases.

### `def get_skin(self, uuid: str) -> Skin | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L273)

Resolve a skin from any indexed base, offer, or level identifier.

### `def get_bundle(self, uuid: str) -> Bundle | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L277)

Resolve bundle metadata by its Riot UUID.

### `async def accessory(self, item_type: str, uuid: str) -> Accessory | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L282)

Fetch and cache a supported accessory using its Riot item type ID.

### `async def _buddy_accessory(self, uuid: str) -> Accessory | None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L316)

Resolve a Riot bundle buddy by its buddy or level UUID.

### `def _accessory_from_data(endpoint: str, raw: dict[str, Any]) -> Accessory`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L354)

Convert endpoint-specific Riot accessory data into a common display shape.

### `def search_skins(self, query: str, *, limit: int = 25) -> list[Skin]`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L372)

Return fuzzy name matches whose weighted score is at least 35.

### `def update_prices(self, offers: list[dict[str, Any]]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L382)

Apply current store prices to catalog skins matched by offer identifier.

### `def _serialize(self) -> str`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L393)

Encode the current version, skins, and bundles as compact JSON.

### `def _save(self, snapshot: str) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L424)

Write a complete catalog snapshot through a temporary file replacement.

### `def _deserialize(self, raw: dict[str, Any]) -> None`

**Scope:** `src/services/catalog.py` · `CatalogService`

[Source](../src/services/catalog.py#L431)

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

### `class GameplayService`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L15)

Riot gameplay APIs used by battlepass, mission, and penalty commands.

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

### `async def penalties(self, account: Account) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L127)

Fetch and normalize an account's current Riot matchmaking penalties.

### `def _mission_progress(row: Any, definitions: dict[str, dict[str, Any]]) -> dict[str, Any] | None`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L230)

Normalize one Riot mission row and its objective progress for display.

### `async def _reward(self, levels: list[dict[str, Any]], level: int) -> dict[str, Any]`

**Scope:** `src/services/gameplay.py` · `GameplayService`

[Source](../src/services/gameplay.py#L309)

Resolve the next battlepass reward to display data, including its icon.

### `def _api_data(value: Any) -> list[dict[str, Any]]`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L349)

Return a validated API response's data list or an empty list.

### `class GameplayUnavailable(RuntimeError)`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L358)

Riot did not return usable gameplay data.

### `def _nonnegative_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L362)

Convert a non-Boolean value to a nonnegative integer when possible.

### `def _positive_int(value: Any) -> int | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L373)

Convert a value to a positive integer or return ``None``.

### `def _parse_datetime(value: Any) -> datetime | None`

**Scope:** `src/services/gameplay.py` · `module`

[Source](../src/services/gameplay.py#L378)

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

Hold an HTTP response status and decoded body.

### `class HTTPClient`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L46)

Own a reusable aiohttp session and normalize transport failures.

### `def __init__(self, config: Settings) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L49)

Store request settings and initialize session and rate-limit state.

### `async def start(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L55)

Create the shared aiohttp session with configured timeout and pool limits.

### `async def close(self) -> None`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L61)

Close the shared session when it has been started and remains open.

### `async def request(self, method: str, url: str, *, headers: dict[str, str] | None = None, json: Any = None, data: Any = None) -> HTTPResult`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L66)

Send a request, decode its body, and apply per-host rate-limit backoff.


**Raises**
- **`RuntimeError`** — If the client has not been started.
- **`HTTPFailure`** — If the request is rate-limited, times out, or fails at the
  transport layer.

### `def _retry_after(self, value: str | None) -> int`

**Scope:** `src/services/http.py` · `HTTPClient`

[Source](../src/services/http.py#L112)

Parse and clamp a Retry-After value to the configured backoff limit.

### `class HTTPFailure(RuntimeError)`

**Scope:** `src/services/http.py` · `module`

[Source](../src/services/http.py#L121)

Raised for rate limits, transport failures, and bounded request timeouts.

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

[Source](../src/services/shop.py#L104)

Remove an account's cached storefront after coordinating with active fetches.

### `async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L109)

Return a fresh or unexpired cached storefront for the linked account.

### `async def _fetch_storefront(self, account: Account, headers: dict[str, str]) -> ShopData`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L128)

Fetch, repair claims, normalize all shop offers, and cache the result.

### `async def _storefront_request(self, account: Account, headers: dict[str, str]) -> HTTPResult`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L272)

Request one account's regional storefront.

### `async def wallet(self, account: Account) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L283)

Return VP, Radianite, and Kingdom Credit balances for an account.

### `async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L303)

Resolve the storefront's accessory rewards and their Kingdom Credit prices.

### `def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L319)

Extract the raw single-item store offers across Riot response shapes.

### `def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]`

**Scope:** `src/services/shop.py` · `ShopService`

[Source](../src/services/shop.py#L326)

Build a skin-offer-to-VP-price lookup from the storefront payload.

### `class ShopUnavailable(RuntimeError)`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L342)

Raised when Riot does not return a usable storefront or wallet.

### `def _int_at_least(value: Any, minimum: int) -> int | None`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L346)

Parse an integer only when it meets the requested minimum.

### `def _vp_price(value: Any, currency_uuid: str) -> int | None`

**Scope:** `src/services/shop.py` · `module`

[Source](../src/services/shop.py#L355)

Return a price only when the source entry explicitly uses VALORANT Points.

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

[Source](../src/views/components.py#L82)

Dispatch the button action to its registered handler inside a trace.

### `class OwnedSelect(discord.ui.DynamicItem[discord.ui.Select])`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L99)

Create a persistent select menu whose action is restricted to its owner.

### `def __init__(self, action: str, owner_id: int, payload: str = '', *, placeholder: str | None = None, options: list[discord.SelectOption] | None = None) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L102)

Build a stable custom ID and provide a safe placeholder option if empty.

### `async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item[Any], match: re.Match[str]) -> OwnedSelect`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L125)

Reconstruct a persistent select menu from its ID and current options.

### `async def interaction_check(self, interaction: discord.Interaction) -> bool`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L141)

Reject interactions from users other than the menu's recorded owner.

### `async def callback(self, interaction: discord.Interaction) -> None`

**Scope:** `src/views/components.py` · `OwnedSelect`

[Source](../src/views/components.py#L155)

Dispatch the selected value with the menu payload to its registered handler.

### `def _error_embed(message: str) -> discord.Embed`

**Scope:** `src/views/components.py` · `module`

[Source](../src/views/components.py#L173)

Build a compact red embed for an invalid or unavailable component action.
