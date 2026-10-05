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
   uv run --frozen python -m compileall -q src tests
   uv run --frozen python tools/generate_api_reference.py --check
   ```

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
