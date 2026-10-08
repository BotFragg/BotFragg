"""Behavior and regression checks for data deletion."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import UUID

import discord
import pytest
from cryptography.fernet import Fernet

from src.cogs.events import EventsCog
from src.cogs.valorant.logout import LogoutCog
from src.localization import BotFraggTranslator
from src.models import (
    Account,
    Alert,
    CommandInvocation,
    Suggestion,
    SuggestionFollower,
    User,
)
from src.services.accounts import delete_user_data
from src.services.auth import AuthService
from src.services.crypto import AuthVault
from tests.helpers import (
    _localized_bot,
    _localized_interaction,
)


def lifetime_jwt(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{payload}.x"


def auth_service(http=None):
    return AuthService(
        NS(
            token_refresh_buffer_minutes=5,
            auto_refresh_tokens=True,
            max_accounts_per_user=10,
        ),
        http or NS(),
        AuthVault(Fernet.generate_key().decode()),
    )


@pytest.mark.usefixtures("database")
async def test_delete_data_without_riot_profile():
    suggestion = await Suggestion.create(author_id=101, content="Synthetic idea")
    await SuggestionFollower.create(suggestion=suggestion, user_id=101)
    await CommandInvocation.create(command="suggest", user_id=101)
    assert await delete_user_data(101)
    assert not await CommandInvocation.exists(user_id=101)
    assert not await Suggestion.exists(author_id=101)
    assert not await SuggestionFollower.exists(user_id=101)
    assert not await delete_user_data(101)


@pytest.mark.usefixtures("database")
async def test_deletedata_completion_does_not_recreate_personal_data():
    await User.create(id=102)
    await delete_user_data(102)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=102), guild_id=None, channel_id=None
    )
    await EventsCog(SimpleNamespace()).on_app_command_completion(
        interaction, SimpleNamespace(qualified_name="deletedata")
    )
    assert not await CommandInvocation.exists(user_id=102)


@pytest.mark.asyncio
async def test_deletedata_invalidates_pending_login(database):
    auth = auth_service()
    await User.create(id=101)
    auth.login_url(101)
    nonce = auth._pending_nonces[101][0]
    auth.http = NS(
        request=AsyncMock(
            return_value=NS(
                status=200,
                data={
                    "access_token": lifetime_jwt(
                        sub="synthetic", exp=int(time.time()) + 3600
                    ),
                    "id_token": lifetime_jwt(nonce=nonce),
                    "refresh_token": "synthetic-refresh",
                },
            )
        )
    )
    auth._user_info = AsyncMock(return_value={"game_name": "Example", "tag_line": "NA"})
    auth._entitlement = AsyncMock(return_value="synthetic-ent")
    auth._region = AsyncMock(return_value="na")
    bot = NS(
        auth=auth,
        translator=BotFraggTranslator(),
        shop=NS(clear_cached_storefront=AsyncMock()),
    )
    interaction = NS(
        user=NS(id=101),
        client=bot,
        locale=discord.Locale.american_english,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await LogoutCog.deletedata.callback(LogoutCog(bot), interaction, True)
    result = await auth.redeem_callback(101, "http://localhost/redirect?code=synthetic")
    assert not result.success and not await User.exists(id=101), (
        "An outstanding login recreated deleted user data"
    )


@pytest.mark.asyncio
async def test_inflight_login_cannot_recreate_deleted_data(database):
    auth = auth_service()
    await User.create(id=101)
    auth.login_url(101)
    nonce = auth._pending_nonces[101][0]
    entered, resume = asyncio.Event(), asyncio.Event()

    async def exchange(*args, **kwargs):
        entered.set()
        await resume.wait()
        return NS(
            status=200,
            data={
                "access_token": lifetime_jwt(
                    sub="synthetic", exp=int(time.time()) + 3600
                ),
                "id_token": lifetime_jwt(nonce=nonce),
                "refresh_token": "synthetic-refresh",
            },
        )

    auth.http = NS(request=exchange)
    auth._user_info = AsyncMock(return_value={"game_name": "Example", "tag_line": "NA"})
    auth._entitlement = AsyncMock(return_value="synthetic-ent")
    auth._region = AsyncMock(return_value="na")
    login = asyncio.create_task(
        auth.redeem_callback(101, "http://localhost/redirect?code=synthetic")
    )
    await entered.wait()
    bot = NS(
        auth=auth,
        translator=BotFraggTranslator(),
        shop=NS(clear_cached_storefront=AsyncMock()),
    )
    interaction = NS(
        user=NS(id=101),
        client=bot,
        locale=discord.Locale.american_english,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await LogoutCog.deletedata.callback(LogoutCog(bot), interaction, True)
    resume.set()
    result = await login
    assert not result.success and not await User.exists(id=101), (
        "Login started before deletion recreated data after deletion completed"
    )
    assert result.error_key == "login-attempt-expired"
    auth.login_url(101)
    nonce = auth._pending_nonces[101][0]
    fresh = await auth.redeem_callback(101, "http://localhost/redirect?code=fresh")
    assert fresh.success and await User.exists(id=101)
    assert not auth._login_cancellations
    assert not auth._login_locks


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
        LogoutCog(
            _localized_bot(
                shop=Shop(),
                auth=AuthService(
                    SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
                ),
            )
        ),
        interaction,
        True,
    )

    assert events == [
        ("list", 123),
        ("delete", 123),
        ("clear", "first"),
        ("clear", "second"),
    ]
