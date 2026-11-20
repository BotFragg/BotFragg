# Public read-only API

BotFragg can expose three read-only JSON endpoints for your own website. The
listener is **disabled by default**: with `PUBLIC_API_ENABLED=false` the bot
builds no server, opens no socket, and logs one line. Self-hosters who do not
run a website should leave it off.

The API publishes reach counters plus static build and command metadata. It does
not expose command usage, active users, per-guild data, or per-user data.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `PUBLIC_API_ENABLED` | `false` | Strict boolean; blank falls back to the default |
| `PUBLIC_API_HOST` | `0.0.0.0` | Bare host or IP, no scheme or path |
| `PUBLIC_API_PORT` | `8081` | Integer `1..65535` |
| `PUBLIC_API_ALLOWED_ORIGINS` | empty | Comma-separated absolute origins, no path or userinfo |

An empty origin list means no browser can read the API. Same-origin and
non-browser clients are unaffected, so an empty list is a safe default while you
set up the edge proxy.

```dotenv
PUBLIC_API_ENABLED=true
PUBLIC_API_HOST=0.0.0.0
PUBLIC_API_PORT=8081
PUBLIC_API_ALLOWED_ORIGINS=https://botfragg.gg,https://www.botfragg.gg
```

## Endpoints

All successful `GET` responses are `application/json`, carry `schemaVersion: 1`,
and include a `generatedAt` ISO-8601 UTC timestamp. `schemaVersion` only
increases for breaking changes; new fields are additive.

| Route | Cache | Payload |
| --- | --- | --- |
| `GET /v1/stats` | 60 s | Reach counters |
| `GET /v1/meta` | 300 s | Build version, locales, Riot client and catalog freshness |
| `GET /v1/commands` | 3600 s | Command manifest for documentation drift checks |

### `GET /v1/stats`

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T11:40:00Z",
  "bot": { "version": "2.0.0" },
  "reach": { "servers": 3000, "members": 512340 }
}
```

`members` is the sum of cached guild member counts, so treat it as "members
reached" rather than a live count.

### `GET /v1/meta`

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T11:40:00Z",
  "bot": { "version": "2.0.0" },
  "locales": ["de", "en-US", "pt-BR"],
  "riot": {
    "clientVersion": "11.10.00.1234567",
    "catalogRefreshedAt": "2026-11-12T09:00:00Z"
  }
}
```

`riot.catalogRefreshedAt` is `null` until the catalog has loaded once.

### `GET /v1/commands`

A manifest of registered application commands, sorted by `qualifiedName`, with
`name`, `description`, `guildOnly`, and `params` (`name`, `required`). Owner-only
staff commands are excluded. It exists so the website can detect documentation
drift in CI; render the public commands page from committed data rather than
fetching this at runtime.

## Caching and conditional requests

Successful `GET` responses carry an `ETag` and a `Cache-Control` header matching
the table above, plus `Vary: Origin` on every response so shared caches cannot
serve a CORS-less copy to an allowed browser. Send `If-None-Match` with the
previous `ETag` to receive `304 Not Modified` (no body; includes `ETag`,
`Cache-Control`, and `Vary`). `generatedAt` marks when the document last
*changed*, so a refresh that produces identical data keeps the previous
timestamp and `ETag`. Allowed origins receive
`Access-Control-Expose-Headers: ETag`, so browser JavaScript can read the tag and
revalidate.

Error and pre-payload responses have no JSON body: `503` carries
`Retry-After: 5` and no JSON body, and `OPTIONS` preflights answer `204` with no
body, `Cache-Control`, or `ETag`. Every response, including those, still carries
`Vary: Origin`. Do not call `response.json()` on those.

## Exposure model

The bot speaks plain HTTP. Your edge terminates TLS.

- Reverse-proxy `api.example.com` to the bot on `PUBLIC_API_PORT`.
- Do not publish the port directly to the internet.
- The allowlist is an exact origin match; no wildcard, no credentials.
- Payloads are rebuilt from in-memory Discord state by a single background task,
  so request handling never touches the database. A failed refresh keeps the
  previous document instead of publishing zeros.
