# Repository code reference

This guide describes key project files and how the application is
organized. The [API reference](api-reference.md) lists every application Python
module, class, function, and method with its signature, source link, and source
docstring. Regenerate it after application documentation changes with
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
| [CI workflow](../.github/workflows/ci.yml) | Requires PostgreSQL tests, Mypy, Ruff, locales, API-reference freshness, and Python compilation before image builds. |
| [.gitignore](../.gitignore) | Excludes local configuration, data, build products, and test caches from Git. |
| [Pre-commit configuration](../.pre-commit-config.yaml) | Runs the same Ruff and pytest checks before commits. |
| [.python-version](../.python-version) | Selects the Python version used by uv and local tooling. |
| [CHANGELOG.md](../CHANGELOG.md) | Records user-visible release changes. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Documents the development environment and required checks. |
| [docs/api-reference.md](api-reference.md) | Lists application modules, classes, and callables with their signatures, source links, and docstrings. |
| [docs/code-reference.md](code-reference.md) | Maps tracked files and summarizes how runtime components work together. |
| [docs/operations.md](operations.md) | Documents health evidence, outage response, backup/restore verification, and measured database workloads. |
| [Dockerfile](../Dockerfile) | Builds the Python 3.14 BotFragg image and runs it as an unprivileged user. |
| [LICENSE](../LICENSE) | Contains the GNU GPLv3 license text. |
| [PRIVACY.md](../PRIVACY.md) | Describes BotFragg's data processing, retention, and user controls. |
| [README.md](../README.md) | Covers setup, commands, configuration, deployment, and privacy. |
| [SECURITY.md](../SECURITY.md) | Explains how to report a vulnerability and respond to exposed credentials. |
| [docker-compose.yml](../docker-compose.yml) | Defines the local production-style BotFragg service and persistent data volume. |
| [main.py](../main.py) | Invokes the application entry point for `python main.py` startup. |
| [pyproject.toml](../pyproject.toml) | Defines package metadata, dependencies, entry point, Mypy, Ruff, and test settings. |
| [tools/benchmark_database.py](../tools/benchmark_database.py) | Measures synthetic alert and analytics queries in a disposable PostgreSQL schema. |
| [tools/verify_restore.py](../tools/verify_restore.py) | Checks restored model counts, migration history, and encrypted credentials using a read-only transaction. |
| [tools/generate_api_reference.py](../tools/generate_api_reference.py) | Generates the application API reference from source docstrings and signatures. |
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
| [src/health.py](../src/health.py) | Tracks job completion/failures and provides the local container health probe. |
| [src/localization.py](../src/localization.py) | Loads Fluent catalogs and translates command metadata and response text with English fallback. |
| [src/main.py](../src/main.py) | Configures process logging and monitoring before starting the Discord client. |
| [src/monitoring.py](../src/monitoring.py) | Formats structured logs and strips sensitive data from log and GlitchTip events. |
| [src/cogs/__init__.py](../src/cogs/__init__.py) | Defines the Discord cog package. |
| [src/cogs/events.py](../src/cogs/events.py) | Records command analytics and reports guild and shard lifecycle events. |
| [src/cogs/extra.py](../src/cogs/extra.py) | Implements utility commands and persistent shard status. |
| [src/cogs/suggestions.py](../src/cogs/suggestions.py) | Implements suggestion submission, following, and owner-only review. |
| [src/cogs/staff.py](../src/cogs/staff.py) | Implements owner-only user, server, and command-usage diagnostics. |
| [src/cogs/tasks.py](../src/cogs/tasks.py) | Runs scheduled alerts and refreshes and optionally forwards filtered logs to Discord. |
| [src/cogs/valorant/__init__.py](../src/cogs/valorant/__init__.py) | Defines the VALORANT cog package. |
| [src/cogs/valorant/accounts.py](../src/cogs/valorant/accounts.py) | Implements account switching, listing, and pagination commands. |
| [src/cogs/valorant/alerts.py](../src/cogs/valorant/alerts.py) | Implements user-owned skin alerts and alert-management controls. |
| [src/cogs/valorant/battlepass.py](../src/cogs/valorant/battlepass.py) | Displays battlepass and mission progress using Riot gameplay data. |
| [src/cogs/valorant/login.py](../src/cogs/valorant/login.py) | Handles nonce-bound Riot sign-in through a private Discord modal. |
| [src/cogs/valorant/logout.py](../src/cogs/valorant/logout.py) | Clears Riot credentials or deletes the caller's stored data. |
| [src/cogs/valorant/penalties.py](../src/cogs/valorant/penalties.py) | Displays paginated private matchmaking-penalty summaries for the selected Riot account. |
| [src/cogs/valorant/settings.py](../src/cogs/valorant/settings.py) | Displays and updates user privacy and notification preferences. |
| [src/cogs/valorant/shop.py](../src/cogs/valorant/shop.py) | Displays daily and accessory shops, featured bundles, Night Markets, and wallet balances. |
| [src/migrations/__init__.py](../src/migrations/__init__.py) | Exposes the Tortoise migration package. |
| [src/migrations/0001_initial.py](../src/migrations/0001_initial.py) | Creates the initial user, account, and alert schema. |
| [src/migrations/0002_add_command_analytics.py](../src/migrations/0002_add_command_analytics.py) | Adds command invocation analytics. |
| [src/migrations/0003_add_suggestions.py](../src/migrations/0003_add_suggestions.py) | Adds suggestions and unique follower records. |
| [src/migrations/0004_add_shard_status_message.py](../src/migrations/0004_add_shard_status_message.py) | Adds persistent shard-status message references. |
| [src/models/__init__.py](../src/models/__init__.py) | Re-exports model classes for application code. |
| [src/models/entities.py](../src/models/entities.py) | Defines ORM records and uniqueness constraints. |
| [src/services/__init__.py](../src/services/__init__.py) | Defines the service package. |
| [src/services/accounts.py](../src/services/accounts.py) | Owns user preferences, account selection, and transactional personal-data deletion. |
| [src/services/alerts.py](../src/services/alerts.py) | Owns alert persistence, pagination, matching, and bounded daily-alert orchestration. |
| [src/services/analytics.py](../src/services/analytics.py) | Records successful command use and computes scoped aggregate statistics. |
| [src/services/suggestions.py](../src/services/suggestions.py) | Owns suggestion persistence, following, and atomic review outcomes. |
| [src/services/auth.py](../src/services/auth.py) | Owns Riot OAuth, credential refresh, entitlement repair, and account linking. |
| [src/services/catalog.py](../src/services/catalog.py) | Loads, searches, refreshes, and caches skin, bundle, accessory, and mission metadata. |
| [src/services/crypto.py](../src/services/crypto.py) | Encrypts and decrypts stored Riot credentials with Fernet. |
| [src/services/emojis.py](../src/services/emojis.py) | Caches application emojis and creates missing ones from packaged assets. |
| [src/services/gameplay.py](../src/services/gameplay.py) | Normalizes VALORANT battlepass, mission, and matchmaking-penalty data. |
| [src/services/http.py](../src/services/http.py) | Provides shared Riot HTTP requests, URL redaction, and rate-limit handling. |
| [src/services/shop.py](../src/services/shop.py) | Retrieves and normalizes account-scoped skin, bundle, accessory, Night Market, and wallet data. |
| [src/views/__init__.py](../src/views/__init__.py) | Re-exports common timestamps and persistent interactive controls. |
| [src/views/common.py](../src/views/common.py) | Formats values as Discord timestamps. |
| [src/views/components.py](../src/views/components.py) | Implements restart-safe, owner-restricted buttons and select menus. |
| [src/views/shop.py](../src/views/shop.py) | Shares shop cards, account/skin selectors, and Night Market presentation between commands and background notifications. |
| [src/views/ui.py](../src/views/ui.py) | Shares embed, view, error, translation, and privacy-aware account-name helpers. |

## Tests

| File | Coverage |
| --- | --- |
| [tests/conftest.py](../tests/conftest.py) | Shared SQLite setup, isolated PostgreSQL schemas, and database-cache cleanup between backends. |
| [tests/helpers.py](../tests/helpers.py) | Shared synthetic tokens and localized Discord interaction helpers. |
| [tests/test_account_commands.py](../tests/test_account_commands.py) | Account switching, pagination, and privacy-safe command responses. |
| [tests/test_accounts_service.py](../tests/test_accounts_service.py) | Account selection, preferences, deletion/relinking races, and ownership invariants. |
| [tests/test_alert_commands.py](../tests/test_alert_commands.py) | Owner-restricted alert commands and selectors. |
| [tests/test_alert_pagination.py](../tests/test_alert_pagination.py) | Alert ordering, page wrapping, and records removed during pagination. |
| [tests/test_alerts_service.py](../tests/test_alerts_service.py) | Alert ownership, bounded queries, batching, delivery order, and failure handling. |
| [tests/test_analytics.py](../tests/test_analytics.py) | Command analytics scope, DM context, tie-breaking, and empty results. |
| [tests/test_auth.py](../tests/test_auth.py) | Nonce-bound login, refresh races, token validation, and PostgreSQL row-lock protection. |
| [tests/test_bot.py](../tests/test_bot.py) | Bot lifecycle, resources, and the complete registered-command contract. |
| [tests/test_cache_expiry.py](../tests/test_cache_expiry.py) | Expiry and release of idle login, storefront, and accessory state. |
| [tests/test_catalog.py](../tests/test_catalog.py) | Catalog validation, persistence, refresh, localization, and search. |
| [tests/test_components.py](../tests/test_components.py) | Persistent component reconstruction and ownership checks. |
| [tests/test_config.py](../tests/test_config.py) | Configuration validation and safe errors for invalid values. |
| [tests/test_crypto.py](../tests/test_crypto.py) | Authenticated encryption round trips and mismatched-key rejection. |
| [tests/test_data_deletion.py](../tests/test_data_deletion.py) | Transactional deletion, pending-login cancellation, and analytics behavior after deletion. |
| [tests/test_gameplay.py](../tests/test_gameplay.py) | Validated battlepass, mission, reward, and penalty service results. |
| [tests/test_gameplay_commands.py](../tests/test_gameplay_commands.py) | Gameplay response rendering and progress bars. |
| [tests/test_health.py](../tests/test_health.py) | Freshness, failed/stopped/overdue jobs, cancellation, and dependency-health recovery. |
| [tests/test_http.py](../tests/test_http.py) | Cooldowns, concurrent rate limits, Retry-After parsing, decoding failures, and URL privacy. |
| [tests/test_jobs.py](../tests/test_jobs.py) | Background retry behavior, delivery ordering, and awaited shutdown. |
| [tests/test_localization.py](../tests/test_localization.py) | Translated command/response contracts and catalog validation. |
| [tests/test_migration.py](../tests/test_migration.py) | Migration/model parity and database initialization behavior. |
| [tests/test_models.py](../tests/test_models.py) | ORM cascade and uniqueness constraints. |
| [tests/test_monitoring.py](../tests/test_monitoring.py) | Privacy filtering, safe telemetry, and bounded/retryable Discord log delivery. |
| [tests/test_penalties.py](../tests/test_penalties.py) | Private matchmaking-penalties command output, privacy, pagination, and account ownership. |
| [tests/test_shard_status_service.py](../tests/test_shard_status_service.py) | Reuse and replacement of saved shard-status messages. |
| [tests/test_shop_commands.py](../tests/test_shop_commands.py) | Daily/accessory/featured/Night Market rendering, selectors, and private errors. |
| [tests/test_shop_service.py](../tests/test_shop_service.py) | Storefront and wallet validation, caching, expiry, and concurrent requests. |
| [tests/test_recovery.py](../tests/test_recovery.py) | PostgreSQL read-only restore verification, key rejection, and migration-history checks. |
| [tests/test_suggestions_service.py](../tests/test_suggestions_service.py) | Suggestion delivery, follower uniqueness, and review outcomes. |
| [tests/test_staff.py](../tests/test_staff.py) | Owner-only user and server diagnostics with incomplete member caches. |
