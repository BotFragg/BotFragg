"""Tests for alert ownership, bounded queries, batching, and delivery behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from tortoise.exceptions import IntegrityError

from src.models import (
    Account,
    Alert,
    User,
)
from src.services import alerts as alert_service
from src.services.accounts import (
    delete_user_data,
    get_user,
    list_accounts,
    selected_account,
)
from src.services.alerts import (
    account_ids_with_alerts,
    create_alert,
    list_alerts_page,
    matching_alerts_for_skins,
    remove_alert,
    run_daily_alerts,
    user_ids_with_alerts,
)
from src.services.auth import AuthenticationRequired, AuthService
from src.services.catalog import (
    Skin,
)
from src.services.crypto import AuthVault
from src.services.shop import (
    Offer,
    ShopData,
    ShopService,
    ShopUnavailable,
)


@pytest.mark.usefixtures("database")
async def test_create_alert_returns_existing_record_for_duplicate() -> None:
    """Verify that creating a duplicate alert returns the existing record."""
    user = await User.create(id=321)
    first = await Account.create(puuid="first", user=user, username="First#NA")
    second = await Account.create(puuid="second", user=user, username="Second#NA")
    other = await User.create(id=325)
    skin_uuid = UUID(int=1)

    alert, created = await create_alert(user.id, first, skin_uuid)
    duplicate, duplicate_created = await create_alert(user.id, first, skin_uuid)
    other_account_alert, other_account_created = await create_alert(
        user.id, second, skin_uuid
    )

    assert created
    assert not duplicate_created
    assert duplicate.id == alert.id
    assert other_account_created
    assert other_account_alert.id != alert.id
    with pytest.raises(ValueError, match="Account does not belong"):
        await create_alert(other.id, first, skin_uuid)


@pytest.mark.usefixtures("database")
async def test_remove_alert_is_scoped_to_owner() -> None:
    """Verify that remove alert is scoped to owner."""
    owner = await User.create(id=322)
    owner_account = await Account.create(puuid="owned", user=owner, username="Owner#NA")
    other = await User.create(id=323)
    alert = await Alert.create(account=owner_account, skin_uuid=UUID(int=2))

    assert await remove_alert(other.id, alert.id) is None
    assert await Alert.filter(id=alert.id).exists()
    assert await remove_alert(owner.id, alert.id) is not None
    assert not await Alert.filter(id=alert.id).exists()


@pytest.mark.usefixtures("database")
async def test_alert_job_queries_are_bounded_to_users_accounts_and_skins() -> None:
    """Verify that alert job queries are bounded to users accounts and skins."""
    owner = await User.create(id=326)
    first = await Account.create(puuid="notify-first", user=owner, username="One#NA")
    second = await Account.create(puuid="notify-second", user=owner, username="Two#NA")
    other = await User.create(id=327)
    other_account = await Account.create(
        puuid="notify-other", user=other, username="Other#NA"
    )
    first_skin = UUID(int=3)
    second_skin = UUID(int=4)
    await Alert.create(account=first, skin_uuid=first_skin)
    await Alert.create(account=first, skin_uuid=second_skin)
    await Alert.create(account=second, skin_uuid=first_skin)
    await Alert.create(account=other_account, skin_uuid=first_skin)

    assert await user_ids_with_alerts() == {owner.id, other.id}
    assert await account_ids_with_alerts([first.puuid, second.puuid]) == {
        first.puuid,
        second.puuid,
    }
    matches = await matching_alerts_for_skins(first, [str(first_skin)])
    assert [alert.skin_uuid for alert in matches] == [first_skin]
    assert await account_ids_with_alerts([]) == set()
    assert await matching_alerts_for_skins(first, []) == []


async def test_alert_page_uses_a_bounded_owner_scoped_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that alert page uses a bounded owner scoped query."""
    rows = [SimpleNamespace(id=index) for index in range(1, 51)]
    filters: dict[str, int] = {}

    class Query:
        """Capture query filters and pagination bounds, including rows removed between count and fetch."""

        offset_value = 0
        limit_value = 0

        def order_by(self, *_args: object) -> Query:
            """Record the requested ordering and return this query stub."""
            return self

        async def count(self) -> int:
            """Return the number of rows represented by this query stub."""
            return len(rows)

        def offset(self, value: int) -> Query:
            """Set the query offset and return this query stub."""
            self.offset_value = value
            return self

        def limit(self, value: int) -> Query:
            """Set the query limit and return this query stub."""
            self.limit_value = value
            return self

        def __await__(self):
            """Make the query stub awaitable and yield its configured rows."""

            async def fetch() -> list[object]:
                """Return the configured result from the fake query or HTTP client."""
                return rows[self.offset_value : self.offset_value + self.limit_value]

            return fetch().__await__()

    query = Query()

    def filter_alerts(_cls, **query_filters):
        """Filter the fake alert query by the requested accounts and skins."""
        filters.update(query_filters)
        return query

    monkeypatch.setattr(
        Alert,
        "filter",
        classmethod(filter_alerts),
    )

    result = await list_alerts_page(user_id=324, page=1, page_size=100)

    assert filters == {"account__user_id": 324}
    assert (query.offset_value, query.limit_value) == (20, 20)
    assert (result.total, result.page, result.pages, result.page_size) == (50, 1, 3, 20)
    assert [alert.id for alert in result.alerts] == list(range(21, 41))


def shop_data(*skin_uuids: str) -> ShopData:
    """Build a shop fixture containing offers for the supplied skin identifiers."""
    return ShopData(
        offers=[
            Offer(
                skin=SimpleNamespace(uuid=skin_uuid, name=skin_uuid, icon=None),
                price=1,
                expires=100,
            )
            for skin_uuid in skin_uuids
        ],
        accessory=[],
        night_market=[],
        expires=100,
        night_market_expires=None,
    )


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("dry_run", [False, True])
async def test_daily_summary_separates_credentials_and_delivery_failures(dry_run):
    user = await User.create(
        id=101, daily_shop_enabled=True, current_account_id="daily"
    )
    daily = await Account.create(puuid="daily", user=user, username="Daily#NA")
    expired = await Account.create(puuid="expired", user=user, username="Expired#NA")
    skin = UUID(int=1)
    await Alert.create(account=daily, skin_uuid=skin)
    await Alert.create(account=expired, skin_uuid=skin)

    async def storefront(account, *, use_cache):
        if account.puuid == expired.puuid:
            raise AuthenticationRequired("expired")
        return shop_data(str(skin))

    delivery = AsyncMock(return_value=2)
    notice = AsyncMock(return_value=1)
    summary = await run_daily_alerts(
        SimpleNamespace(storefront=storefront),
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
        dry_run=dry_run,
        on_shop=delivery,
        on_credentials_expired=notice,
    )
    assert summary == {
        "users": 1,
        "shops": 1,
        "alerts": 1,
        "failures": 1 if dry_run else 4,
        "expired_logins": 1,
        "shop_failures": 0,
        "delivery_failures": 0 if dry_run else 3,
    }
    from src.monitoring import _scrub

    assert _scrub(summary) == summary
    if dry_run:
        delivery.assert_not_awaited()
        notice.assert_not_awaited()
    else:
        delivery.assert_awaited_once()
        notice.assert_awaited_once_with(user.id)


@pytest.mark.usefixtures("database")
async def test_daily_alert_run_preserves_selection_summary_and_batches_alert_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that daily alert run preserves selection summary and batches alert presence."""
    user = await User.create(
        id=901, current_account_id="daily", daily_shop_enabled=True
    )
    daily = await Account.create(puuid="daily", user=user, username="Daily#NA")
    matching = await Account.create(puuid="matching", user=user, username="Matching#NA")
    no_match = await Account.create(puuid="no-match", user=user, username="NoMatch#NA")
    unused = await Account.create(puuid="unused", user=user, username="Unused#NA")
    other_user = await User.create(id=902)
    failing = await Account.create(
        puuid="failing", user=other_user, username="Failing#NA"
    )

    first_skin = UUID(int=1)
    second_skin = UUID(int=2)
    no_match_skin = UUID(int=3)
    failed_skin = UUID(int=4)
    daily_skin = UUID(int=5)
    daily_alert = await Alert.create(account=daily, skin_uuid=daily_skin)
    first_alert = await Alert.create(account=matching, skin_uuid=first_skin)
    second_alert = await Alert.create(account=matching, skin_uuid=second_skin)
    await Alert.create(account=no_match, skin_uuid=no_match_skin)
    await Alert.create(account=failing, skin_uuid=failed_skin)

    original_filter = Alert.filter
    batched_account_ids: list[list[str]] = []

    def tracked_filter(cls, **filters):
        """Capture filters used to select accounts that have alerts."""
        if "account_id__in" in filters:
            batched_account_ids.append(list(filters["account_id__in"]))
        return original_filter(**filters)

    monkeypatch.setattr(Alert, "filter", classmethod(tracked_filter))

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        def __init__(self) -> None:
            """Start storefront-call tracking before the alert job runs."""
            self.calls: list[tuple[int, str, bool]] = []

        async def storefront(self, account, *, use_cache=True):
            """Return the configured storefront fixture for the requested account."""
            self.calls.append((account.user_id, account.puuid, use_cache))
            if account.puuid == failing.puuid:
                raise AuthenticationRequired("credentials expired")
            if account.puuid == daily.puuid:
                return shop_data(str(daily_skin))
            if account.puuid == matching.puuid:
                return shop_data(str(first_skin), str(second_skin))
            if account.puuid == no_match.puuid:
                return shop_data(str(first_skin))
            return shop_data(str(first_skin))

    shop = Shop()
    outcomes: list[tuple[object, ...]] = []

    async def on_shop(user_id, _user, account, _shop, alerts, send_daily_shop):
        """Capture arguments passed to the daily-shop delivery callback."""
        outcomes.append(
            (
                "shop",
                user_id,
                account.puuid,
                [alert.id for alert, _offer in alerts],
                send_daily_shop,
            )
        )
        return 0

    async def on_credentials_expired(user_id):
        """Capture expired-credential callback invocations."""
        outcomes.append(("credentials", user_id))
        return 0

    summary = await run_daily_alerts(
        shop,
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
        dry_run=False,
        on_shop=on_shop,
        on_credentials_expired=on_credentials_expired,
    )

    assert summary == {
        "users": 2,
        "shops": 3,
        "alerts": 3,
        "failures": 1,
        "expired_logins": 1,
        "shop_failures": 0,
        "delivery_failures": 0,
    }
    assert [
        account_id
        for user_id, account_id, _use_cache in shop.calls
        if user_id == user.id
    ] == [daily.puuid, matching.puuid, no_match.puuid]
    assert all(use_cache is False for _, _, use_cache in shop.calls)
    assert {account_id for _, account_id, _ in shop.calls} == {
        daily.puuid,
        matching.puuid,
        no_match.puuid,
        failing.puuid,
    }
    assert [
        outcome
        for outcome in outcomes
        if outcome[0] == "shop" and outcome[2] == daily.puuid
    ] == [("shop", user.id, daily.puuid, [daily_alert.id], True)]
    assert [
        outcome
        for outcome in outcomes
        if outcome[0] == "shop" and outcome[2] == matching.puuid
    ] == [
        (
            "shop",
            user.id,
            matching.puuid,
            [first_alert.id, second_alert.id],
            False,
        )
    ]
    assert not any(
        outcome[0] == "shop" and outcome[2] == no_match.puuid for outcome in outcomes
    )
    assert ("credentials", other_user.id) in outcomes
    assert len(batched_account_ids) == 1
    assert set(batched_account_ids[0]) == {
        daily.puuid,
        matching.puuid,
        no_match.puuid,
        unused.puuid,
        failing.puuid,
    }


@pytest.mark.usefixtures("database")
async def test_daily_alert_run_cancels_and_awaits_sibling_users_on_failure() -> None:
    """Verify that daily alert run cancels and awaits sibling users on failure."""
    first_user = await User.create(id=903)
    first = await Account.create(puuid="blocks", user=first_user, username="Blocks#NA")
    second_user = await User.create(id=904)
    second = await Account.create(puuid="fails", user=second_user, username="Fails#NA")
    await Alert.create(account=first, skin_uuid=UUID(int=11))
    await Alert.create(account=second, skin_uuid=UUID(int=12))

    sibling_started = asyncio.Event()
    sibling_cleanup_finished = asyncio.Event()

    class FailingShop:
        """Fail one storefront lookup so the alert job can verify sibling-task cancellation."""

        async def storefront(self, account, *, use_cache=True):
            """Return the configured storefront fixture for the requested account."""
            if account.puuid == second.puuid:
                await sibling_started.wait()
                raise RuntimeError("unexpected storefront failure")

            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_cleanup_finished.set()

    async def unused_callback(*_args):
        """Fail the test if an unexpected notification callback is invoked."""
        return 0

    with pytest.raises(ExceptionGroup) as raised:
        await run_daily_alerts(
            FailingShop(),
            alert_concurrency=2,
            delay_between_alerts_seconds=0,
            dry_run=True,
            on_shop=unused_callback,
            on_credentials_expired=unused_callback,
        )

    assert any(isinstance(error, RuntimeError) for error in raised.value.exceptions)
    assert sibling_cleanup_finished.is_set()


@pytest.mark.usefixtures("database")
async def test_daily_alert_run_keeps_send_and_delay_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that daily alert run keeps send and delay order."""
    user = await User.create(
        id=905, current_account_id="ordered-first", daily_shop_enabled=True
    )
    first = await Account.create(puuid="ordered-first", user=user, username="First#NA")
    second = await Account.create(
        puuid="ordered-second", user=user, username="Second#NA"
    )
    failed = await Account.create(puuid="ordered-fail", user=user, username="Fail#NA")
    first_skin = UUID(int=21)
    second_skin = UUID(int=22)
    await Alert.create(account=first, skin_uuid=first_skin)
    await Alert.create(account=second, skin_uuid=second_skin)
    await Alert.create(account=failed, skin_uuid=UUID(int=23))

    timeline: list[tuple[object, ...]] = []

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def storefront(self, account, *, use_cache=True):
            """Return the configured storefront fixture for the requested account."""
            timeline.append(("store", account.puuid))
            if account.puuid == failed.puuid:
                raise ShopUnavailable("temporarily unavailable")
            skin_uuid = first_skin if account.puuid == first.puuid else second_skin
            return shop_data(str(skin_uuid))

    async def on_shop(user_id, _user, account, _shop, _alerts, _send_daily_shop):
        """Capture arguments passed to the daily-shop delivery callback."""
        timeline.append(("send", user_id, account.puuid))
        return 0

    async def on_credentials_expired(user_id):
        """Capture expired-credential callback invocations."""
        timeline.append(("credentials", user_id))
        return 0

    async def record_delay(seconds: float) -> None:
        """Record alert delays so delivery ordering can be asserted."""
        timeline.append(("delay", seconds))

    monkeypatch.setattr(alert_service.asyncio, "sleep", record_delay)

    summary = await run_daily_alerts(
        Shop(),
        alert_concurrency=1,
        delay_between_alerts_seconds=3.0,
        dry_run=False,
        on_shop=on_shop,
        on_credentials_expired=on_credentials_expired,
    )

    assert summary == {
        "users": 1,
        "shops": 2,
        "alerts": 2,
        "failures": 1,
        "expired_logins": 0,
        "shop_failures": 1,
        "delivery_failures": 0,
    }
    assert timeline == [
        ("store", first.puuid),
        ("send", user.id, first.puuid),
        ("delay", 3.0),
        ("store", second.puuid),
        ("send", user.id, second.puuid),
        ("delay", 3.0),
        ("store", failed.puuid),
    ]


@pytest.mark.usefixtures("database")
async def test_daily_alert_auth_http_5xx_does_not_request_relogin() -> None:
    """Verify that daily alert auth HTTP 5xx does not request relogin."""
    user = await User.create(id=904, current_account_id="transient-auth")
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="transient-auth",
        user=user,
        username="Player#NA",
        auth_blob=vault.encrypt(
            {"rso": "x.eyJleHAiOjB9.x", "refresh_token": "refresh"}
        ),
    )
    await Alert.create(account=account, skin_uuid=UUID(int=24))
    credential_notices: list[int] = []

    class UnavailableHTTP:
        """Return an upstream server error to verify temporary failures do not trigger relogin notices."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(status=503, data={})

    async def unused_callback(*_args) -> int:
        """Fail the test if an unexpected notification callback is invoked."""
        return 0

    async def on_credentials_expired(user_id: int) -> int:
        """Capture expired-credential callback invocations."""
        credential_notices.append(user_id)
        return 0

    auth = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        UnavailableHTTP(),
        vault,
    )
    shop = ShopService(
        SimpleNamespace(use_shop_cache=True), UnavailableHTTP(), auth, None
    )
    summary = await run_daily_alerts(
        shop,
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
        dry_run=False,
        on_shop=unused_callback,
        on_credentials_expired=on_credentials_expired,
    )

    assert summary == {
        "users": 1,
        "shops": 0,
        "alerts": 0,
        "failures": 1,
        "expired_logins": 0,
        "shop_failures": 1,
        "delivery_failures": 0,
    }
    assert credential_notices == []


@pytest.mark.usefixtures("database")
async def test_daily_alert_run_batches_user_and_alert_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that daily alert run batches user and alert lookups."""
    user_ids = (906, 907)
    for user_id in user_ids:
        user = await User.create(id=user_id)
        account = await Account.create(
            puuid=f"benchmark-{user_id}",
            user=user,
            username=f"User{user_id}#NA",
        )
        await User.filter(id=user_id).update(current_account_id=account.puuid)
        await Alert.create(account=account, skin_uuid=UUID(int=user_id))

    query_counts = {
        "user_get": 0,
        "account_get": 0,
        "account_filter": 0,
        "alert_filter": 0,
    }
    original_user_get = User.get_or_none
    original_account_get = Account.get_or_none
    original_account_filter = Account.filter
    original_alert_filter = Alert.filter

    async def count_user_get(cls, *args, **filters):
        """Count user-record lookups during the alert run."""
        query_counts["user_get"] += 1
        return await original_user_get(*args, **filters)

    async def count_account_get(cls, *args, **filters):
        """Count account-record lookups during the alert run."""
        query_counts["account_get"] += 1
        return await original_account_get(*args, **filters)

    def count_account_queries(cls, **filters):
        """Count account query executions during the alert run."""
        if "user_id" in filters or "user_id__in" in filters:
            query_counts["account_filter"] += 1
        return original_account_filter(**filters)

    def count_alert_queries(cls, **filters):
        """Count alert query executions during the alert run."""
        if "account_id" in filters or "account_id__in" in filters:
            query_counts["alert_filter"] += 1
        return original_alert_filter(**filters)

    monkeypatch.setattr(User, "get_or_none", classmethod(count_user_get))
    monkeypatch.setattr(Account, "get_or_none", classmethod(count_account_get))
    monkeypatch.setattr(Account, "filter", classmethod(count_account_queries))
    monkeypatch.setattr(Alert, "filter", classmethod(count_alert_queries))

    for user_id in user_ids:
        user = await get_user(user_id)
        await selected_account(user_id, user=user)
        accounts = await list_accounts(user_id)
        for account in accounts:
            await Alert.filter(account_id=account.puuid).exists()
    old_query_counts = query_counts.copy()
    for query in query_counts:
        query_counts[query] = 0

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def storefront(self, _account, *, use_cache=True):
            """Return the configured storefront fixture for the requested account."""
            raise ShopUnavailable("temporarily unavailable")

    async def unused_callback(*_args):
        """Fail the test if an unexpected notification callback is invoked."""
        return 0

    await run_daily_alerts(
        Shop(),
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
        dry_run=True,
        on_shop=unused_callback,
        on_credentials_expired=unused_callback,
    )

    new_query_counts = query_counts.copy()
    assert old_query_counts == {
        "user_get": 2,
        "account_get": 2,
        "account_filter": 2,
        "alert_filter": 2,
    }
    assert new_query_counts == {
        "user_get": 0,
        "account_get": 0,
        "account_filter": 1,
        "alert_filter": 1,
    }


@pytest.mark.usefixtures("database")
async def test_daily_alert_tasks_are_bounded_by_configured_concurrency() -> None:
    """Verify that the alert job creates workers, not one task per user."""
    user_count = 8
    for index in range(user_count):
        user_id = 950 + index
        user = await User.create(id=user_id, current_account_id=f"bounded-{index}")
        account = await Account.create(
            puuid=f"bounded-{index}", user=user, username=f"User{index}#NA"
        )
        await Alert.create(account=account, skin_uuid=UUID(int=10_000 + index))

    concurrency = 2
    entered = 0
    started = asyncio.Event()
    release = asyncio.Event()

    class Shop:
        """Hold storefront workers until the test can inspect scheduled task counts."""

        async def storefront(self, _account, *, use_cache=True):
            """Wait for the test to inspect the bounded worker pool."""
            nonlocal entered
            entered += 1
            if entered == concurrency:
                started.set()
            await release.wait()
            return SimpleNamespace(offers=[])

    async def unused_callback(*_args) -> int:
        """Fail the test if an unexpected notification callback is invoked."""
        raise AssertionError("dry-run should not send notifications")

    existing_tasks = len(asyncio.all_tasks())
    job = asyncio.create_task(
        run_daily_alerts(
            Shop(),
            alert_concurrency=concurrency,
            delay_between_alerts_seconds=0,
            dry_run=True,
            on_shop=unused_callback,
            on_credentials_expired=unused_callback,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)
    new_tasks = len(asyncio.all_tasks()) - existing_tasks
    release.set()

    await asyncio.wait_for(job, timeout=1)

    assert new_tasks <= concurrency + 1


SKIN_ID = UUID("11111111-1111-4111-8111-111111111111")


async def replace_account(old, owner_id=202):
    await delete_user_data(old.user_id)
    new_owner = await User.create(id=owner_id)
    return await Account.create(
        puuid=old.puuid, user=new_owner, username="Replacement#NA"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id", [101, 202])
async def test_stale_alert_creation_cannot_mutate_relinked_account(database, owner_id):
    owner = await User.create(id=101)
    old = await Account.create(puuid="synthetic", user=owner, username="Original#NA")
    replacement = await replace_account(old, owner_id)
    with pytest.raises(ValueError, match="Account no longer exists"):
        await create_alert(owner.id, old, SKIN_ID)
    assert not await Alert.exists(account__user_id=replacement.user_id), (
        "A stale request inserted an alert for the new owner"
    )
    await create_alert(replacement.user_id, replacement, SKIN_ID)
    assert await matching_alerts_for_skins(old, [str(SKIN_ID)]) == []
    matches = await matching_alerts_for_skins(replacement, [str(SKIN_ID)])
    assert len(matches) == 1 and matches[0].account.user_id == owner_id


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id", [101, 202])
@pytest.mark.parametrize("daily_shop", [False, True])
async def test_alert_worker_does_not_deliver_replacement_owners_alerts(
    database, owner_id, daily_shop
):
    owner = await User.create(id=101, daily_shop_enabled=daily_shop)
    old = await Account.create(puuid="synthetic", user=owner, username="Original#NA")
    await Alert.create(account=old, skin_uuid=SKIN_ID)
    skin = Skin(str(SKIN_ID), "offer", "Synthetic skin", None, None)

    async def storefront(account, **kwargs):
        replacement = await replace_account(account, owner_id)
        await Alert.create(account=replacement, skin_uuid=SKIN_ID)
        return ShopData([Offer(skin, 100, 4000000000)], [], [], 4000000000, None)

    delivery = AsyncMock()
    await run_daily_alerts(
        NS(storefront=storefront),
        alert_concurrency=1,
        delay_between_alerts_seconds=0,
        dry_run=False,
        on_shop=delivery,
        on_credentials_expired=AsyncMock(),
    )
    assert delivery.await_count == 0, (
        "The old Discord owner received the replacement owner alert"
    )


async def test_alert_insert_serializes_with_deletion_and_relink(database, monkeypatch):
    owner = await User.create(id=101)
    account = await Account.create(puuid="synthetic", user=owner, username="Original")
    inserting, release = asyncio.Event(), asyncio.Event()
    original = Alert.get_or_create

    async def paused_insert(**kwargs):
        inserting.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(Alert, "get_or_create", paused_insert)
    creation = asyncio.create_task(create_alert(owner.id, account, SKIN_ID))
    await asyncio.wait_for(inserting.wait(), timeout=1)
    deletion = asyncio.create_task(replace_account(account))
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(deletion), timeout=0.05)
    finally:
        release.set()
        await asyncio.gather(creation, deletion)
    replacement = deletion.result()
    assert not await Alert.exists(account__user_id=replacement.user_id)


@pytest.mark.usefixtures("database")
async def test_alert_unique_per_account_and_skin() -> None:
    """Verify that each account can have only one alert for a given skin."""
    user = await User.create(id=456)
    account = await Account.create(puuid="account", user=user, username="One#NA")
    skin = UUID("11111111-1111-1111-1111-111111111111")
    await Alert.create(account=account, skin_uuid=skin)
    with pytest.raises(IntegrityError):
        await Alert.create(account=account, skin_uuid=skin)
