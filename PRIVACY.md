# Privacy Policy

**Last updated:** October 8, 2026

This policy describes data handled by BotFragg when you use its Discord bot
features. BotFragg is an independent project and is not affiliated with Riot
Games. Data is stored by the operator of the BotFragg instance you use, so
hosting, database access, and retention settings depend on that operator.

## Data BotFragg processes

BotFragg processes the following information to provide its features:

- **Discord identifiers:** your Discord user ID, and where relevant guild and
  channel IDs. These associate a Discord user with their BotFragg records and
  support command analytics and configured operational logs.
- **Riot account information:** Riot PUUID, in-game name and tag, region, and
  the encrypted session credential payload needed to retrieve account data.
- **Preferences and account state:** selected account, daily shop DM setting,
  in-game-name visibility setting, shop-sharing setting, and account timestamps.
- **Alerts:** the skin identifier and creation time for each alert.
- **Command analytics:** command name, Discord user ID, guild ID and channel
  ID when available, and the time the command ran. Command option values are
  not included in these analytics records.
- **Suggestions:** submitted text, author ID, review status and reason, delivery
  channel and message IDs, and IDs of users following the suggestion.
- **Operational records:** where configured, BotFragg stores the channel and
  message IDs of its shard-status message. Optional Discord logs may include
  guild or shard information described below.

BotFragg processes slash-command interactions and the values you submit to
those commands, plus any configured operator prefix commands addressed to the
bot. It does not request Discord's privileged Message Content intent or store
ordinary conversation messages. A suggestion is an exception by design: its
text is stored and posted to the configured suggestion channel.

## Riot sign-in and VALORANT data

When you use `/login`, sign-in takes place on Riot's website. BotFragg does not
ask you to type your Riot password into Discord. You return a Riot redirect
URL through an ephemeral Discord form; BotFragg processes its authorization
code, exchanges it with Riot, and stores the resulting session credentials
encrypted with the operator's Fernet `TOKEN_ENCRYPTION_KEY`.

BotFragg sends the necessary Riot session credentials and account identifiers
to Riot authentication and VALORANT endpoints to retrieve your store, wallet,
mission, and battlepass information. It also requests public game catalog and
version data from [VALORANT-API.com](https://valorant-api.com/). Those external
services handle requests under their own terms and privacy practices.

## Discord messages and optional integrations

BotFragg sends command responses and alert DMs through Discord. If suggestion
delivery is configured, a suggestion is posted to the configured channel with
the submitting Discord user's display name and avatar, the suggestion text,
and the server name. BotFragg may edit that message when the suggestion is
reviewed. People who can access the channel can see its messages.

Operators may enable additional destinations:

- **Guild join and leave logs** can include the server name and ID, owner ID,
  creation time, member count, text and voice channel counts, server icon, and
  BotFragg's current server count.
- **Shard webhooks** include the shard ID, connection state, and shard count.
- **Application log channels** receive structured logs after BotFragg filters
  credential fields and common Riot or Discord identifiers.
- **GlitchTip** may receive error reports and logs when the operator configures
  a DSN; traces and profiles use the configured sampling rates. BotFragg
  disables default PII and local variable capture, removes request data,
  filters sensitive values, and strips HTTP span details before sending
  telemetry. The GlitchTip operator controls access and retention for that
  instance.

Discord and any configured monitoring or logging service apply their own
policies and retention controls to information they receive.

## Storage, retention, and deletion

The operator stores BotFragg records in the configured SQLite or PostgreSQL
database. BotFragg does not automatically expire account, alert, analytics,
or suggestion records.

- `/logout` removes stored Riot credentials for an account. It keeps the linked
  account record, alerts, and preferences.
- `/deletedata confirm:True` deletes your linked accounts and encrypted
  credentials, alerts, preferences, command analytics, suggestions, and
  suggestion follows from BotFragg's database.

Deleting data from BotFragg does not delete suggestion messages already sent
to Discord, messages in configured logging channels, or telemetry already
received by Discord or GlitchTip. Those copies follow the relevant service's
retention and deletion controls. Operator-managed backups may also retain
records until those backups expire.

## Your choices and privacy requests

Use `/settings` to control daily shop DMs, in-game-name visibility, and whether
other users may view your shop. Use `/logout` to remove account credentials or
`/deletedata confirm:True` to remove your BotFragg records. For a privacy
question or a request about data that the commands do not remove, contact the
team through the [BotFragg support server](https://discord.gg/VjZ5N8nT4K).

## Security

Riot session credentials are encrypted at rest using the operator's Fernet
key. Operators should restrict access to the database, encryption key,
backups, log destinations, and monitoring service. BotFragg's logging filters
reduce exposure of sensitive values, but users should never submit passwords,
verification codes, recovery codes, or session tokens in support posts.

## Changes to this policy

This policy may be updated when BotFragg's data handling changes. The current
version is maintained in this repository.
