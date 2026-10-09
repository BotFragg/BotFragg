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
from asyncpg.exceptions import DeadlockDetectedError
from cryptography.fernet import Fernet
from tortoise import Tortoise
from tortoise.queryset import DeleteQuery

from src.bot import BotFraggCommandTree
from src.cogs.events import EventsCog
from src.cogs.valorant.alerts import AlertsCog
from src.cogs.valorant.battlepass import BattlepassCog
from src.cogs.valorant.logout import LogoutCog
from src.cogs.valorant.penalties import PenaltiesCog
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
from src.services.analytics import command_analytics
from src.services.auth import AuthService
from src.services.catalog import Skin
from src.services.crypto import AuthVault
from src.services.suggestions import create_suggestion, follow_suggestion
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


@pytest.mark.usefixtures("backend_database")
@pytest.mark.parametrize(
    "mode", ["missions", "mission_bars", "penalties", "penalties_page", "testalerts"]
)
@pytest.mark.parametrize("change", ["delete", "relink"])
async def test_pending_account_responses_reject_deleted_or_recreated_accounts(
    mode, change
):
    owner = await User.create(id=101, current_account_id="synthetic")
    account = await Account.create(
        puuid="synthetic", user=owner, username="PrivateName#TEST"
    )
    skin = Skin(str(UUID(int=1)), "offer", "Synthetic", None, None)
    await Alert.create(account=account, skin_uuid=skin.uuid)

    async def mutate():
        await delete_user_data(owner.id)
        if change == "relink":
            replacement = await User.create(id=owner.id)
            await Account.create(
                puuid=account.puuid, user=replacement, username="Replacement#TEST"
            )

    async def gameplay(_account, **_):
        if mode != "mission_bars":
            await mutate()
        if mode in {"missions", "mission_bars"}:
            return [
                {
                    "type": "Daily Missions",
                    "title": "PRIVATE MISSION",
                    "xp": 100,
                    "complete": False,
                    "expires": None,
                    "tasks": [],
                }
            ]
        return [
            {
                "infraction": "PRIVATE PENALTY",
                "expires": None,
                "games_remaining": 3,
                "platform_scope": "All platforms",
                "effects": [],
            }
        ]

    async def bars():
        if mode == "mission_bars":
            await mutate()
        return "#", "."

    async def storefront(_account):
        await mutate()
        return NS(expires=4_000_000_000)

    bot = _localized_bot(
        register_component=lambda *_: None,
        gameplay=NS(missions=gameplay, penalties=gameplay),
        emoji_service=NS(battlepass_bars=bars, skin_name=lambda name, _: name),
        auth=NS(ensure=AsyncMock(return_value=NS(success=True))),
        shop=NS(storefront=storefront),
        catalog=NS(get_skin=lambda _: skin),
    )
    interaction = _localized_interaction(
        user=NS(id=owner.id, send=AsyncMock()),
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    if mode in {"missions", "mission_bars"}:
        await BattlepassCog.missions.callback(BattlepassCog(bot), interaction)
    elif mode == "penalties":
        await PenaltiesCog.penalties.callback(PenaltiesCog(bot), interaction)
    elif mode == "penalties_page":
        await PenaltiesCog(bot).penalties_page(interaction, "synthetic,0")
    else:
        await AlertsCog.testalerts.callback(AlertsCog(bot), interaction)
    interaction.user.send.assert_not_awaited()
    interaction.edit_original_response.assert_not_awaited()
    interaction.followup.send.assert_awaited_once()
    result = interaction.followup.send.await_args.kwargs
    assert result["ephemeral"]
    assert result["embed"].description == bot.translator.text(
        interaction.locale, "error-account-unavailable"
    )


@pytest.mark.usefixtures("backend_database")
@pytest.mark.parametrize("change", ["remove", "replace", "rename"])
async def test_manual_alert_rechecks_original_alert_and_current_account_name(change):
    owner = await User.create(id=101, current_account_id="synthetic")
    account = await Account.create(
        puuid="synthetic", user=owner, username="FormerName#TEST"
    )
    skin = Skin(str(UUID(int=1)), "offer", "Synthetic", None, None)
    alert = await Alert.create(account=account, skin_uuid=skin.uuid)

    async def storefront(_account):
        if change == "rename":
            await Account.filter(puuid=account.puuid).update(
                username="CurrentName#TEST"
            )
        else:
            await alert.delete()
            if change == "replace":
                await Alert.create(id=alert.id, account=account, skin_uuid=skin.uuid)
        return NS(expires=4_000_000_000)

    bot = _localized_bot(
        register_component=lambda *_: None,
        auth=NS(ensure=AsyncMock(return_value=NS(success=True))),
        shop=NS(storefront=storefront),
        catalog=NS(get_skin=lambda _: skin),
        emoji_service=NS(skin_name=lambda name, _: name),
    )
    interaction = _localized_interaction(
        user=NS(id=owner.id, send=AsyncMock()),
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await AlertsCog.testalerts.callback(AlertsCog(bot), interaction)
    if change == "rename":
        interaction.user.send.assert_awaited_once()
        card = interaction.user.send.await_args.kwargs["embed"]
        assert "CurrentName#TEST" in card.description
        assert "FormerName#TEST" not in card.description
    else:
        interaction.user.send.assert_not_awaited()
        assert interaction.followup.send.await_args.kwargs["ephemeral"]


async def test_crossed_suggestion_deletions_recover_from_real_deadlock(
    postgres_url, monkeypatch
):
    await Tortoise.init(
        db_url=postgres_url, modules={"models": ["src.models.entities"]}
    )
    await Tortoise.generate_schemas()
    for user_id in (101, 202):
        await User.create(id=user_id)
        await CommandInvocation.create(command="suggest", user_id=user_id)
    first = await create_suggestion(101, "First synthetic suggestion", None)
    second = await create_suggestion(202, "Second synthetic suggestion", None)
    await follow_suggestion(first.id, 202)
    await follow_suggestion(second.id, 101)
    both = asyncio.Event()
    arrived = deadlocks = 0
    original = DeleteQuery._execute

    async def synchronized_delete(query):
        nonlocal arrived, deadlocks
        try:
            result = await original(query)
        except DeadlockDetectedError:
            deadlocks += 1
            raise
        if query.model is SuggestionFollower and arrived < 2:
            arrived += 1
            if arrived == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 5)
        return result

    monkeypatch.setattr(DeleteQuery, "_execute", synchronized_delete)
    async with (
        command_analytics(101) as cancelled_first,
        command_analytics(202) as cancelled_second,
    ):
        results = await asyncio.wait_for(
            asyncio.gather(
                delete_user_data(101), delete_user_data(202), return_exceptions=True
            ),
            10,
        )
        assert results == [True, True]
        assert cancelled_first.is_set() and cancelled_second.is_set()
    assert deadlocks == 1
    for model in (User, CommandInvocation, Suggestion, SuggestionFollower):
        assert not await model.exists()


@pytest.mark.usefixtures("backend_database")
@pytest.mark.parametrize("failure", [DeadlockDetectedError, ValueError])
async def test_failed_deletion_retries_only_deadlocks_and_preserves_all_data(
    monkeypatch, failure
):
    owner = await User.create(id=101)
    await CommandInvocation.create(command="suggest", user_id=owner.id)
    await create_suggestion(owner.id, "Synthetic suggestion", None)
    original = DeleteQuery._execute
    attempts = 0

    async def failed_delete(query):
        nonlocal attempts
        if query.model is User:
            attempts += 1
            raise failure("Synthetic deletion failure")
        return await original(query)

    monkeypatch.setattr(DeleteQuery, "_execute", failed_delete)
    async with command_analytics(owner.id) as cancelled:
        with pytest.raises(failure):
            await delete_user_data(owner.id)
        assert not cancelled.is_set()
        for model in (User, CommandInvocation, Suggestion, SuggestionFollower):
            assert await model.exists()
        assert attempts == (3 if failure is DeadlockDetectedError else 1)
        monkeypatch.setattr(DeleteQuery, "_execute", original)
        assert await delete_user_data(owner.id)
        assert cancelled.is_set()


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


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize(
    "case", ["success", "failure", "missing", "deletedata", "autocomplete"]
)
async def test_command_tree_records_only_successful_commands(monkeypatch, case):
    invoke = AsyncMock()
    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", invoke)
    interaction = NS(
        type=discord.InteractionType.autocomplete
        if case == "autocomplete"
        else discord.InteractionType.application_command,
        data={"name": "localized-name"},
        user=NS(id=104),
        command=None
        if case == "missing"
        else NS(
            qualified_name="deletedata" if case == "deletedata" else "settings privacy"
        ),
        command_failed=case == "failure",
        guild_id=105,
        channel_id=106,
    )
    await object.__new__(BotFraggCommandTree)._call(interaction)
    invoke.assert_awaited_once()
    rows = await CommandInvocation.filter(user_id=104)
    assert len(rows) == (1 if case == "success" else 0)
    if rows:
        assert (rows[0].command, rows[0].guild_id, rows[0].channel_id) == (
            "settings privacy",
            105,
            106,
        )


@pytest.mark.usefixtures("database")
async def test_command_tree_suppresses_completion_after_concurrent_deletion(
    monkeypatch,
):
    started, resume = asyncio.Event(), asyncio.Event()

    async def invoke(tree, interaction):
        started.set()
        await resume.wait()

    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", invoke)
    tree = object.__new__(BotFraggCommandTree)
    interaction = NS(
        type=discord.InteractionType.application_command,
        data={"name": "shop"},
        user=NS(id=105),
        guild_id=None,
        channel_id=None,
        command=NS(qualified_name="shop"),
        command_failed=False,
    )
    pending = asyncio.create_task(tree._call(interaction))
    await started.wait()
    await delete_user_data(105)
    resume.set()
    await pending
    assert not await CommandInvocation.exists(user_id=105)
    await tree._call(interaction)
    assert await CommandInvocation.filter(user_id=105).count() == 1


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
