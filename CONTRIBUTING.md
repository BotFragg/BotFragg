# Contributing to BotFragg

Use Python 3.14 and [uv](https://docs.astral.sh/uv/).

1. Copy `.env.example` to `.env` and provide development-only credentials.
2. Run `uv sync --all-groups --frozen`.
3. Install the pre-commit hook once:

   ```sh
   uv tool install pre-commit
   pre-commit install
   ```

4. Before opening a pull request, run the same checks as CI:

   ```sh
   pre-commit run --all-files
   uv run --frozen mypy
   uv run --frozen python -m compileall -q src tests
   uv run --frozen python tools/generate_api_reference.py --check
   ```

Mypy checks every application module, including bodies of unannotated functions.

## PostgreSQL verification

CI provisions PostgreSQL 17 and sets `BOTFRAGG_REQUIRE_POSTGRES=1`, so its
database checks cannot silently skip. Locally, SQLite checks always run and
PostgreSQL checks skip unless a disposable database is provided. To run the
full suite, start a localhost-only disposable database:

```sh
docker run --rm --name botfragg-test-postgres -e POSTGRES_DB=botfragg_test -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55432:5432 postgres:17
```

In another terminal, set the test environment and run pytest. PowerShell:

```powershell
$env:BOTFRAGG_TEST_POSTGRES_URL = "postgres://postgres@127.0.0.1:55432/botfragg_test"
$env:BOTFRAGG_REQUIRE_POSTGRES = "1"
uv run --frozen pytest -q
docker stop botfragg-test-postgres
Remove-Item Env:BOTFRAGG_TEST_POSTGRES_URL, Env:BOTFRAGG_REQUIRE_POSTGRES
```

This trust-authenticated instance is disposable and bound only to localhost;
use an isolated development machine. Each PostgreSQL test creates and drops
its own schema. Tests cover row locking, migrations, constraints, data deletion,
rollback/reapply, and read-only recovery verification. Never point these test
variables at production. Test modules are grouped by behavior; preserve the
existing regression cases when moving responsibilities.

The [operations guide](docs/operations.md) documents health probes, backup/restore
verification, and the synthetic database benchmark.

When changing Python modules, classes, callables, or their docstrings,
regenerate the browsable API reference:

```sh
uv run --frozen python tools/generate_api_reference.py
```

## Adding a translation

English (`locales/en-US/messages.ftl`) is the source catalog. To add a language,
create `locales/<Discord locale>/messages.ftl` using the exact locale code that
Discord uses, then translate the English messages while keeping their IDs
unchanged. For example, Discord's French locale code is `fr`.

Keep every Fluent variable such as `{ $username }` in the translated message;
the values are supplied by the bot and must remain visible. Missing messages
fall back to English, so translations can be contributed in smaller batches.
Command names, parameter names, and their descriptions use the same catalog.
Translated names must follow Discord's slash-command naming limits. Keep
VALORANT/Riot names, player names, and commit subjects as provided by their
source.

Run `uv run --frozen python tools/check_locales.py` to validate Fluent syntax,
Discord locale codes, message IDs, and placeholder names before opening a pull
request.

Keep changes focused, preserve Discord interaction ownership checks, never log Riot credentials or callback URLs, and add a focused regression test for changed behaviour. Do not commit `.env`, databases, compiled catalogs, or API secrets.
