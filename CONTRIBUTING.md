# Contributing to BotFragg

Use Python 3.14 and [uv](https://docs.astral.sh/uv/).

1. Copy `.env.example` to `.env` and provide development-only credentials.
2. Run `uv sync --all-groups --frozen`.
3. Install the pre-commit hook once:

   ```sh
   uv tool install pre-commit
   pre-commit install
   ```

   Linting workflow files uses the actionlint Docker image, so Docker must be
   available when changing files under `.github/workflows/`.

4. Before opening a pull request, run the same checks as CI:

   ```sh
   pre-commit run --all-files
   ```

   The hook runs Ruff, Mypy, the locale check, API-reference freshness,
   pytest, `compileall`, and actionlint for workflow files. PostgreSQL-backed
   tests still skip locally unless `BOTFRAGG_TEST_POSTGRES_URL` is set, as
   described below.

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

## Releasing

Releases are prepared by
[release-please](https://github.com/googleapis/release-please) from Conventional
Commits. Pushing to `main` opens or updates a release pull request that bumps
`pyproject.toml`, updates `CHANGELOG.md`, and creates the `vX.Y.Z` tag when
merged. The tag triggers the Docker publish workflow.

The `RELEASE_PLEASE_TOKEN` secret needs Contents, Issues, and Pull requests
write access. release-please labels its pull request `autorelease: pending`
and finds it by that label, so the Issues permission is required.

1. Review the release pull request and edit its `CHANGELOG.md` entry if the
   generated summary needs more context.
2. Merge once CI passes. The release workflow refreshes `uv.lock` on the
   release branch automatically, so the lockfile stays in sync.

If another commit lands on `main` while the release pull request is open,
release-please rewrites the branch and regenerates the changelog. Re-apply any
hand-written changelog edits before merging.

Only `feat`, `fix`, `perf`, and `refactor` appear in the generated changelog;
`docs`, `chore`, `ci`, `test`, `style`, and `build` commits are hidden.

The first release needs a one-time reconciliation: the existing
`## [Unreleased]` section predates release-please. Merge its prose into the
generated section and remove it in the release pull request.

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
