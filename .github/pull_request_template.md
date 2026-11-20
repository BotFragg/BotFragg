## Summary

<!-- What changes, and why. Link the issue this closes. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Dependency update
- [ ] Docs, CI, or chore only

## Test plan

<!-- The commands you ran, and anything a reviewer must check by hand: Discord client, a linked Riot account, a resumed gateway session. -->

## Touched any of these?

- [ ] **Migration added** — chain assertions extended in `tests/test_migration.py`.
- [ ] **Command added or removed** — `tests/test_bot.py::test_initial_release_command_contract` updated deliberately.
- [ ] **Module added or renamed** — row added to `docs/code-reference.md`.
- [ ] **Signature or docstring changed** — `docs/api-reference.md` regenerated.
- [ ] **Persistent component added** — registered through `component_handlers` and `add_dynamic_items`.
- [ ] **User-facing string added** — present in `locales/en-US/messages.ftl`, placeholders consistent across catalogs.
- [ ] **Dockerfile or base image changed** — image still builds and the startup smoke test passes.

## Checklist

- [ ] `uv run --frozen ruff check .`
- [ ] `uv run --frozen ruff format --check .`
- [ ] `uv run --frozen mypy`
- [ ] `uv run --frozen python tools/check_locales.py`
- [ ] `uv run --frozen python tools/generate_api_reference.py --check`
- [ ] `uv run --frozen pytest -q`
- [ ] `uv run --frozen python -m compileall -q src tests`

PostgreSQL-backed tests skip without `BOTFRAGG_TEST_POSTGRES_URL`; note it if the change touches row locking, migrations, or backups.

## Notes for reviewers

<!-- Trade-offs, follow-up work, known gaps. CHANGELOG.md and the pyproject version belong to release-please; do not edit them here. -->
