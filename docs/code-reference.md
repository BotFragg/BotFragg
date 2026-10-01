# Repository code reference

This guide describes every tracked project file and how the application is
organized. The [API reference](api-reference.md) lists every Python module,
class, function, and method with its signature, source link, and source
docstring. Regenerate it after code documentation changes with
`uv run --frozen python tools/generate_api_reference.py`.

## Runtime flow

1. `main.py` starts `src.main.main`, which loads settings, configures logging
   and optional GlitchTip reporting, and runs `BotFraggBot`.
2. `BotFraggBot.setup_hook` initializes the database and Riot HTTP client,
   warms the catalog and application emojis, registers persistent controls,
   and loads the Discord cogs.
3. Cogs translate Discord commands and events into calls to `src.services`.
   Services own Riot requests, account and suggestion operations, and catalog
   normalization, including static bundle metadata and account-scoped featured
   offers; `src.models.entities` defines the persisted records.
4. Background task cogs schedule daily alerts and periodic refreshes. Monitoring
   helpers remove sensitive fields before logs and events leave the process.

## Repository and development files

| File | Purpose |
| --- | --- |
| [.dockerignore](../.dockerignore) | Excludes secrets, runtime data, tests, and local caches from Docker build context. |
| [.env.example](../.env.example) | Lists supported environment settings with safe example values. |
| [CI workflow](../.github/workflows/ci.yml) | Checks API-reference freshness, runs pytest and Ruff, and compiles Python modules. |
| [.gitignore](../.gitignore) | Excludes local configuration, data, build products, and test caches from Git. |
| [Pre-commit configuration](../.pre-commit-config.yaml) | Runs the same Ruff and pytest checks before commits. |
| [.python-version](../.python-version) | Selects the Python version used by uv and local tooling. |
| [CHANGELOG.md](../CHANGELOG.md) | Records user-visible release changes. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Documents the development environment and required checks. |
| [docs/api-reference.md](api-reference.md) | Lists all Python modules, classes, and callables with their signatures, source links, and docstrings. |
| [docs/code-reference.md](code-reference.md) | Maps tracked files and summarizes how runtime components work together. |
| [Dockerfile](../Dockerfile) | Builds the Python 3.14 BotFragg image and runs it as an unprivileged user. |
| [LICENSE](../LICENSE) | Contains the GNU GPLv3 license text. |
| [PRIVACY.md](../PRIVACY.md) | Describes BotFragg's data processing, retention, and user controls. |
| [README.md](../README.md) | Covers setup, commands, configuration, deployment, and privacy. |
| [SECURITY.md](../SECURITY.md) | Explains how to report a vulnerability and respond to exposed credentials. |
| [docker-compose.yml](../docker-compose.yml) | Defines the local production-style BotFragg service and persistent data volume. |
| [main.py](../main.py) | Invokes the application entry point for `python main.py` startup. |
| [pyproject.toml](../pyproject.toml) | Defines package metadata, dependencies, entry point, Ruff rules, and test settings. |
| [tools/generate_api_reference.py](../tools/generate_api_reference.py) | Generates the exhaustive API reference from Python source docstrings and signatures. |
| [uv.lock](../uv.lock) | Pins the resolved dependency graph for reproducible installs. |

## Packaged assets

| File | Purpose |
| --- | --- |
| [assets/ebar.png](../assets/ebar.png) | Empty progress-bar emoji used for battlepass and mission progress. |
| [assets/fbar.png](../assets/fbar.png) | Filled progress-bar emoji used for battlepass and mission progress. |
| [assets/kc.png](../assets/kc.png) | Kingdom Credits currency emoji source. |
| [assets/rad.png](../assets/rad.png) | Radianite Points currency emoji source. |
| [assets/vp.png](../assets/vp.png) | VALORANT Points currency emoji source. |

## Application modules

| File | Responsibility |
| --- | --- |
| [src/__init__.py](../src/__init__.py) | Defines the application package. |
| [src/bot.py](../src/bot.py) | Constructs the sharded Discord client, wires services, loads extensions, and handles command errors. |
| [src/config.py](../src/config.py) | Loads environment-backed settings and validates secrets, URLs, IDs, times, and numeric limits. |
| [src/database.py](../src/database.py) | Configures Tortoise ORM and provides database health and shard-status persistence helpers. |
| [src/main.py](../src/main.py) | Configures process logging and monitoring before starting the Discord client. |
| [src/monitoring.py](../src/monitoring.py) | Formats structured logs and strips sensitive data from log and GlitchTip events. |
| [src/cogs/__init__.py](../src/cogs/__init__.py) | Defines the Discord cog package. |
| [src/cogs/events.py](../src/cogs/events.py) | Records command analytics and reports guild and shard lifecycle events. |
| [src/cogs/extra.py](../src/cogs/extra.py) | Implements utility commands, suggestion workflows, and persistent shard status. |
| [src/cogs/staff.py](../src/cogs/staff.py) | Implements owner-only user, server, and command-usage diagnostics. |
| [src/cogs/tasks.py](../src/cogs/tasks.py) | Runs scheduled alerts and refreshes and optionally forwards filtered logs to Discord. |
| [src/cogs/valorant/__init__.py](../src/cogs/valorant/__init__.py) | Defines the VALORANT cog package. |
| [src/cogs/valorant/_ui.py](../src/cogs/valorant/_ui.py) | Shares embed, view, error, and privacy-aware account-name helpers. |
| [src/cogs/valorant/accounts.py](../src/cogs/valorant/accounts.py) | Implements account switching, listing, and pagination commands. |
| [src/cogs/valorant/alerts.py](../src/cogs/valorant/alerts.py) | Implements user-owned skin alerts and alert-management controls. |
| [src/cogs/valorant/battlepass.py](../src/cogs/valorant/battlepass.py) | Displays battlepass and mission progress using Riot gameplay data. |
| [src/cogs/valorant/login.py](../src/cogs/valorant/login.py) | Handles nonce-bound Riot sign-in through a private Discord modal. |
| [src/cogs/valorant/logout.py](../src/cogs/valorant/logout.py) | Clears Riot credentials or deletes the caller's stored data. |
| [src/cogs/valorant/settings.py](../src/cogs/valorant/settings.py) | Displays and updates user privacy and notification preferences. |
| [src/cogs/valorant/shop.py](../src/cogs/valorant/shop.py) | Displays daily and accessory shops, featured bundles, Night Markets, and wallet balances. |
| [src/migrations/__init__.py](../src/migrations/__init__.py) | Exposes the Tortoise migration package. |
| [src/migrations/0001_initial.py](../src/migrations/0001_initial.py) | Creates the initial user, account, alert, and suggestion schema. |
| [src/migrations/0002_add_command_analytics.py](../src/migrations/0002_add_command_analytics.py) | Adds command invocation analytics. |
| [src/migrations/0003_add_suggestions.py](../src/migrations/0003_add_suggestions.py) | Adds suggestions and unique follower records. |
| [src/migrations/0004_add_shard_status_message.py](../src/migrations/0004_add_shard_status_message.py) | Adds persistent shard-status message references. |
| [src/models/__init__.py](../src/models/__init__.py) | Re-exports model classes for application code. |
| [src/models/entities.py](../src/models/entities.py) | Defines ORM records and uniqueness constraints. |
| [src/services/__init__.py](../src/services/__init__.py) | Defines the service package. |
| [src/services/accounts.py](../src/services/accounts.py) | Owns user preferences, account selection, alerts, analytics, and suggestion persistence. |
| [src/services/auth.py](../src/services/auth.py) | Owns Riot OAuth, credential refresh, entitlement repair, and account linking. |
| [src/services/catalog.py](../src/services/catalog.py) | Loads, searches, refreshes, and caches skin, bundle, accessory, and mission metadata. |
| [src/services/crypto.py](../src/services/crypto.py) | Encrypts and decrypts stored Riot credentials with Fernet. |
| [src/services/emojis.py](../src/services/emojis.py) | Caches application emojis and creates missing ones from packaged assets. |
| [src/services/gameplay.py](../src/services/gameplay.py) | Normalizes VALORANT battlepass and mission progress. |
| [src/services/http.py](../src/services/http.py) | Provides shared Riot HTTP requests, URL redaction, and rate-limit handling. |
| [src/services/shop.py](../src/services/shop.py) | Retrieves and normalizes account-scoped skin, bundle, accessory, Night Market, and wallet data. |
| [src/views/__init__.py](../src/views/__init__.py) | Re-exports common timestamps and persistent interactive controls. |
| [src/views/common.py](../src/views/common.py) | Formats values as Discord timestamps. |
| [src/views/components.py](../src/views/components.py) | Implements restart-safe, owner-restricted buttons and select menus. |

## Tests

| File | Coverage |
| --- | --- |
| [tests/conftest.py](../tests/conftest.py) | Shared asynchronous database setup and teardown. |
| [tests/test_alert_pagination.py](../tests/test_alert_pagination.py) | Alert ordering, page wrapping, and records removed during pagination. |
| [tests/test_alerts_service.py](../tests/test_alerts_service.py) | Alert ownership, bounded queries, batching, delivery order, and failure handling. |
| [tests/test_analytics.py](../tests/test_analytics.py) | Command analytics scope, DM context, tie-breaking, and empty results. |
| [tests/test_config_crypto_monitoring.py](../tests/test_config_crypto_monitoring.py) | Configuration validation, credential encryption, and privacy scrubbing. |
| [tests/test_migration.py](../tests/test_migration.py) | Migration/model parity and database initialization behavior. |
| [tests/test_models_services.py](../tests/test_models_services.py) | Data invariants, concurrency, authentication, catalog, shop, and gameplay services. |
| [tests/test_shard_status_service.py](../tests/test_shard_status_service.py) | Reuse and replacement of saved shard-status messages. |
| [tests/test_suggestions_service.py](../tests/test_suggestions_service.py) | Suggestion delivery, follower uniqueness, and review outcomes. |
| [tests/test_views_commands.py](../tests/test_views_commands.py) | Command output, component ownership, privacy, and cog shutdown behavior. |
