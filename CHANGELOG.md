# Changelog

## [Unreleased]

### Added

- `/crosshair view` shows the caller's saved crosshair profiles, their export codes,
  and a locally rendered preview, with a menu to switch profiles.

## [1.3.0] - 2026-10-31

### Changed

- `/logout` now cancels a Riot login that is already in flight, so credentials submitted
  moments earlier cannot be stored after the command reports success.
- The Riot client-version and catalog refresh jobs are merged into one loop; the same
  upstream fetch now feeds both. `GAME_VERSION_INTERVAL_MINUTES` is removed — use
  `USER_AGENT_INTERVAL_MINUTES` to set the cadence.
- The inert `VERBOSE_LOGGING` setting is removed; the bot logs at `INFO`.
- `SHARD_COUNT` is limited to 1–1000 so a typo fails at startup instead of stalling shard
  launches.
- Account ownership columns are indexed, and command analytics ids are 64-bit, so
  lookups stay fast and the never-pruned table cannot overflow.
- Container images built for a version tag are smoke-tested before they are published.
- Container images are published for both `linux/amd64` and `linux/arm64`.
- Rolling migration 0006 back now refuses when analytics ids no longer fit in 32 bits
  instead of narrowing the column and breaking later inserts.

### Fixed

- A cached storefront is served while Riot authentication is unavailable instead of being
  discarded, and `/logout` drops the cached entry.
- Switching accounts on a Night Market view for an account without offers now reports that
  no Night Market is available instead of rendering an empty header.
- A suggestion review now confirms to the owner before notifying followers, so a large
  follower list no longer stalls or fails the confirmation.
- Shop prices and discounts use each locale's number formatting.
- A malformed `GLITCHTIP_DSN` logs a warning and disables error reporting instead of
  stopping the bot.
- `/testalerts` reports a failed DM when the connection drops instead of hanging.
- `/botinfo` retries a failed commit lookup after a minute instead of an hour.
- `/help` fetches the command list once per process instead of on every call.
- Alert pagination no longer skips an alert when another view removes one from an earlier
  page.
- Rolling migration 0005 back no longer republishes every user's shop.
- Suggestion review no longer DMs a follower who untracked or deleted their data mid-review.
- Concurrent daily-alert workers no longer lose delivery-failure counts.
- Shard webhook transport failures are logged instead of escaping the listener.
- Daily alert runs query accounts and alerts in batches, so a large opted-in user base no
  longer exceeds the database's parameter limit and stops the job.
- A malformed `GLITCHTIP_DSN` port disables error reporting instead of stopping the bot.
- `AUTO_REFRESH_TOKENS=false` is honoured when an account has a valid access token but no
  entitlement token.
- `/ping` reports the database as unavailable after a five-second probe instead of hanging.
- The health probe reports a closed gateway shard, so a disconnected bot no longer looks
  healthy.
- Accessory shop prices, wallet balances, and battlepass progress use the locale's number
  formatting.
- A Riot login outage is reported as temporarily unavailable instead of a rejected code.
- The shard-status message notes any shards hidden by Discord's 25-field limit.
- `/ping` reports an unreachable database as unavailable, not only a slow one.
- Submitting an older `/login` link no longer discards the current pending login.
- A failed daily alert run logs its error instead of only marking the job unhealthy.
- `/botinfo` caps its commit list below Discord's field limit and formats source lines
  and process numbers for the locale.
- A failed application-emoji fetch at startup is retried instead of disabling tier emojis
  until the next restart.
- Applying migration 0006 to a development database whose schema was generated from the
  models no longer fails with an "index already exists" error.

## [1.2.3] - 2026-10-22

### Changed

- Upgrade tzdata to 2026.5, python-dotenv to 1.2.4, and sentry-sdk to 2.72.0.
- Update the CI workflows to `actions/checkout` v7, `astral-sh/setup-uv` v7, `docker/build-push-action` v7, and `docker/login-action` v4.
- Upgrade ruff to 0.17.1 for development.

## [1.2.2] - 2026-10-22

### Security

- Upgrade aiohttp to 3.14.5, resolving eight security advisories that affect 3.14.3 and earlier, three of them high severity.

## [1.2.1] - 2026-10-22

### Security

- Upgrade certifi to 2026.10.19 so Sentry error reporting stops trusting the compromised eMudhra/emSign intermediate CA certificates.
- Build container images with uv 0.13.5 instead of 0.11.21 so dependency resolution rejects the compromised eMudhra/emSign intermediates.

### Changed

- Publish container images only for version tags matching `v*`. The `latest` tag now tracks the newest version tag instead of every push to `main`.

## [1.2.0] - 2026-10-10

### Added

- Localized commands, responses, and VALORANT catalog text with 25 Fluent catalogs and English fallback.
- Publish container images to GitHub Container Registry after CI passes on `main` and version tags.
- Add container health probes for Discord, the database, and background jobs, including daily shop and notification failures.
- Add a read-only backup recovery verifier, a disposable PostgreSQL benchmark, and an [operations guide](docs/operations.md).

### Changed

- Organize `/help` by command category and keep its links in dedicated controls.
- Share shop and Night Market presentation, separate service responsibilities, and organize regression tests by behavior.
- Require PostgreSQL migration, row-lock, and recovery checks in CI alongside application type checking.
- Remove unused settings and translation entries; exclude private notes, caches, bytecode, and build output from Git or release inputs as appropriate.

### Fixed

- Retry daily alert lookups after Riot rate limits and transient database errors without replaying delivered notifications; contain exhausted database retries without duplicating the next scheduled run.
- Keep unreadable stored credentials intact and isolate their failure to the affected account.
- Reject incomplete daily shop catalogs instead of caching empty or partial results.
- Retry saving rotated credentials before exchanging a refresh token again after a database failure.
- Prevent commands running during data deletion from recreating personal analytics, suggestions, or follows.
- Recheck account ownership, alert identity, and daily shop preferences after preparing notifications.
- Remove persistent component handlers when command extensions unload so they can reload cleanly.
- Report incomplete Night Market catalogs as unavailable and fetch them again after catalog recovery.
- Retry saving a shard-status message ID without posting a duplicate after a database failure.
- Honor privacy changes while preparing accounts, shops, balances, battlepass, and interactive responses; redact lists after a public defer and send hidden names privately when paging.
- Preserve newer login credentials during concurrent refreshes, allow re-login at the account limit, and show localized errors for malformed callback URLs.
- Reject stale account selections after deletion or relinking and handle accounts deleted during token refresh.
- Delete personal records without requiring a linked Riot account; cancel pending logins and prevent command analytics from recreating deleted records.
- Keep valid catalog data after malformed responses, failed saves, or cancelled refreshes; refresh buddy and accessory metadata when catalog versions change.
- Report unavailable or malformed accessory metadata as an error instead of claiming all accessories are owned.
- Validate nested login, token, shop, wallet, battlepass, and buddy data; keep temporary upstream failures retryable.
- Respect Night Market expiry, select the active battlepass act, and safely display empty shops or incomplete bundle data.
- Honor bounded `Retry-After` delays, including HTTP dates and malformed response bodies, and preserve the longest concurrent rate-limit cooldown.
- Back off repeated Riot accessory lookup, application emoji creation, and Discord delivery failures; resume failed suggestion deliveries without duplicate notices.
- Use the accessory store's expiry for its countdown and reject Night Market timers that are missing or incomplete.
- Recover daily alerts, catalog refreshes, and shard-status jobs after temporary HTTP, socket, timeout, or database failures.
- Report component and login-form failures privately, and send at most one expired-login notice per user per run.
- Notify suggestion authors when reviews overlap submission, show completed reviews privately when tracking, and bound review reasons before saving.
- Translate setting prompts and placeholders, correct account-limit instructions, and avoid suggestion command-name collisions in Greek, Hungarian, and Vietnamese.
- Split oversized Discord log records and expire abandoned login, shop, and idle lock state.

### Security

- Bind credential access, alert creation and delivery, and public account responses to the original account owner and creation time across deletion and relinking.
- Redact webhook tokens, interaction tokens, and OAuth values in logged URLs.
- Discard raw telemetry logging parameters and redact Discord delivery identifiers from logged URLs.
- Upgrade multidict to 6.9.1 to address CVE-2026-104874.

### Documentation

- Refresh setup, configuration, contributor, and API documentation; clarify that configured operator prefix commands can be processed in DMs.

## [1.1.0] - 2026-10-03

### Added

- Browse the featured VALORANT bundle and its available items.
- Check matchmaking penalties privately, with five records per page.
- Open skin and chroma videos from the shop.
- View the five latest public GitHub commits in `/botinfo` and find the repository in `/links`.

### Improved

- Show skin tier emojis alongside skin names in shops, alerts, and Night Market.
- Display Night Market discounts consistently when opened from the shop.
- Preserve Night Market controls when switching accounts.
- Expand `/botinfo` with community, software, and process details.
- Improve catalog refresh reliability, alert delivery, diagnostics, and `/userinfo` responsiveness.
- Improve Riot API error messages and currency formatting.

### Fixed

- Include timezone data required for Windows deployments.
- Use consistent BotFragg capitalization.

### Documentation

- Published the [Terms of Service](tos.md) and updated the [Privacy Policy](PRIVACY.md).
