"""Behavior checks for account commands."""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest

from src.cogs.valorant.accounts import AccountsCog
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


async def test_account_switch_hides_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that account switch hides name when preference enabled."""
    target = SimpleNamespace(puuid="target", username="SecretName#NA")
    user = SimpleNamespace(hide_ign=True, current_account_id="current")
    sent: list[discord.Embed] = []

    async def list_accounts(_user_id: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        return [target]

    async def resolve_account(_user_id: int, _value: str) -> SimpleNamespace:
        """Resolve the requested account from the fixture list."""
        return target

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Return the configured user fixture for the requested Discord ID."""
        return user

    async def select_account(_user_id: int, _account: object) -> None:
        """Record the account selected by the command under test."""
        return None

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent.append(embed)

    monkeypatch.setattr("src.cogs.valorant.accounts.list_accounts", list_accounts)
    monkeypatch.setattr("src.cogs.valorant.accounts.resolve_account", resolve_account)
    monkeypatch.setattr("src.cogs.valorant.accounts.get_user", get_user)
    monkeypatch.setattr("src.cogs.valorant.accounts.select_account", select_account)
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    cog = AccountsCog(_localized_bot(register_component=lambda *_args: None))
    await AccountsCog.account.callback(cog, interaction, "target")

    assert "SecretName" not in sent[0].description
    assert "Account" in sent[0].description


def test_accounts_layout_marks_selected_account() -> None:
    """Verify that accounts layout marks selected account."""
    first = type("Account", (), {"puuid": "one", "username": "One#NA"})()
    second = type("Account", (), {"puuid": "two", "username": "Two#EU"})()
    card = AccountsCog._accounts_embed(
        [first, second], "two", TEST_TRANSLATOR, TEST_LOCALE
    )
    assert (card.description, card.fields) == ("1. One#NA\n2. **Two#EU**", [])


def test_accounts_paginate_after_discord_embed_field_limit() -> None:
    """Verify that accounts paginate after Discord embed field limit."""
    accounts = [
        type("Account", (), {"puuid": str(index), "username": f"Account {index}"})()
        for index in range(26)
    ]
    card = AccountsCog._accounts_embed(accounts, "25", TEST_TRANSLATOR, TEST_LOCALE, 1)
    controls = AccountsCog._accounts_view(1, len(accounts), 1)
    assert (card.title, card.description, card.footer.text, controls is not None) == (
        "Your linked accounts",
        "26. **Account 25**",
        "Page 2/2",
        True,
    )
