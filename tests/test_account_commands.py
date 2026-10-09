"""Behavior and regression checks for account commands."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
import pytest_asyncio
from tortoise import Tortoise

from src.cogs.valorant.accounts import AccountsCog
from src.localization import BotFraggTranslator
from src.models import Account, User
from src.services.accounts import delete_user_data, select_account
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


@pytest_asyncio.fixture
async def command_accounts(migration_url):
    """Exercise command races against both supported databases."""
    await Tortoise.init(
        db_url=migration_url, modules={"models": ["src.models.entities"]}
    )
    await Tortoise.generate_schemas()
    try:
        owner = await User.create(id=101, current_account_id="first")
        await Account.create(puuid="first", user=owner, username="SecretOne#NA")
        target = await Account.create(
            puuid="target", user=owner, username="SecretTwo#NA"
        )
        yield owner, target
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize(
    ("route", "stage"),
    [("switch", "select"), ("list", "list"), ("list", "defer"), ("page", "list")],
)
async def test_account_commands_recheck_privacy_after_preparation(
    command_accounts, monkeypatch, route, stage
):
    import src.cogs.valorant.accounts as module

    owner, target = command_accounts
    original_list = module.list_accounts
    original_select = module.select_account

    async def hide_names():
        await User.filter(id=owner.id).update(hide_ign=True)

    async def list_accounts(user_id):
        accounts = await original_list(user_id)
        if stage == "list":
            await hide_names()
        return accounts

    async def select_account(user_id, account):
        await original_select(user_id, account)
        if stage == "select":
            await hide_names()

    async def defer(**kwargs):
        if stage == "defer":
            await hide_names()

    monkeypatch.setattr(module, "list_accounts", list_accounts)
    monkeypatch.setattr(module, "select_account", select_account)
    bot = _localized_bot(register_component=lambda *args: None)
    interaction = _localized_interaction(
        user=NS(id=owner.id),
        response=NS(defer=AsyncMock(side_effect=defer), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(),
        message=NS(flags=NS(ephemeral=False)),
    )
    cog = AccountsCog(bot)
    if route == "switch":
        await AccountsCog.account.callback(cog, interaction, target.puuid)
    elif route == "list":
        await AccountsCog.accounts.callback(cog, interaction)
    else:
        await cog.accounts_page(interaction, "0")

    assert (await User.get(id=owner.id)).hide_ign is True
    assert interaction.followup.send.await_count == 1
    sent = interaction.followup.send.await_args.kwargs
    # A slash command's first followup inherits its deferred response visibility.
    private = (
        interaction.response.defer.await_args.kwargs.get("ephemeral", False)
        if route == "list"
        else sent.get("ephemeral", False)
    )
    if private:
        assert "Secret" in sent["embed"].description
    else:
        assert "Secret" not in str(sent["embed"].to_dict())
    if route == "page":
        interaction.edit_original_response.assert_not_awaited()


@pytest.mark.parametrize("hide", [False, True])
async def test_account_list_preserves_normal_visibility(command_accounts, hide):
    owner, _ = command_accounts
    await User.filter(id=owner.id).update(hide_ign=hide)
    interaction = _localized_interaction(
        user=NS(id=owner.id),
        response=NS(defer=AsyncMock()),
        followup=NS(send=AsyncMock()),
    )
    cog = AccountsCog(_localized_bot(register_component=lambda *args: None))
    await AccountsCog.accounts.callback(cog, interaction)
    assert interaction.response.defer.await_args.kwargs["ephemeral"] is hide
    sent = interaction.followup.send.await_args.kwargs
    assert sent["ephemeral"] is hide
    assert "SecretOne#NA" in sent["embed"].description
    assert "SecretTwo#NA" in sent["embed"].description


@pytest.mark.parametrize("route", ["list", "page"])
@pytest.mark.parametrize("stage", ["defer", "list"])
@pytest.mark.parametrize("relink", [False, True])
async def test_account_lists_reject_profile_changes_during_preparation(
    command_accounts, monkeypatch, route, stage, relink
):
    import src.cogs.valorant.accounts as module

    owner, _ = command_accounts
    original_list = module.list_accounts
    changed = False

    async def replace_profile():
        nonlocal changed
        if changed:
            return
        changed = True
        await delete_user_data(owner.id)
        if relink:
            replacement = await User.create(id=owner.id, current_account_id="first")
            assert replacement.created_at != owner.created_at
            await Account.create(
                puuid="first", user=replacement, username="NewProfile#TEST"
            )

    async def list_accounts(user_id):
        accounts = await original_list(user_id)
        if stage == "list":
            await replace_profile()
        return accounts

    async def defer(**kwargs):
        if stage == "defer":
            await replace_profile()

    monkeypatch.setattr(module, "list_accounts", list_accounts)
    interaction = _localized_interaction(
        user=NS(id=owner.id),
        response=NS(defer=AsyncMock(side_effect=defer), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(),
        message=NS(flags=NS(ephemeral=False)),
    )
    cog = AccountsCog(_localized_bot(register_component=lambda *args: None))

    async def invoke():
        if route == "list":
            await AccountsCog.accounts.callback(cog, interaction)
        else:
            await cog.accounts_page(interaction, "0")

    await invoke()
    interaction.edit_original_response.assert_not_awaited()
    sent = interaction.followup.send.await_args.kwargs
    key = "error-not-registered" if route == "list" else "accounts-none-left"
    assert sent["embed"].description == TEST_TRANSLATOR.text(TEST_LOCALE, key)
    assert "view" not in sent
    assert not await Account.exists(puuid="target")
    if relink:
        interaction.followup.send.reset_mock()
        await invoke()
        sent = (
            interaction.followup.send.await_args.kwargs
            if route == "list"
            else interaction.edit_original_response.await_args.kwargs
        )
        assert "NewProfile#TEST" in sent["embed"].description
        assert "Secret" not in sent["embed"].description


async def test_account_command_uses_one_consistent_account_list(database, monkeypatch):
    import src.cogs.valorant.accounts as cog_module

    owner = await User.create(id=101)
    await Account.create(puuid="first", user=owner, username="First")
    original_list = cog_module.list_accounts
    queried = False

    async def list_then_link(discord_id):
        nonlocal queried
        accounts = await original_list(discord_id)
        if not queried:
            queried = True
            linked = await Account.create(puuid="new", user=owner, username="New")
            await select_account(owner.id, linked)
            await select_account(owner.id, accounts[0])
        return accounts

    monkeypatch.setattr(cog_module, "list_accounts", list_then_link)
    translator = NS(text=lambda locale, key, **kwargs: key)
    bot = NS(register_component=lambda *args: None, translator=translator)
    cog = AccountsCog(bot)
    interaction = NS(
        user=NS(id=owner.id),
        client=bot,
        locale=discord.Locale.american_english,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await AccountsCog.account.callback(cog, interaction, "new")
    assert interaction.followup.send.await_count == 1


async def test_stale_command_selection_returns_account_not_found(database, monkeypatch):
    import src.cogs.valorant.accounts as cog_module

    owner = await User.create(id=101)
    await Account.create(puuid="synthetic", user=owner, username="Synthetic")
    original_get_user = cog_module.get_user

    async def user_then_delete(discord_id):
        user = await original_get_user(discord_id)
        await delete_user_data(discord_id)
        return user

    monkeypatch.setattr(cog_module, "get_user", user_then_delete)
    translator = NS(text=lambda locale, key, **kwargs: key)
    bot = NS(register_component=lambda *args: None, translator=translator)
    cog = AccountsCog(bot)
    interaction = NS(
        user=NS(id=owner.id),
        client=bot,
        locale=discord.Locale.american_english,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await AccountsCog.account.callback(cog, interaction, "synthetic")
    assert interaction.followup.send.await_count == 1
    assert (
        interaction.followup.send.call_args.kwargs["embed"].description
        == "account-not-found"
    )


@pytest.mark.parametrize("hide", [False, True])
@pytest.mark.parametrize("ephemeral", [False, True])
async def test_account_paging_respects_current_privacy(monkeypatch, hide, ephemeral):
    import src.cogs.valorant.accounts as module

    user = NS(
        id=101,
        hide_ign=hide,
        current_account_id="0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    accounts = [
        NS(puuid=str(index), username=f"SyntheticName{index}#AUDIT")
        for index in range(26)
    ]
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module, "list_accounts", AsyncMock(return_value=accounts))
    cog = AccountsCog(
        NS(register_component=lambda *args: None, translator=BotFraggTranslator())
    )
    interaction = NS(
        user=NS(id=101),
        locale=discord.Locale.american_english,
        message=NS(flags=NS(ephemeral=ephemeral)),
        response=NS(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=NS(send=AsyncMock()),
    )
    await cog.accounts_page(interaction, "1")
    if hide and not ephemeral:
        interaction.edit_original_response.assert_not_awaited()
        result = interaction.followup.send.await_args.kwargs
        assert result["ephemeral"] is True
    else:
        interaction.followup.send.assert_not_awaited()
        result = interaction.edit_original_response.await_args.kwargs
    assert result["embed"].description == "26. SyntheticName25#AUDIT"
    assert all(control.owner_id == user.id for control in result["view"].children)


async def test_account_switch_hides_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that account switch hides name when preference enabled."""
    target = SimpleNamespace(puuid="target", username="SecretName#NA")
    user = SimpleNamespace(hide_ign=True, current_account_id="current")
    target.user = user
    target.persisted_row = lambda: NS(
        select_related=lambda *args: NS(get_or_none=AsyncMock(return_value=target))
    )
    sent: list[discord.Embed] = []

    async def list_accounts(_user_id: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        return [target]

    async def resolve_account(
        _user_id: int, _value: str, *, accounts: list[SimpleNamespace]
    ) -> SimpleNamespace:
        """Resolve the requested account from the fixture list."""
        assert accounts == [target]
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
