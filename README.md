# Botfragg

Botfragg is a privacy-conscious VALORANT companion for Discord. Link a Riot
account to view the daily shop, Night Market, balances, battlepass progress,
and receive direct-message skin alerts.

Botfragg is written in Python 3.14 with discord.py, Tortoise ORM, and uv. It uses
SQLite for local development and PostgreSQL in production.

## Features

- Riot account login with encrypted credentials and multi-account switching.
- Daily shop, accessory shop, Night Market, balances, and battlepass progress.
- DM-only daily-shop delivery and skin alerts.
- Per-user privacy controls for in-game names and shop sharing.
- Persistent interactive controls, restart-safe alert removal, and application
  emoji fallbacks.
- Command analytics, staff tools, guild/shard lifecycle logging,
  suggestions, and GlitchTip observability.

## Commands

| Area | Commands |
| --- | --- |
| Account | `/login`, `/logout`, `/deletedata`, `/account`, `/accounts` |
| VALORANT | `/shop`, `/nightmarket`, `/balance`, `/battlepass` |
| Alerts | `/alert`, `/alerts`, `/testalerts` |
| Settings | `/settings view`, `/settings set` |
| Community | `/ping`, `/botinfo`, `/links`, `/suggest`, `/suggestion` |

`/userinfo` and `/serverinfo` are owner-only operational commands.

## Requirements

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- A Discord application and bot token
- A Fernet key for credential encryption
- PostgreSQL 18 for the bundled production deployment

## Discord application setup

Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications),
then copy the bot token into `.env`. In **OAuth2 → URL Generator**, select the
`bot` and `applications.commands` scopes. Grant **View Channels**, **Send
Messages**, **Embed Links**, and **Read Message History**, then use the generated
URL to invite Botfragg to a server. Administrator access is not required.

The bot enables the non-privileged Guilds, Guild Messages, and Direct Messages
intents in code. The slash-command setup does not require privileged intents.

## Local development

1. Copy `.env.example` to `.env`.
2. Set `DISCORD_TOKEN` and generate `TOKEN_ENCRYPTION_KEY`:

   ```powershell
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Install the locked development environment:

   ```powershell
   uv sync --all-groups --frozen
   ```

4. Apply migrations, then start the bot:

   ```powershell
   uv run tortoise -c src.database.TORTOISE_CONFIG migrate
   uv run botfragg
   ```

SQLite is selected automatically when `APP_ENV=development` and no
`DATABASE_URL` is provided. Botfragg creates its development schema on startup;
running the migration command keeps local environments aligned with production.

## Production

1. Set `APP_ENV=production`, `DISCORD_TOKEN`, `TOKEN_ENCRYPTION_KEY`, and a
   strong `POSTGRES_PASSWORD` in `.env`.
2. Start PostgreSQL and Botfragg:

   ```sh
   docker compose up -d --build
   ```

The Compose deployment waits for PostgreSQL health checks, applies native
Tortoise migrations, and then starts the bot. Do not share or commit `.env`.

## Configuration

See `.env.example` for every supported setting. The essential values are:

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Discord bot token. |
| `TOKEN_ENCRYPTION_KEY` | Fernet key used to encrypt Riot credential payloads. |
| `APP_ENV` | `development`, `test`, or `production`. |
| `DATABASE_URL` | Required in production; otherwise SQLite is used locally. |
| `ALERT_TIME_UTC` | UTC time for the daily DM alert job. |
| `GLITCHTIP_DSN` | Optional self-hosted GlitchTip endpoint. |

Set `GLITCHTIP_TRACES_SAMPLE_RATE` and `GLITCHTIP_PROFILES_SAMPLE_RATE` above
their default `0.1` only when full telemetry capture is needed.

## Privacy and observability

Read [PRIVACY.md](PRIVACY.md) before operating or using Botfragg. Users can delete
their Botfragg data with `/deletedata confirm:True`; `/logout` removes credentials
only and retains account settings and alerts.

Optional GlitchTip reporting filters credentials, tokens, cookies, HTTP
request data, local variables, command inputs, message content, Riot account
identifiers, and Discord IDs before events are sent. Botfragg does not read or
retain DM content or attachments.

## Code reference

The [API reference](docs/api-reference.md) lists every Python module, class,
function, and method with its signature, source link, and docstring. The
[repository file guide](docs/code-reference.md) describes every tracked file and
summarizes the runtime flow.

## Contributing and security

Read the [repository file guide](docs/code-reference.md) for the package layout
and [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report
vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Botfragg is licensed under the [GNU GPLv3](LICENSE).
