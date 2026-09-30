"""Tests for suggestion persistence, following, and review transitions."""

from __future__ import annotations

import pytest

from src.models import Suggestion, SuggestionFollower
from src.services.accounts import (
    count_suggestions_by_author,
    create_suggestion,
    follow_suggestion,
    record_suggestion_delivery,
    review_suggestion,
    unfollow_suggestion,
)


@pytest.mark.usefixtures("database")
async def test_submission_persists_delivery_and_author_follow_atomically() -> None:
    """Verify that submission persists delivery and author follow atomically."""
    suggestion = await create_suggestion(101, "Add a feature", 201)

    await record_suggestion_delivery(suggestion, message_id=301)

    saved = await Suggestion.get(id=suggestion.id)
    follower = await SuggestionFollower.get(suggestion_id=suggestion.id)
    assert (saved.log_channel_id, saved.log_message_id) == (201, 301)
    assert follower.user_id == 101
    assert await count_suggestions_by_author(101) == 1


@pytest.mark.usefixtures("database")
async def test_follow_suggestion_is_idempotent_and_scoped() -> None:
    """Verify that follow suggestion is idempotent and scoped."""
    suggestion = await create_suggestion(102, "A request", None)

    assert await follow_suggestion(suggestion.id, 202) is True
    assert await follow_suggestion(suggestion.id, 202) is False
    assert await follow_suggestion(999, 202) is None
    assert await SuggestionFollower.filter(suggestion=suggestion).count() == 1


@pytest.mark.usefixtures("database")
async def test_unfollow_suggestion_reports_domain_outcomes() -> None:
    """Verify that unfollow suggestion reports domain outcomes."""
    suggestion = await create_suggestion(103, "A request", None)
    await follow_suggestion(suggestion.id, 203)

    assert await unfollow_suggestion(999, 203) == "missing"
    assert await unfollow_suggestion(suggestion.id, 103) == "own"
    assert await unfollow_suggestion(suggestion.id, 203) == "removed"
    assert await unfollow_suggestion(suggestion.id, 203) == "not_following"


@pytest.mark.usefixtures("database")
async def test_review_updates_pending_suggestion_once_and_returns_followers() -> None:
    """Verify that review updates pending suggestion once and returns followers."""
    suggestion = await create_suggestion(104, "A request", None)
    await follow_suggestion(suggestion.id, 204)
    await follow_suggestion(suggestion.id, 205)

    result = await review_suggestion(suggestion.id, "approved", "Looks good")

    assert result is not None
    reviewed, follower_ids = result
    assert (reviewed.status, reviewed.reason) == ("approved", "Looks good")
    assert follower_ids == {204, 205}
    assert await review_suggestion(suggestion.id, "denied", "Too late") is None
