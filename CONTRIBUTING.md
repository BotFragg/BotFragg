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

5. When changing Python modules, classes, callables, or their docstrings,
   regenerate the browsable API reference:

   ```sh
   uv run --frozen python tools/generate_api_reference.py
   ```

Keep changes focused, preserve Discord interaction ownership checks, never log Riot credentials or callback URLs, and add a focused regression test for changed behaviour. Do not commit `.env`, databases, compiled catalogs, or API secrets.
