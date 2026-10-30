# AGENTS.md

Python 3.14 Discord bot (`discord.py`) with Tortoise ORM. `src` is the
application package; `pyproject.toml` exposes `src.main:main` as `botfragg`.

Read `docs/code-reference.md` for module ownership and `docs/operations.md` for
health, backup, and performance behavior before changing those areas. The
code-reference tables are hand-maintained; update them when adding or renaming
source or test modules.

## Setup and run

- Use uv with the locked environment: `uv sync --all-groups --frozen`. Python
  3.14 is pinned in `.python-version`; do not hand-edit `uv.lock`.
- Start with `uv run botfragg` (root `main.py` supports `python main.py`).
  Settings load from `.env`; `TOKEN_ENCRYPTION_KEY` must be a valid Fernet key
  (the generator one-liner is in `README.md`).
- With `APP_ENV != production`, startup generates the schema from the models.
  The app never migrates itself: `docker-compose.yml` runs
  `tortoise -c src.database.TORTOISE_CONFIG migrate` before `botfragg`.

## Verification

Run these before claiming work is complete (CI order):

```sh
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv run --frozen python tools/check_locales.py
uv run --frozen python tools/generate_api_reference.py --check
uv run --frozen pytest -q
uv run --frozen python -m compileall -q src tests
```

- Focused test: `uv run --frozen pytest tests/test_auth.py::test_name -q`.
- PostgreSQL tests silently skip unless `BOTFRAGG_TEST_POSTGRES_URL` is set; CI
  also sets `BOTFRAGG_REQUIRE_POSTGRES=1`. Without them a local run never
  exercises row locking, migrations, or restore checks. Setup steps are in
  `CONTRIBUTING.md`.
- Async tests need no decorator (`asyncio_mode = auto`). Command and service
  tests use `tests.helpers` (`_localized_bot`, `_localized_interaction`,
  `TEST_TRANSLATOR`) and fake Discord objects instead of live clients.
- `pre-commit run --all-files` covers Ruff, Mypy, and pytest only; CI also
  enforces the locale check, API-reference freshness, and `compileall`.

## Generated files and schema

- `docs/api-reference.md` is generated; never hand-edit it. Every module,
  class, module-level function, and method under `main.py` and `src/**` needs a
  docstring or `tools/generate_api_reference.py` raises. Regenerate after
  changing signatures or docstrings:
  `uv run --frozen python tools/generate_api_reference.py`
- Models live in `src/models/entities.py`. Create migrations with
  `uv run --frozen tortoise -c src.database.TORTOISE_CONFIG makemigrations`;
  apply them with `... migrate`.
- After adding a migration, extend the hard-coded chain assertions in
  `tests/test_migration.py`. Do not rewrite applied migrations; they are
  exempt from formatting and some lint rules for that reason.

## Wiring and conventions

- `src/bot.py::BotFraggBot.setup_hook` explicitly lists every extension and
  calls `add_dynamic_items(...)`; new cogs and dynamic items are not discovered
  automatically. `jishaku` loads only when `APP_ENV != production`.
- Persistent controls dispatch through `BotFraggBot.component_handlers`.
  Register each action with `bot.register_component(action, handler)` in the
  cog constructor. Action names must match `[a-z_]+`, and payloads cannot
  contain `:` (custom-ID regexes in `src/views/components.py`).
- `tests/test_bot.py::test_initial_release_command_contract` hard-codes the
  command set. Update it deliberately when adding or removing commands.
- Keep the layering: cogs handle Discord I/O, `src/services` own Riot/Discord
  HTTP and persistence, `src/models` holds ORM records, and `src/views` holds
  shared UI and persistent controls. Put domain logic in services, not cogs.
- User-facing strings are Fluent messages in `locales/en-US/messages.ftl`;
  other locales fall back to English. Keep IDs and `$placeholders` consistent
  across catalogs and use `app_commands.locale_str(..., key=...)` for command
  metadata.
- Never log Riot credentials, tokens, refresh codes, or callback URLs.
  Monitoring scrubs known fields, so add any new sensitive field to that
  filter. Preserve the per-interaction ownership checks on every control.
- Ruff enforces 88 columns and bandit (`S`) rules, and Mypy checks `src` only.
  `assert` is allowed only in `tests/**` and `src/views/components.py` (`S101`).
- Commit subjects follow Conventional Commits (`fix:`, `feat:`, `chore(deps):`).
