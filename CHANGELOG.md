# Changelog

## [1.2.0] - Unreleased

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
- Recover daily alerts, catalog refreshes, and shard-status jobs after temporary HTTP, socket, timeout, or database failures.
- Notify suggestion authors when reviews overlap submission, show completed reviews privately when tracking, and bound review reasons before saving.
- Translate setting prompts and placeholders, correct account-limit instructions, and avoid suggestion command-name collisions in Greek, Hungarian, and Vietnamese.
- Split oversized Discord log records and expire abandoned login, shop, and idle lock state.

### Security

- Bind credential access, alert creation and delivery, and public account responses to the original account owner and creation time across deletion and relinking.
- Redact webhook tokens, interaction tokens, and OAuth values in logged URLs.
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
