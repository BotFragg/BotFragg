# Public read-only API — implementation plan

Status: implemented · 2026-11-12 · target: BotFragg 2.x

> Archived. The served contract lives in [../public-api.md](../public-api.md);
> this file is kept for rationale history and must not be updated.

Read-only HTTP API served by the bot process, consumed by the Astro website
(separate host, different origin). **Disabled by default** so self-hosters never
expose an endpoint they did not ask for.

v1 publishes **reach only**. Command-usage metrics are explicitly deferred; when
added later they arrive as an additive `usage` object, not a breaking change.

---

## 1. Goals

- Serve `GET /v1/stats`, `GET /v1/meta`, `GET /v1/commands` from the bot.
- One env flag disables everything: no listener, no port, no side effects.
- Public payloads are aggregates only. No user IDs, guild IDs, tokens, shop
  data, or per-user rows.
- Cross-origin browser access works via an explicit origin allowlist.
- Payloads are cached in memory; requests never touch the database.

## 2. Non-goals

- Command-usage counts, top commands, feature adoption — deferred by explicit
  decision. Do not read `CommandInvocation` in v1.
- `/healthz`, uptime, shard status, Gatus integration — parked.
- Authentication, writes, per-user or per-guild data.
- TLS termination, reverse proxy, WAF, rate limiting — deployment edge.
- Historical analytics, growth charts, failure tracking — needs migrations.
- Website changes; those live in `botfragg-website`.

## 3. Decisions

| Decision | Rationale |
|---|---|
| `aiohttp.web` inside the bot process | Already a discord.py dependency; no new service |
| `PUBLIC_API_ENABLED=false` default | Self-hosters serve nothing unless they opt in |
| No usage metrics in v1 | At current scale they are noisy and vanity-negative; add when wanted |
| CORS allowlist, never `*` | Correct caching with `Vary: Origin`; explicit trust |
| Pure payload builders, thin HTTP layer | Testable without Discord login |
| In-memory cache refreshed by one loop | No DB work on request path |
| Keep last good payload on failure | Never publish zeros during an outage |
| `schemaVersion: 1`, additive changes only | Safe website contract |
| `/v1/commands` stays | It is documentation metadata, not usage analytics |
| App speaks HTTP; edge terminates TLS | Coolify/Traefik handles Let's Encrypt; the bot never manages certs |

## 4. Environment

| Variable | Default | Validation |
|---|---|---|
| `PUBLIC_API_ENABLED` | `false` | strict boolean, same rules as `_bool` |
| `PUBLIC_API_HOST` | `0.0.0.0` | non-empty, no scheme, no path, no whitespace |
| `PUBLIC_API_PORT` | `8081` | integer `1..65535` |
| `PUBLIC_API_ALLOWED_ORIGINS` | empty | comma-separated absolute origins, no path/userinfo |

Official deployment:

```dotenv
PUBLIC_API_ENABLED=true
PUBLIC_API_HOST=0.0.0.0
PUBLIC_API_PORT=8081
PUBLIC_API_ALLOWED_ORIGINS=https://botfragg.gg,https://www.botfragg.gg
```

Self-hosters: leave the block alone or set `PUBLIC_API_ENABLED=false` explicitly.
Empty `PUBLIC_API_ALLOWED_ORIGINS` means no browser can read the API; same-origin
and non-browser clients still can.

## 5. Files

| File | Change |
|---|---|
| `src/config.py` | 4 settings, `_origins()` helper, validation |
| `src/services/public_api.py` | new — payload builders, version/locale discovery |
| `src/api.py` | new — `PublicAPI`, routes, CORS middleware, cache loop |
| `src/bot.py` | start in `setup_hook`, stop in `close`, `self.api` attribute |
| `src/services/catalog.py` | add `loaded_at` timestamp set on load/refresh |
| `tests/test_config.py` | new setting coverage |
| `tests/test_public_api.py` | new — builders, routes, CORS, toggle |
| `.env.example` | commented block, off by default |
| `README.md` | Self-Hosting note + env table row |
| `docs/code-reference.md` | add the two new modules |
| `docs/public-api.md` | new — endpoint contracts and deploy notes |

Delete or archive this plan once implemented.

## 6. Config changes

Add fields to `Settings`:

```python
public_api_enabled: bool
public_api_host: str
public_api_port: int
public_api_allowed_origins: tuple[str, ...]
```

Helpers:

```python
def _host(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value or any(c.isspace() for c in value) or "/" in value:
        raise ValueError(f"{name} must be a host or IP address without a path")
    return value


def _origins(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    origins: list[str] = []
    for part in raw.split(","):
        value = part.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(f"{name} must be comma-separated origins")
        origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return tuple(dict.fromkeys(origins))
```

Port check: `_int("PUBLIC_API_PORT", 8081, 1)` then reject `> 65535` in
`from_env` with a clear message. Keep `settings = Settings.from_env(
require_secrets=False)` working without new required values.

## 7. Server module (`src/api.py`)

```python
class PublicAPI:
    def __init__(self, bot: BotFraggBot, config: Settings) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

- `start()`: build `web.Application(middlewares=[self._cors])`, register three
  GET routes, `web.AppRunner(app, access_log=None)`, `TCPSite(host, port)`,
  then a single refresh task.
- Refresh loop: every 60 s while the bot is ready, rebuild each payload that is
  due (`stats` 60 s, `meta` 300 s, `commands` 3600 s), set `ETag` from
  `sha256(body)[:16]`, keep previous body on exception.
- Handlers: `If-None-Match` → 304 with `ETag`; otherwise the cached bytes with
  `Content-Type: application/json`, `ETag`, `Cache-Control`.
- Before the first successful payload: `503` + `Retry-After: 5`.
- Non-GET: aiohttp returns 405 automatically; do not add POST routes.
- `stop()`: cancel task, `await asyncio.gather(task, return_exceptions=True)`,
  `await runner.cleanup()`. Idempotent; safe during shutdown.

Lifecycle in `src/bot.py`:

```python
# end of setup_hook
self.api = PublicAPI(self, self.config) if self.config.public_api_enabled else None
if self.api is not None:
    await self.api.start()

# close(): AsyncExitStack is LIFO, so push before super().close()
if self.api is not None:
    stack.push_async_callback(self.api.stop)
```

Logging:

- disabled: one `log.info("public API disabled")` at startup (or debug).
- enabled: one `log.info("public API listening on %s:%s", host, port)`.
- refresh failures: `log.exception` at most once per failure, never per request.

## 8. Payload contracts

Header on every response: `schemaVersion: 1`, `generatedAt` ISO-8601 UTC (`Z`).

### 8.1 `GET /v1/stats` — cache 60 s

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T11:40:00Z",
  "bot": { "version": "2.0.0" },
  "reach": { "servers": 3000, "members": 512340 }
}
```

Rules:

- `servers` = `len(bot.guilds)`.
- `members` = `sum(g.member_count or 0 for g in bot.guilds)`; cached and
  approximate — document as "members reached".
- No usage fields at all in v1. Do not include `registeredUsers`, feature
  opt-ins, active users, command counts, top commands, per-guild or per-user
  data.
- No database access. The payload is built from in-memory Discord state only.
- Future: `usage` may be added as an optional object with its own threshold
  rules. Absent field, not `null`, so older clients keep working.

### 8.2 `GET /v1/meta` — cache 300 s

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T11:40:00Z",
  "bot": { "version": "2.0.0" },
  "locales": ["en-US", "de", "pt-BR"],
  "riot": {
    "clientVersion": "11.10.00.1234567",
    "catalogRefreshedAt": "2026-11-12T09:00:00Z"
  }
}
```

- `bot.version`: `importlib.metadata.version("botfragg")`; fall back to `"unknown"`.
- `locales`: sorted directory names under `ROOT / "locales"`, filtered to
  directories. Cache at startup; it cannot change at runtime.
- `riot.clientVersion`: `bot.catalog.version` (already populated by load).
- `riot.catalogRefreshedAt`: new `CatalogService.loaded_at`, set on successful
  `load()` and `refresh()`; `null` before the first load.
- No DB queries.

### 8.3 `GET /v1/commands` — cache 3600 s

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T11:40:00Z",
  "commands": [
    {
      "name": "shop",
      "qualifiedName": "shop",
      "description": "View your daily shop",
      "guildOnly": false,
      "params": [{ "name": "user", "required": false }]
    }
  ]
}
```

- Iterate `bot.tree.walk_commands()`; include `app_commands.Command` objects.
- Exclude `command.module` containing `.staff` (owner diagnostics), and any
  command not present in the synced tree.
- English only (`command.description`, parameter descriptions as-is).
- Flatten subcommands via `qualifiedName`; keep the parent group entry too.
- Sort by `qualifiedName` for stable diffs.
- This endpoint is a manifest, not usage data. It exists for CI drift detection;
  the website keeps rendering its commands page from committed data, not from a
  client-side fetch.

## 9. CORS

```python
if origin in self._origins:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "If-None-Match"
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers["Vary"] = "Origin"
```

- `OPTIONS` short-circuits to `204`; no origin allowlisted → no CORS headers.
- No wildcard, no credentials, no `Access-Control-Allow-Credentials`.
- Same-origin and non-browser consumers are unaffected.

## 10. Deployment and exposure

The public URL is HTTPS. The bot process speaks HTTP behind the proxy; Coolify's
Traefik terminates TLS with a Let's Encrypt certificate.

### Coolify

- Compose: add `expose: ["8081"]` to the bot service. Do not add a host `ports:`
  mapping — Traefik reaches the container over the Coolify Docker network.
- In the resource's Domains field, set `https://api.botfragg.gg` and point it at
  container port `8081`. Coolify generates the Traefik route and certificate.
- Keep `PUBLIC_API_HOST=0.0.0.0`; a loopback bind is unreachable from Traefik's
  container.
- The site calls `https://api.botfragg.gg/...`; allowed origins remain the site
  origins, because the origins differ even though both are HTTPS.
- Verify: `curl -i https://api.botfragg.gg/v1/stats` returns 200 with a valid
  certificate, and the host publishes no `8081`.

### Any other edge

- A host nginx/Traefik, platform router, or Cloudflare Tunnel works the same way:
  proxy `api.botfragg.gg` → `bot:8081` (or `127.0.0.1:8081`).
- No access logging in-process; the edge owns request logs and rate limits.
- Never publish `8081` directly to the internet.
- Self-hosters set the same four variables and use their own edge.

## 11. Query and CPU budget

- Stats refresh: two in-memory passes (`len(bot.guilds)`, sum of cached member
  counts) and JSON serialization. No DB.
- Meta: one directory scan at startup; no DB.
- Commands: tree walk once per hour; no DB.
- Payload size target: < 32 KiB; commands endpoint is the largest. Fixed data,
  no user input, no unbounded growth.
- Refresh task sleeps, never polls faster than 60 s.
- No per-request work beyond a dict lookup and optional 304, so CORS preflight
  and conditional requests are effectively free.

## 12. Tests (`tests/test_public_api.py`)

Builders take plain values so tests do not need a logged-in bot:

```python
def render_stats(*, servers: int, members: int, version: str) -> dict
def render_meta(*, version: str, locales: list[str], ...) -> dict
def render_commands(commands: Iterable[PublicCommand]) -> dict
```

Required cases:

- Disabled config → `PublicAPI` not constructed / `start()` not called.
- `PUBLIC_API_ENABLED` parsing: `1/true/yes/on`, `0/false/no/off`, invalid raises.
- Port bounds: `0`, `65536`, non-integer raise.
- Origin parsing: empty → `()`, duplicates removed, paths rejected, userinfo
  rejected, `http://localhost:3000` accepted.
- Stats: payload contains no `usage`, `registeredUsers`, `users`, `guilds`,
  `commands`, or `topCommands` keys; zero guilds/members does not raise.
- Meta: locales sorted, version fallback, `catalogRefreshedAt` null before load.
- Commands: staff cog excluded, sorted output, params shape, `guildOnly`.
- HTTP: 200 + `ETag`; matching `If-None-Match` → 304; unknown origin → no CORS
  header; allowed origin → echoed header + `Vary: Origin`; `OPTIONS` → 204;
  before first payload → 503 with `Retry-After`.
- Shutdown: `stop()` can run twice without raising.

Config tests go in `tests/test_config.py` following existing patterns.

Run:

```sh
uv run pytest tests/test_public_api.py tests/test_config.py
uv run ruff check src tests
uv run mypy src
```

`AGENTS.md` rules apply: 88 columns, bandit `S`, mypy on `src` only, no `assert`
outside tests.

## 13. Documentation

`.env.example` addition:

```dotenv
# Public read-only API (disabled by default; self-hosters can leave this off)
PUBLIC_API_ENABLED=false
PUBLIC_API_HOST=0.0.0.0
PUBLIC_API_PORT=8081
# Comma-separated browser origins allowed to call the API.
PUBLIC_API_ALLOWED_ORIGINS=
```

- README Self-Hosting: one short paragraph and an env-table row.
- `docs/public-api.md`: endpoints, payload rules, exposure model (TLS at edge,
  CORS allowlist), the fact that it is off by default, and that v1 publishes
  reach only. Note the reserved `usage` object as future work.
- `docs/code-reference.md`: add `src/api.py` and
  `src/services/public_api.py` ownership rows.

## 14. Implementation order

1. Config settings + helpers + tests.
2. `src/services/public_api.py` builders + tests.
3. `src/api.py` server, CORS, cache loop + HTTP tests.
4. `BotFraggBot` lifecycle hooks; verify disabled mode has no listener.
5. `CatalogService.loaded_at`.
6. `.env.example`, README, API docs, code reference.
7. Manual smoke: enable locally, `curl -i` the three routes, verify 304 and
   CORS headers, then confirm disabled mode opens no socket (`ss -ltnp`).

## 15. Acceptance criteria

- [ ] `PUBLIC_API_ENABLED=false` (default): no socket, no request handling, no
      new log noise beyond one line.
- [ ] `PUBLIC_API_ENABLED=true`: three routes answer with `schemaVersion: 1`,
      correct `ETag`/`Cache-Control`, 503 before the first payload.
- [ ] CORS headers appear only for allowlisted origins; `Vary: Origin` present.
- [ ] Payloads contain no user/guild IDs, tokens, shop or account data, and no
      command-usage fields.
- [ ] No DB query on the request path.
- [ ] Config, tests, and docs updated; `ruff`, `mypy`, `pytest` pass.
- [ ] `https://api.botfragg.gg/v1/stats` works through Coolify with a valid
      certificate, and the host publishes no `8081`.

## 16. Open questions

- Keep `/v1/commands` in the first release, or ship it after the website CI
  consumer exists? Default: ship it; the payload is small and it prevents copy
  drift.
- Should the official instance expose `members` given cached counts? Default:
  yes, labelled "members reached".
- Command usage: deferred. When added, define its threshold and privacy rules
  first, then extend `/v1/stats` with an optional `usage` object.
- When the parked status work resumes, mount `/healthz` on this same app rather
  than starting a second listener.
