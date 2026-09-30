"""Persistence operations for users, Riot accounts, alerts, analytics, and ideas."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from tortoise import timezone
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from ..models import (
    Account,
    Alert,
    CommandInvocation,
    Suggestion,
    SuggestionFollower,
    User,
)
from .auth import AuthenticationRequired
from .shop import Offer, ShopData, ShopService, ShopUnavailable

UserPreference = Literal["daily_shop_enabled", "hide_ign", "others_can_view_shop"]
_USER_PREFERENCE_FIELDS = frozenset(
    {"daily_shop_enabled", "hide_ign", "others_can_view_shop"}
)


async def get_user(discord_id: int) -> User | None:
    """Return the stored Botfragg user for a Discord ID, if one exists."""
    return await User.get_or_none(id=discord_id)


async def count_registered_users() -> int:
    """Count users with a stored Botfragg profile."""
    return await User.all().count()


async def daily_shop_user_ids() -> set[int]:
    """Return Discord IDs whose saved preference enables daily shop DMs."""
    return set(await User.filter(daily_shop_enabled=True).values_list("id", flat=True))


async def account_for_user(discord_id: int, puuid: str) -> Account | None:
    """Return a Riot account only when it belongs to the requested Discord user."""
    return await Account.get_or_none(puuid=puuid, user_id=discord_id)


async def update_user_preference(discord_id: int, field: str, enabled: bool) -> bool:
    """Update one allowlisted Boolean preference and refresh the user's timestamp."""
    if field not in _USER_PREFERENCE_FIELDS:
        raise ValueError(f"Unsupported user preference: {field}")
    updated = await User.filter(id=discord_id).update(
        **{field: enabled}, updated_at=timezone.now()
    )
    return bool(updated) or await User.exists(id=discord_id)


async def selected_account(
    discord_id: int,
    *,
    user: User | None = None,
    accounts: Sequence[Account] | None = None,
) -> Account | None:
    """Return the active account, choosing the oldest account when none is selected.

    A supplied user or account sequence avoids redundant queries; a supplied user
    must belong to ``discord_id``. When choosing a default, the database update is
    conditional so a concurrent selection is not overwritten.
    """
    if user is None:
        user = await User.get_or_none(id=discord_id)
    elif user.id != discord_id:
        raise ValueError("User does not match the Discord ID")
    if not user:
        return None
    if user.current_account_id:
        if accounts is not None:
            return next(
                (
                    account
                    for account in accounts
                    if account.puuid == user.current_account_id
                ),
                None,
            )
        return await account_for_user(discord_id, user.current_account_id)
    first = (
        next((account for account in accounts if account.user_id == discord_id), None)
        if accounts is not None
        else await Account.filter(user_id=discord_id).order_by("created_at").first()
    )
    if first:
        updated = await User.filter(
            id=discord_id, current_account_id__isnull=True
        ).update(current_account_id=first.puuid, updated_at=timezone.now())
        if updated:
            return first
        user = await User.get_or_none(id=discord_id)
        if user and user.current_account_id:
            if accounts is not None:
                return next(
                    (
                        account
                        for account in accounts
                        if account.puuid == user.current_account_id
                    ),
                    None,
                )
            return await account_for_user(discord_id, user.current_account_id)
        return None
    return None


async def list_accounts(discord_id: int) -> list[Account]:
    """Return a user's Riot accounts in creation order."""
    return await Account.filter(user_id=discord_id).order_by("created_at")


async def resolve_account(discord_id: int, query: str | None) -> Account | None:
    """Resolve an account by PUUID, case-insensitive name, or one-based position."""
    if not query:
        return await selected_account(discord_id)
    accounts = await list_accounts(discord_id)
    lowered = query.casefold()
    for account in accounts:
        if account.puuid == query or account.username.casefold() == lowered:
            return account
    try:
        index = int(query) - 1
    except ValueError:
        return None
    return accounts[index] if 0 <= index < len(accounts) else None


async def select_account(discord_id: int, account: Account) -> None:
    """Set a user's active account after verifying that the account is theirs."""
    if account.user_id != discord_id:
        raise ValueError("Account does not belong to this Discord user")
    await User.filter(id=discord_id).update(
        current_account_id=account.puuid, updated_at=timezone.now()
    )


async def delete_user_data(discord_id: int) -> bool:
    """Delete the user's stored Botfragg records and all linked Riot accounts."""
    async with in_transaction():
        user = await User.get_or_none(id=discord_id)
        if not user:
            return False
        await CommandInvocation.filter(user_id=discord_id).delete()
        await SuggestionFollower.filter(user_id=discord_id).delete()
        await Suggestion.filter(author_id=discord_id).delete()
        await user.delete()
    return True


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
    return await Alert.get_or_create(account=account, skin_uuid=skin_uuid)


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
    return set(await Alert.all().distinct().values_list("account__user_id", flat=True))


async def account_ids_with_alerts(account_ids: list[str]) -> set[str]:
    """Return only the supplied account IDs that currently have alerts."""
    if not account_ids:
        return set()
    return set(
        await Alert.filter(account_id__in=account_ids).values_list(
            "account_id", flat=True
        )
    )


async def matching_alerts_for_skins(
    account_id: str, skin_uuids: list[str]
) -> list[Alert]:
    """Fetch alerts matching one account and a bounded set of shop skin IDs."""
    if not skin_uuids:
        return []
    return await Alert.filter(
        account_id=account_id, skin_uuid__in=skin_uuids
    ).prefetch_related("account")


ShopOutcomeHandler = Callable[
    [int, User | None, Account, ShopData, list[tuple[Alert, Offer]], bool],
    Awaitable[None],
]
CredentialsExpiredHandler = Callable[[int], Awaitable[None]]


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
    handle successful shops and expired credentials; the returned counts include
    users, fetched shops, matched alerts, and recoverable failures.
    """
    user_ids = await user_ids_with_alerts()
    user_ids.update(await daily_shop_user_ids())
    summary = {"users": len(user_ids), "shops": 0, "alerts": 0, "failures": 0}

    accounts_by_user: dict[int, list[Account]] = defaultdict(list)
    accounts = (
        await Account.filter(user_id__in=user_ids)
        .select_related("user")
        .order_by("created_at")
        if user_ids
        else []
    )
    for account in accounts:
        accounts_by_user[account.user_id].append(account)
    alerted_accounts = await account_ids_with_alerts(
        [account.puuid for account in accounts]
    )

    semaphore = asyncio.Semaphore(alert_concurrency)

    async def process(user_id: int) -> None:
        """Check one user's accounts and dispatch any matching shop results."""
        async with semaphore:
            user_accounts = accounts_by_user.get(user_id, [])
            user = user_accounts[0].user if user_accounts else None
            current = (
                await selected_account(user_id, user=user, accounts=user_accounts)
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
                    storefront = await shop.storefront(account, use_cache=False)
                except AuthenticationRequired:
                    summary["failures"] += 1
                    if not dry_run:
                        await on_credentials_expired(user_id)
                    continue
                except ShopUnavailable:
                    summary["failures"] += 1
                    continue

                summary["shops"] += 1
                offers_by_uuid = {offer.skin.uuid: offer for offer in storefront.offers}
                matches = (
                    await matching_alerts_for_skins(account.puuid, list(offers_by_uuid))
                    if has_alerts
                    else []
                )
                summary["alerts"] += len(matches)

                if not dry_run and (matches or send_daily_shop):
                    await on_shop(
                        user_id,
                        user,
                        account,
                        storefront,
                        [
                            (alert, offers_by_uuid[str(alert.skin_uuid)])
                            for alert in matches
                        ],
                        send_daily_shop,
                    )
                if delay_between_alerts_seconds:
                    await asyncio.sleep(delay_between_alerts_seconds)

    async with asyncio.TaskGroup() as task_group:
        for user_id in user_ids:
            task_group.create_task(process(user_id))

    return summary


async def record_command_invocation(
    *,
    command: str,
    user_id: int,
    guild_id: int | None,
    channel_id: int | None,
) -> None:
    """Persist a successful command invocation with its optional Discord scope."""
    await CommandInvocation.create(
        command=command,
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id,
    )


async def command_stats(
    *, user_id: int | None = None, guild_id: int | None = None
) -> tuple[int, str | None]:
    """Return a scoped command-use count and the most-used command.

    Exactly one of ``user_id`` or ``guild_id`` is required. Ties for the most-used
    command are resolved alphabetically for stable results.
    """
    if (user_id is None) == (guild_id is None):
        raise ValueError("Provide exactly one of user_id or guild_id")

    filters = {"user_id": user_id} if user_id is not None else {"guild_id": guild_id}
    records = await (
        CommandInvocation.filter(**filters)
        .group_by("command")
        .annotate(total=Count("id"))
        .values("command", "total")
    )
    if not records:
        return 0, None

    count = sum(record["total"] for record in records)
    favorite = min(records, key=lambda record: (-record["total"], record["command"]))[
        "command"
    ]
    return count, favorite


UnfollowResult = Literal["missing", "own", "removed", "not_following"]
ReviewStatus = Literal["approved", "denied"]


async def create_suggestion(
    author_id: int, content: str, log_channel_id: int | None
) -> Suggestion:
    """Create a pending suggestion with its author and optional delivery channel."""
    return await Suggestion.create(
        author_id=author_id, content=content, log_channel_id=log_channel_id
    )


async def record_suggestion_delivery(suggestion: Suggestion, message_id: int) -> None:
    """Record the posted message and ensure the author follows the suggestion."""
    async with in_transaction():
        await Suggestion.filter(id=suggestion.id).update(log_message_id=message_id)
        await SuggestionFollower.get_or_create(
            suggestion_id=suggestion.id, user_id=suggestion.author_id
        )


async def delete_suggestion(suggestion_id: int) -> None:
    """Delete a suggestion record by its database ID."""
    await Suggestion.filter(id=suggestion_id).delete()


async def follow_suggestion(suggestion_id: int, user_id: int) -> bool | None:
    """Follow an existing suggestion, returning ``None`` when it does not exist."""
    if not await Suggestion.filter(id=suggestion_id).exists():
        return None
    _, created = await SuggestionFollower.get_or_create(
        suggestion_id=suggestion_id, user_id=user_id
    )
    return created


async def unfollow_suggestion(suggestion_id: int, user_id: int) -> UnfollowResult:
    """Remove a follow and report missing, own, removed, or absent-follow status."""
    suggestion = await Suggestion.get_or_none(id=suggestion_id)
    if not suggestion:
        return "missing"
    if suggestion.author_id == user_id:
        return "own"
    removed = await SuggestionFollower.filter(
        suggestion_id=suggestion_id, user_id=user_id
    ).delete()
    return "removed" if removed else "not_following"


async def review_suggestion(
    suggestion_id: int, status: ReviewStatus, reason: str
) -> tuple[Suggestion, set[int]] | None:
    """Atomically review a pending suggestion and return its followers once.

    A suggestion that is missing or already reviewed returns ``None``; a successful
    review returns the updated record and the distinct follower IDs to notify.
    """
    async with in_transaction():
        updated = await Suggestion.filter(id=suggestion_id, status="pending").update(
            status=status, reason=reason
        )
        if not updated:
            return None
        suggestion = await Suggestion.get(id=suggestion_id)
        follower_ids = set(
            await SuggestionFollower.filter(suggestion=suggestion).values_list(
                "user_id", flat=True
            )
        )
    return suggestion, follower_ids


async def count_suggestions_by_author(author_id: int) -> int:
    """Count suggestions submitted by a Discord user."""
    return await Suggestion.filter(author_id=author_id).count()
