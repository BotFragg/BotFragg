"""Behavior checks for accounts service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.models import (
    Account,
    User,
)
from src.services import accounts as accounts_service
from src.services.accounts import (
    account_for_user,
    count_registered_users,
    daily_shop_user_ids,
    get_user,
    select_account,
    selected_account,
    update_user_preference,
)


@pytest.mark.usefixtures("database")
async def test_account_selection_preserves_invariant() -> None:
    """Verify that account selection preserves invariant."""
    user = await User.create(id=123)
    first = await Account.create(
        puuid="first", user=user, username="One#NA", region="na"
    )
    second = await Account.create(
        puuid="second", user=user, username="Two#EU", region="eu"
    )
    assert (await selected_account(user.id)).puuid == first.puuid
    resolved = await account_for_user(user.id, first.puuid)
    assert resolved is not None and resolved.puuid == first.puuid
    assert await account_for_user(999, first.puuid) is None
    await select_account(user.id, second)
    assert (await selected_account(user.id)).puuid == second.puuid


@pytest.mark.usefixtures("database")
async def test_selected_account_updates_user_timestamp() -> None:
    """Verify that selected account updates user timestamp."""
    user = await User.create(id=127)
    account = await Account.create(puuid="fallback", user=user, username="One#NA")
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    result = await selected_account(user.id)

    saved = await User.get(id=user.id)
    assert result is not None and result.puuid == account.puuid
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_user_preference_updates_user_timestamp() -> None:
    """Verify that user preference updates user timestamp."""
    user = await User.create(id=128)
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    assert await update_user_preference(user.id, "hide_ign", True)

    saved = await User.get(id=user.id)
    assert saved.hide_ign
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_select_account_updates_user_timestamp() -> None:
    """Verify that select account updates user timestamp."""
    user = await User.create(id=129)
    account = await Account.create(puuid="selected", user=user, username="One#NA")
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    await select_account(user.id, account)

    saved = await User.get(id=user.id)
    assert saved.current_account_id == account.puuid
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_user_preference_service_validates_and_updates_fields() -> None:
    """Verify that user preference service validates and updates fields."""
    user = await User.create(id=125)
    await User.create(id=126, daily_shop_enabled=True)

    assert await get_user(user.id) is not None
    assert await count_registered_users() == 2
    assert await daily_shop_user_ids() == {126}
    assert await update_user_preference(user.id, "hide_ign", True)
    assert (await get_user(user.id)).hide_ign is True
    assert not await update_user_preference(999, "hide_ign", True)
    with pytest.raises(ValueError, match="Unsupported user preference"):
        await update_user_preference(user.id, "auth_blob", True)


@pytest.mark.usefixtures("database")
async def test_selected_account_does_not_overwrite_concurrent_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that selected account does not overwrite concurrent selection."""
    user = await User.create(id=124)
    first = await Account.create(puuid="fallback-first", user=user, username="First#NA")
    second = await Account.create(
        puuid="fallback-second", user=user, username="Second#NA"
    )
    lookup_finished = asyncio.Event()
    continue_lookup = asyncio.Event()
    original_get_or_none = accounts_service.User.get_or_none
    lookup_count = 0

    async def paused_lookup(cls, *args, **kwargs):
        """Pause account selection until the test releases its synchronization gate."""
        nonlocal lookup_count
        result = await original_get_or_none(*args, **kwargs)
        lookup_count += 1
        if lookup_count == 1:
            lookup_finished.set()
            await continue_lookup.wait()
        return result

    monkeypatch.setattr(
        accounts_service.User, "get_or_none", classmethod(paused_lookup)
    )
    fallback = asyncio.create_task(selected_account(user.id))
    await asyncio.wait_for(lookup_finished.wait(), timeout=1)
    await select_account(user.id, second)
    continue_lookup.set()

    result = await asyncio.wait_for(fallback, timeout=1)
    saved = await User.get(id=user.id)
    assert result is not None and result.puuid == second.puuid
    assert saved.current_account_id == second.puuid
    assert first.puuid != second.puuid
