"""Tests for suggestion persistence, following, and review transitions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from tortoise import Tortoise

from src.cogs.suggestions import SuggestionsCog
from src.localization import BotFraggTranslator
from src.models import Suggestion, SuggestionFollower, User
from src.services.accounts import delete_user_data
from src.services.analytics import command_analytics
from src.services.suggestions import (
    count_suggestions_by_author,
    create_suggestion,
    follow_suggestion,
    record_suggestion_delivery,
    review_suggestion,
    unfollow_suggestion,
)
from tests.helpers import _localized_bot, _localized_interaction


@pytest.mark.usefixtures("backend_database")
async def test_pending_submission_cannot_recreate_deleted_records():
    await User.create(id=101)

    class Channel(discord.abc.Messageable):
        send = AsyncMock(return_value=SimpleNamespace(id=301))

    channel = Channel()

    async def fetch_channel(_):
        await delete_user_data(101)
        return channel

    bot = _localized_bot(
        config=SimpleNamespace(suggestion_log_channel_id=201),
        get_channel=lambda _: None,
        fetch_channel=fetch_channel,
    )
    interaction = _localized_interaction(
        user=SimpleNamespace(
            id=101, display_avatar=SimpleNamespace(url="https://example.com/avatar.png")
        ),
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
        guild=None,
        guild_locale=None,
    )
    async with command_analytics(101):
        await SuggestionsCog.suggest.callback(
            SuggestionsCog(bot), interaction, "Synthetic request"
        )
    assert not await Suggestion.exists(author_id=101)
    assert not await SuggestionFollower.exists(user_id=101)
    channel.send.assert_not_awaited()
    assert interaction.followup.send.await_args.kwargs["ephemeral"]
    async with command_analytics(101):
        assert (
            await create_suggestion(101, "New request after deletion", None) is not None
        )


@pytest.mark.usefixtures("backend_database")
async def test_deletion_cancels_pending_follow_but_allows_new_follow():
    suggestion = await create_suggestion(101, "Synthetic request", None)
    async with command_analytics(202):
        await delete_user_data(202)
        assert await follow_suggestion(suggestion.id, 202) is None
    assert not await SuggestionFollower.exists(user_id=202)
    async with command_analytics(202):
        assert await follow_suggestion(suggestion.id, 202) is True


@pytest.mark.usefixtures("backend_database")
@pytest.mark.parametrize("operation", ["create", "follow"])
async def test_deletion_waits_for_active_suggestion_writes(monkeypatch, operation):
    suggestion = await create_suggestion(101, "Synthetic request", None)
    started, resume = asyncio.Event(), asyncio.Event()
    model, method = (
        (Suggestion, "create")
        if operation == "create"
        else (SuggestionFollower, "get_or_create")
    )
    original = getattr(model, method)

    async def delayed_write(*args, **kwargs):
        started.set()
        await resume.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(model, method, delayed_write)

    async def write():
        async with command_analytics(202):
            if operation == "create":
                await create_suggestion(202, "Pending request", None)
            else:
                await follow_suggestion(suggestion.id, 202)

    writing = asyncio.create_task(write())
    await asyncio.wait_for(started.wait(), 2)
    deleting = asyncio.create_task(delete_user_data(202))
    try:
        await asyncio.sleep(0)
        assert not deleting.done()
    finally:
        resume.set()
        await asyncio.wait_for(asyncio.gather(writing, deleting), 2)
    assert not await Suggestion.exists(author_id=202)
    assert not await SuggestionFollower.exists(user_id=202)


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("status", ["approved", "denied"])
async def test_review_during_submission_notifies_author_and_updates_post(status):
    message = SimpleNamespace(id=301, edit=AsyncMock())
    author = SimpleNamespace(
        id=101,
        display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
        send=AsyncMock(),
    )
    review_interaction = _localized_interaction(
        user=SimpleNamespace(id=999),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    class Channel(discord.abc.Messageable):
        async def send(self, **kwargs):
            suggestion = await Suggestion.get(author_id=author.id)
            await cog._review_suggestion(
                review_interaction, suggestion.id, "Decision reason", status
            )
            return message

        async def fetch_message(self, message_id):
            assert message_id == message.id
            return message

    channel = Channel()
    cog = SuggestionsCog(
        _localized_bot(
            config=SimpleNamespace(suggestion_log_channel_id=201),
            get_channel=lambda _: channel,
            get_user=lambda _: author,
            is_owner=AsyncMock(return_value=True),
        )
    )
    interaction = _localized_interaction(
        user=author,
        guild_locale=None,
        guild=None,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await SuggestionsCog.suggest.callback(cog, interaction, "A request")

    author.send.assert_awaited_once()
    assert "Decision reason" in author.send.call_args.kwargs["embed"].description
    message.edit.assert_awaited_once()
    card = message.edit.call_args.kwargs["embed"]
    assert status.title() in card.title and "Decision reason" in card.description
    assert (await Suggestion.get(author_id=author.id)).log_message_id == message.id


@pytest.mark.usefixtures("database")
async def test_author_follow_failure_rolls_back_submission(monkeypatch):
    monkeypatch.setattr(
        SuggestionFollower, "create", AsyncMock(side_effect=RuntimeError("failure"))
    )
    with pytest.raises(RuntimeError, match="failure"):
        await create_suggestion(101, "A request", 201)
    assert not await Suggestion.exists()


@pytest.mark.usefixtures("database")
async def test_delivery_does_not_recreate_deleted_author_follow():
    suggestion = await create_suggestion(101, "A request", 201)
    await SuggestionFollower.filter(user_id=101).delete()
    await record_suggestion_delivery(suggestion, 301)
    assert not await SuggestionFollower.exists()
    await suggestion.delete()
    assert await record_suggestion_delivery(suggestion, 301) is None


@pytest.mark.usefixtures("database")
async def test_failed_post_removes_suggestion_and_author_follow():
    class Channel(discord.abc.Messageable):
        async def send(self, **kwargs):
            assert await SuggestionFollower.filter(user_id=101).exists()
            raise discord.HTTPException(
                SimpleNamespace(status=503, reason="Failed"), ""
            )

    cog = SuggestionsCog(
        _localized_bot(
            config=SimpleNamespace(suggestion_log_channel_id=201),
            get_channel=lambda _: Channel(),
        )
    )
    interaction = _localized_interaction(
        user=SimpleNamespace(
            id=101, display_avatar=SimpleNamespace(url="https://example.com/avatar.png")
        ),
        guild_locale=None,
        guild=None,
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await SuggestionsCog.suggest.callback(cog, interaction, "A request")
    assert not await Suggestion.exists() and not await SuggestionFollower.exists()
    sent = interaction.followup.send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert sent["embed"].description == cog.bot.translator.text(
        interaction.locale, "suggestion-delivery-failed"
    )


@pytest.mark.parametrize("first", ["follow", "review"])
async def test_follow_and_review_serialize_without_losing_notification(
    first, postgres_url, monkeypatch
):
    await Tortoise.init(
        db_url=postgres_url, modules={"models": ["src.models.entities"]}
    )
    await Tortoise.generate_schemas()
    suggestion = await create_suggestion(101, "A request", None)
    locked = asyncio.Event()
    release = asyncio.Event()
    model = SuggestionFollower if first == "follow" else Suggestion
    method = "get_or_create" if first == "follow" else "get"
    original = getattr(model, method)

    async def pause_after_lock(*args, **kwargs):
        locked.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(model, method, pause_after_lock)
    async with asyncio.TaskGroup() as group:
        first_task = group.create_task(
            follow_suggestion(suggestion.id, 202)
            if first == "follow"
            else review_suggestion(suggestion.id, "approved", "Reason")
        )
        await asyncio.wait_for(locked.wait(), 2)
        second_task = group.create_task(
            review_suggestion(suggestion.id, "approved", "Reason")
            if first == "follow"
            else follow_suggestion(suggestion.id, 202)
        )
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(second_task), 0.05)
        finally:
            release.set()
        await asyncio.wait_for(asyncio.gather(first_task, second_task), 2)

    followed, reviewed = (
        (first_task.result(), second_task.result())
        if first == "follow"
        else (second_task.result(), first_task.result())
    )
    assert reviewed is not None
    if first == "follow":
        assert followed is True
        assert reviewed[1] == {101, 202}
        assert await SuggestionFollower.filter(suggestion_id=suggestion.id).count() == 2
    else:
        assert isinstance(followed, Suggestion) and followed.status == "approved"
        assert reviewed[1] == {101}
        assert not await SuggestionFollower.filter(
            suggestion_id=suggestion.id, user_id=202
        ).exists()


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("status", ["approved", "denied"])
async def test_tracking_reviewed_suggestion_shows_result_without_adding_follow(status):
    suggestion = await create_suggestion(101, "A request", None)
    await review_suggestion(suggestion.id, status, "Decision reason")
    interaction = _localized_interaction(
        user=SimpleNamespace(id=202),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    cog = SuggestionsCog(_localized_bot())

    await SuggestionsCog.track.callback(cog, interaction, suggestion.id)

    assert not await SuggestionFollower.filter(
        suggestion_id=suggestion.id, user_id=202
    ).exists()
    interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
    sent = interaction.followup.send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert "Decision reason" in sent["embed"].description
    assert "A request" in sent["embed"].description
    assert (
        cog.bot.translator.text(interaction.locale, f"suggestion-status-{status}")
        in sent["embed"].description
    )


@pytest.mark.parametrize("command", ["approve", "deny"])
async def test_non_owner_review_is_rejected_before_writing(command, monkeypatch):
    review = AsyncMock()
    monkeypatch.setattr("src.cogs.suggestions.review_suggestion", review)
    bot = _localized_bot(is_owner=AsyncMock(return_value=False))
    interaction = _localized_interaction(
        user=SimpleNamespace(id=202),
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    cog = SuggestionsCog(bot)
    await getattr(SuggestionsCog, command).callback(cog, interaction, 1, "Reason")
    review.assert_not_awaited()
    sent = interaction.followup.send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert sent["embed"].description == bot.translator.text(
        interaction.locale, "suggestion-owner-only"
    )


@pytest.mark.usefixtures("database")
async def test_submission_persists_delivery_with_author_already_following() -> None:
    """Verify that the author follows before delivery and the message is recorded."""
    suggestion = await create_suggestion(101, "Add a feature", 201)

    assert await SuggestionFollower.filter(
        suggestion_id=suggestion.id, user_id=101
    ).exists()
    delivered = await record_suggestion_delivery(suggestion, message_id=301)
    assert delivered is not None and delivered.log_message_id == 301

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
    assert await SuggestionFollower.filter(suggestion=suggestion).count() == 2


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
    assert follower_ids == {104, 204, 205}
    assert await review_suggestion(suggestion.id, "denied", "Too late") is None


@pytest.mark.usefixtures("database")
async def test_long_review_reason_is_rejected_before_persisting():
    suggestion = await Suggestion.create(author_id=105, content="C" * 1000)
    await SuggestionFollower.create(suggestion=suggestion, user_id=105)
    recipient = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(
        is_owner=AsyncMock(return_value=True),
        get_user=lambda _: recipient,
        translator=BotFraggTranslator(),
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=999),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await SuggestionsCog(bot)._review_suggestion(
        interaction, suggestion.id, "R" * 3000, "approved"
    )
    assert recipient.send.call_count == 0
    assert (await Suggestion.get(id=suggestion.id)).status == "pending"
