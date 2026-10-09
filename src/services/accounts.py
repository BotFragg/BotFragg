"""Persistence operations for user preferences, Riot accounts, and personal-data deletion."""

from __future__ import annotations

from collections.abc import Sequence

from tortoise import timezone
from tortoise.transactions import in_transaction

from ..models import (
    Account,
    CommandInvocation,
    Suggestion,
    SuggestionFollower,
    User,
)
from .analytics import deleting_analytics

_USER_PREFERENCE_FIELDS = frozenset(
    {"daily_shop_enabled", "hide_ign", "others_can_view_shop"}
)


async def get_user(discord_id: int) -> User | None:
    """Return the stored BotFragg user for a Discord ID, if one exists."""
    return await User.get_or_none(id=discord_id)


async def count_registered_users() -> int:
    """Count users with a stored BotFragg profile."""
    return await User.all().count()


async def daily_shop_user_ids() -> set[int]:
    """Return Discord IDs whose saved preference enables daily shop DMs."""
    # Tortoise's annotation describes tuples even when flat=True returns scalars.
    return set(await User.filter(daily_shop_enabled=True).values_list("id", flat=True))  # type: ignore[arg-type]


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
                    if account.user_id == discord_id
                    and account.puuid == user.current_account_id
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
        async with in_transaction() as connection:
            current_user = (
                await User.filter(id=discord_id, created_at=user.created_at)
                .using_db(connection)
                .select_for_update()
                .get_or_none()
            )
            if current_user is None:
                return None
            if current_user.current_account_id:
                return await account_for_user(
                    discord_id, current_user.current_account_id
                )
            current = (
                await first.persisted_row()
                .using_db(connection)
                .select_for_update()
                .get_or_none()
            )
            if current is None:
                return None
            await (
                User.filter(
                    id=discord_id,
                    created_at=user.created_at,
                    current_account_id__isnull=True,
                )
                .using_db(connection)
                .update(current_account_id=current.puuid, updated_at=timezone.now())
            )
            return current
    return None


async def list_accounts(discord_id: int) -> list[Account]:
    """Return a user's Riot accounts in creation order."""
    return await Account.filter(user_id=discord_id).order_by("created_at")


async def resolve_account(
    discord_id: int,
    query: str | None,
    *,
    accounts: Sequence[Account] | None = None,
) -> Account | None:
    """Resolve an account by PUUID, case-insensitive name, or one-based position."""
    if not query:
        return await selected_account(discord_id, accounts=accounts)
    accounts = [
        account
        for account in (
            accounts if accounts is not None else await list_accounts(discord_id)
        )
        if account.user_id == discord_id
    ]
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
    async with in_transaction() as connection:
        user = (
            await User.filter(id=discord_id)
            .using_db(connection)
            .select_for_update()
            .get_or_none()
        )
        current = (
            await account.persisted_row()
            .using_db(connection)
            .select_for_update()
            .get_or_none()
        )
        if user is None or current is None:
            raise ValueError("Account no longer exists")
        await (
            User.filter(id=discord_id)
            .using_db(connection)
            .update(current_account_id=current.puuid, updated_at=timezone.now())
        )


async def delete_user_data(discord_id: int) -> bool:
    """Delete the user's stored BotFragg records and all linked Riot accounts."""
    async with deleting_analytics(discord_id), in_transaction():
        removed = await CommandInvocation.filter(user_id=discord_id).delete()
        removed += await SuggestionFollower.filter(user_id=discord_id).delete()
        removed += await Suggestion.filter(author_id=discord_id).delete()
        removed += await User.filter(id=discord_id).delete()
    return bool(removed)
