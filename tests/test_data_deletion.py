"""Behavior checks for data deletion."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import discord
import pytest

from src.cogs.valorant.logout import LogoutCog
from src.models import (
    Account,
    Alert,
    CommandInvocation,
    Suggestion,
    SuggestionFollower,
    User,
)
from src.services.accounts import (
    delete_user_data,
)
from tests.helpers import _localized_bot, _localized_interaction


@pytest.mark.usefixtures("database")
async def test_delete_user_data_removes_personal_records() -> None:
    """Verify that delete user data removes personal records."""
    user = await User.create(id=901)
    account = await Account.create(puuid="delete-me", user=user, username="Delete#NA")
    await Alert.create(
        account=account, skin_uuid=UUID("11111111-1111-1111-1111-111111111111")
    )
    await CommandInvocation.create(command="shop", user_id=user.id)
    suggestion = await Suggestion.create(author_id=user.id, content="Remove me")
    await SuggestionFollower.create(suggestion=suggestion, user_id=user.id)

    assert await delete_user_data(user.id)
    assert not await User.exists(id=user.id)
    assert not await Account.exists(puuid=account.puuid)
    assert not await Alert.exists(account_id=account.puuid)
    assert not await CommandInvocation.exists(user_id=user.id)
    assert not await Suggestion.exists(author_id=user.id)
    assert not await SuggestionFollower.exists(user_id=user.id)


async def test_deletedata_clears_cached_shops_after_database_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that deletedata clears cached shops after database delete."""
    events: list[object] = []
    accounts = [SimpleNamespace(puuid="first"), SimpleNamespace(puuid="second")]

    async def list_accounts(user_id: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        events.append(("list", user_id))
        return accounts

    async def delete_user_data(user_id: int) -> bool:
        """Record deletion of the user's stored data."""
        events.append(("delete", user_id))
        return True

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def clear_cached_storefront(self, account_id: str) -> None:
            """Record removal of the account's cached storefront."""
            events.append(("clear", account_id))

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking and ephemeral

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
            """Record the follow-up message sent through the fake interaction."""
            assert ephemeral

    monkeypatch.setattr("src.cogs.valorant.logout.list_accounts", list_accounts)
    monkeypatch.setattr("src.cogs.valorant.logout.delete_user_data", delete_user_data)
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await LogoutCog.deletedata.callback(
        LogoutCog(_localized_bot(shop=Shop())), interaction, True
    )

    assert events == [
        ("list", 123),
        ("delete", 123),
        ("clear", "first"),
        ("clear", "second"),
    ]
