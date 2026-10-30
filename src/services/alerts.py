"""Persistence and orchestration for alerts."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from uuid import UUID

from tortoise.transactions import in_transaction

from ..database import TRANSIENT_DATABASE_ERRORS
from ..models import (
    Account,
    Alert,
    User,
)
from .accounts import daily_shop_user_ids, selected_account
from .auth import AuthenticationRequired
from .http import RateLimited
from .shop import Offer, ShopData, ShopService, ShopUnavailable

MAX_ALERTS_PER_PAGE = 20
# A long Riot cooldown is reported as a failure instead of stalling the daily run.
MAX_RATE_LIMIT_WAIT_SECONDS = 120


@dataclass(slots=True)
class AlertPage:
    """Hold one bounded page of alerts and its normalized pagination metadata."""

    alerts: list[Alert]
    total: int
    page: int
    pages: int
    page_size: int
    start: int = 1


async def create_alert(
    user_id: int, account: Account, skin_uuid: UUID
) -> tuple[Alert, bool]:
    """Create an account-scoped skin alert or return the existing duplicate."""
    if account.user_id != user_id:
        raise ValueError("Account does not belong to this Discord user")
    async with in_transaction() as connection:
        current = (
            await account.persisted_row()
            .using_db(connection)
            .select_for_update()
            .get_or_none()
        )
        if current is None:
            raise ValueError("Account no longer exists")
        return await Alert.get_or_create(
            account=current, skin_uuid=skin_uuid, using_db=connection
        )


async def _alert_boundary_page(
    user_id: int,
    anchor_id: int,
    page_size: int,
    *,
    forward: bool,
    inclusive: bool = False,
) -> list[Alert]:
    """Return the page that starts at, after, or before one alert ID."""
    if forward:
        boundary = {"id__gte": anchor_id} if inclusive else {"id__gt": anchor_id}
        return await (
            Alert.filter(account__user_id=user_id, **boundary)
            .order_by("id")
            .limit(page_size)
        )
    rows = await (
        Alert.filter(account__user_id=user_id, id__lt=anchor_id)
        .order_by("-id")
        .limit(page_size)
    )
    return list(reversed(rows))


async def list_alerts_page(
    user_id: int,
    page: int,
    page_size: int,
    *,
    anchor_id: int | None = None,
    forward: bool = True,
    inclusive: bool = False,
) -> AlertPage:
    """Fetch an owner-scoped alert page, wrapping page indexes and bounding size.

    When ``anchor_id`` is given the page is anchored to that alert instead of a row
    offset, so an alert removed from another view cannot shift the page and skip a
    row. ``forward`` selects the page after or before the anchor; paging past either
    end wraps around. ``inclusive`` keeps the anchor itself, which re-renders the
    same window after one of its rows is removed.
    """
    page_size = max(1, min(page_size, MAX_ALERTS_PER_PAGE))
    rows = Alert.filter(account__user_id=user_id)
    total = await rows.count()
    if not total:
        return AlertPage([], 0, 0, 0, page_size)
    pages = (total + page_size - 1) // page_size

    if anchor_id is None:
        page %= pages
        start = page * page_size + 1
        alerts = await rows.order_by("id").offset(page * page_size).limit(page_size)
    else:
        alerts = await _alert_boundary_page(
            user_id, anchor_id, page_size, forward=forward, inclusive=inclusive
        )
        if alerts:
            start = (
                await Alert.filter(
                    account__user_id=user_id, id__lt=alerts[0].id
                ).count()
                + 1
            )
            page = (start - 1) // page_size
        else:
            page = 0 if forward else pages - 1
            start = page * page_size + 1
            alerts = await rows.order_by("id").offset(page * page_size).limit(page_size)
    if not alerts:
        total = await rows.count()
        if not total:
            return AlertPage([], 0, 0, 0, page_size)
        pages = (total + page_size - 1) // page_size
        page %= pages
        start = page * page_size + 1
        alerts = await rows.order_by("id").offset(page * page_size).limit(page_size)

    return AlertPage(alerts, total, page, pages, page_size, start)


async def remove_alert(user_id: int, alert_id: int) -> Alert | None:
    """Delete and return an alert only when it belongs to the requesting user."""
    alert = await Alert.get_or_none(id=alert_id, account__user_id=user_id)
    if alert:
        await alert.delete()
    return alert


async def first_alert(user_id: int) -> Alert | None:
    """Return a user's first alert with its linked account loaded."""
    return (
        await Alert.filter(account__user_id=user_id).prefetch_related("account").first()
    )


async def user_ids_with_alerts() -> set[int]:
    """Return distinct Discord IDs that own at least one alert."""
    # Tortoise's annotation describes tuples even when flat=True returns scalars.
    return set(await Alert.all().distinct().values_list("account__user_id", flat=True))  # type: ignore[arg-type]


async def account_ids_with_alerts(account_ids: list[str]) -> set[str]:
    """Return only the supplied account IDs that currently have alerts."""
    if not account_ids:
        return set()
    return set(  # Tortoise flat=True returns scalar IDs, not tuples.
        await Alert.filter(account_id__in=account_ids).values_list(
            "account_id", flat=True
        )  # type: ignore[arg-type]
    )


async def matching_alerts_for_skins(
    account: Account, skin_uuids: list[str]
) -> list[Alert]:
    """Fetch alerts matching one account and a bounded set of shop skin IDs."""
    if not skin_uuids:
        return []
    return await Alert.filter(
        account_id=account.puuid,
        account__user_id=account.user_id,
        account__created_at=account.created_at,
        skin_uuid__in=skin_uuids,
    ).select_related("account")


ShopOutcomeHandler = Callable[
    [int, User | None, Account, ShopData, list[tuple[Alert, Offer]], bool],
    Awaitable[int],
]

CredentialsExpiredHandler = Callable[[int], Awaitable[int]]


async def _retry_lookup[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Retry transient lookups up to three times without replaying deliveries.

    Short host cooldowns are waited out; longer ones raise so the run can finish
    and report the affected accounts as failures.
    """
    for _ in range(2):
        try:
            return await operation()
        except TRANSIENT_DATABASE_ERRORS:
            delay = 5.0
        except ShopUnavailable as exc:
            if not isinstance(exc.__cause__, RateLimited):
                raise
            if exc.__cause__.retry_after > MAX_RATE_LIMIT_WAIT_SECONDS:
                raise
            delay = exc.__cause__.retry_after
        await asyncio.sleep(delay)
    return await operation()


async def run_daily_alerts(
    shop: ShopService,
    *,
    alert_concurrency: int,
    delay_between_alerts_seconds: float,
    dry_run: bool,
    on_shop: ShopOutcomeHandler,
    on_credentials_expired: CredentialsExpiredHandler,
) -> dict[str, int]:
    """Check eligible accounts with bounded concurrency and report run totals.

    ``dry_run`` performs the lookups without sending notifications. The callbacks
    handle successful shops and expired credentials and return delivery failure
    counts. Totals distinguish expired credentials, shop and delivery failures;
    ``failures`` is their sum.
    """
    user_ids = await _retry_lookup(user_ids_with_alerts)
    user_ids.update(await _retry_lookup(daily_shop_user_ids))
    summary = {
        "users": len(user_ids),
        "shops": 0,
        "alerts": 0,
        "failures": 0,
        "expired_logins": 0,
        "shop_failures": 0,
        "delivery_failures": 0,
    }

    accounts_by_user: dict[int, list[Account]] = defaultdict(list)
    # ponytail: materialize eligible accounts; page users if measured memory grows.
    accounts = (
        await _retry_lookup(
            lambda: (
                Account.filter(user_id__in=user_ids)
                .select_related("user")
                .order_by("created_at")
            )
        )
        if user_ids
        else []
    )
    for account in accounts:
        accounts_by_user[account.user_id].append(account)
    alerted_accounts = await _retry_lookup(
        lambda: account_ids_with_alerts([account.puuid for account in accounts])
    )

    async def process(user_id: int) -> None:
        """Check one user's accounts and dispatch any matching shop results."""
        user_accounts = accounts_by_user.get(user_id, [])
        user = user_accounts[0].user if user_accounts else None
        current = (
            await _retry_lookup(
                lambda: selected_account(user_id, user=user, accounts=user_accounts)
            )
            if user
            else None
        )
        notified_expired = False
        for account in user_accounts:
            has_alerts = account.puuid in alerted_accounts
            send_daily_shop = bool(
                user
                and user.daily_shop_enabled
                and account.puuid == getattr(current, "puuid", None)
            )
            if not has_alerts and not send_daily_shop:
                continue

            try:
                storefront = await _retry_lookup(
                    partial(shop.storefront, account, use_cache=False)
                )
            except AuthenticationRequired:
                summary["expired_logins"] += 1
                if (
                    not dry_run
                    and not notified_expired
                    and await _retry_lookup(account.persisted_row().exists)
                ):
                    # Await into a local: `+= await f()` races with other workers.
                    expired = await on_credentials_expired(user_id)
                    summary["delivery_failures"] += expired
                    notified_expired = True
                continue
            except ShopUnavailable:
                summary["shop_failures"] += 1
                continue

            summary["shops"] += 1
            current_account = await _retry_lookup(
                account.persisted_row().select_related("user").get_or_none
            )
            if current_account is None:
                continue
            send_daily_shop = bool(
                send_daily_shop
                and current_account.user.daily_shop_enabled
                and current_account.user.current_account_id == account.puuid
            )
            offers_by_uuid = {offer.skin.uuid: offer for offer in storefront.offers}
            matches = (
                await _retry_lookup(
                    partial(matching_alerts_for_skins, account, list(offers_by_uuid))
                )
                if has_alerts
                else []
            )
            summary["alerts"] += len(matches)

            if not dry_run and (matches or send_daily_shop):
                # Await into a local: `+= await f()` races with other workers.
                failed = await on_shop(
                    user_id,
                    current_account.user,
                    current_account,
                    storefront,
                    [
                        (alert, offers_by_uuid[str(alert.skin_uuid)])
                        for alert in matches
                    ],
                    send_daily_shop,
                )
                summary["delivery_failures"] += failed
            if delay_between_alerts_seconds:
                await asyncio.sleep(delay_between_alerts_seconds)

    user_iterator = iter(user_ids)

    async def worker() -> None:
        """Process users from the shared iterator until it is exhausted."""
        for user_id in user_iterator:
            try:
                await process(user_id)
            except TRANSIENT_DATABASE_ERRORS:
                # Replaying the whole run would resend notifications already delivered.
                summary["shop_failures"] += 1

    async with asyncio.TaskGroup() as task_group:
        for _ in range(min(alert_concurrency, len(user_ids))):
            task_group.create_task(worker())

    summary["failures"] = (
        summary["expired_logins"]
        + summary["shop_failures"]
        + summary["delivery_failures"]
    )
    return summary
