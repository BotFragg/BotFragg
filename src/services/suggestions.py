"""Persistence and orchestration for suggestions."""

from __future__ import annotations

from typing import Literal

from tortoise.transactions import in_transaction

from ..models import (
    Suggestion,
    SuggestionFollower,
)

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
