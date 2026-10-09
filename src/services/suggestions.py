"""Persistence and orchestration for suggestions."""

from __future__ import annotations

from typing import Literal

from tortoise.transactions import in_transaction

from ..models import (
    Suggestion,
    SuggestionFollower,
)
from .analytics import personal_data_write

UnfollowResult = Literal["missing", "own", "removed", "not_following"]

ReviewStatus = Literal["approved", "denied"]


async def create_suggestion(
    author_id: int, content: str, log_channel_id: int | None
) -> Suggestion | None:
    """Create a suggestion and author follow, or reject a command cancelled by deletion."""
    async with personal_data_write(author_id) as allowed, in_transaction():
        if not allowed:
            return None
        suggestion = await Suggestion.create(
            author_id=author_id, content=content, log_channel_id=log_channel_id
        )
        await SuggestionFollower.create(suggestion=suggestion, user_id=author_id)
        return suggestion


async def record_suggestion_delivery(
    suggestion: Suggestion, message_id: int
) -> Suggestion | None:
    """Record the posted message and return its current review, or None if deleted."""
    async with in_transaction():
        await Suggestion.filter(id=suggestion.id).update(log_message_id=message_id)
        return await Suggestion.get_or_none(id=suggestion.id)


async def delete_suggestion(suggestion_id: int) -> None:
    """Delete a suggestion record by its database ID."""
    await Suggestion.filter(id=suggestion_id).delete()


async def follow_suggestion(
    suggestion_id: int, user_id: int
) -> bool | Suggestion | None:
    """Follow a pending suggestion or return its completed review; missing returns None.

    Lock the suggestion until the follow commits so a concurrent review includes
    this follower, or returns its final result without creating a late follow.
    """
    async with personal_data_write(user_id) as allowed, in_transaction() as connection:
        if not allowed:
            return None
        suggestion = (
            await Suggestion.filter(id=suggestion_id)
            .using_db(connection)
            .select_for_update()
            .get_or_none()
        )
        if suggestion is None:
            return None
        if suggestion.status != "pending":
            return suggestion
        _, created = await SuggestionFollower.get_or_create(
            suggestion_id=suggestion_id, user_id=user_id, using_db=connection
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
    if not 1 <= len(reason) <= 1000:
        raise ValueError("Review reasons must contain 1-1,000 characters.")
    async with in_transaction():
        updated = await Suggestion.filter(id=suggestion_id, status="pending").update(
            status=status, reason=reason
        )
        if not updated:
            return None
        suggestion = await Suggestion.get(id=suggestion_id)
        follower_ids: set[int] = set(  # Tortoise flat=True returns scalar IDs.
            await SuggestionFollower.filter(suggestion=suggestion).values_list(
                "user_id", flat=True
            )  # type: ignore[arg-type]
        )
    return suggestion, follower_ids


async def count_suggestions_by_author(author_id: int) -> int:
    """Count suggestions submitted by a Discord user."""
    return await Suggestion.filter(author_id=author_id).count()
