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


@dataclass(slots=True)
class AlertPage:
    """Hold one bounded page of alerts and its normalized pagination metadata."""

    alerts: list[Alert]
    total: int
    page: int
    pages: int
    page_size: int


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


async def list_alerts_page(user_id: int, page: int, page_size: int) -> AlertPage:
    """Fetch an owner-scoped alert page, wrapping page indexes and bounding size."""
    page_size = max(1, min(page_size, MAX_ALERTS_PER_PAGE))
    query = Alert.filter(account__user_id=user_id).order_by("id")
    total = await query.count()
    if not total:
        return AlertPage([], 0, 0, 0, page_size)

    pages = (total + page_size - 1) // page_size
    page %= pages
    alerts = await query.offset(page * page_size).limit(page_size)
    if not alerts:
        total = await query.count()
        if not total:
            return AlertPage([], 0, 0, 0, page_size)
        pages = (total + page_size - 1) // page_size
        page %= pages
        alerts = await query.offset(page * page_size).limit(page_size)

    return AlertPage(alerts, total, page, pages, page_size)


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
    """Retry transient lookups up to three times without replaying deliveries."""
    for _ in range(2):
        try:
            return await operation()
        except TRANSIENT_DATABASE_ERRORS:
            delay = 5.0
        except ShopUnavailable as exc:
            if not isinstance(exc.__cause__, RateLimited):
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
                if not dry_run and await _retry_lookup(account.persisted_row().exists):
                    summary["delivery_failures"] += await on_credentials_expired(
                        user_id
                    )
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
                summary["delivery_failures"] += await on_shop(
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
