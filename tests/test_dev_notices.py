"""Tests for the persisted maintenance gate and announcement delivery service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from cryptography.fernet import Fernet
from tortoise.exceptions import DBConnectionError, IntegrityError

from src.bot import BotFraggBot, BotFraggCommandTree
from src.models import (
    CommandInvocation,
    DevAnnouncement,
    DevAnnouncementRead,
    DevMaintenance,
)
from src.services.analytics import command_analytics
from src.services.dev_notices import DevNotices
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    RecordingFollowup,
    RecordingResponse,
    _localized_interaction,
    _text,
    _user,
)


def _bot(*, owner: bool = False) -> SimpleNamespace:
    """Build a fake bot with the runtime translator and an owner callback."""
    return SimpleNamespace(
        translator=TEST_TRANSLATOR,
        is_owner=AsyncMock(return_value=owner),
    )


def _service(*, owner: bool = False) -> DevNotices:
    """Build the service around a fake bot."""
    return DevNotices(_bot(owner=owner))


def _interaction(
    *,
    user_id: int = 42,
    kind: discord.InteractionType = discord.InteractionType.application_command,
    data: dict[str, object] | None = None,
    done: bool = False,
) -> tuple[SimpleNamespace, RecordingResponse, RecordingFollowup]:
    """Build a fake interaction with recording responses."""
    response = RecordingResponse(done=done)
    followup = RecordingFollowup()
    interaction = _localized_interaction(
        type=kind,
        user=_user(user_id),
        data=data or {},
        response=response,
        followup=followup,
    )
    return interaction, response, followup


@pytest.mark.usefixtures("database")
async def test_load_reads_maintenance_and_the_newest_announcement() -> None:
    """Verify that load caches the singleton maintenance row and newest notice."""
    await DevMaintenance.create(id=1, enabled=True, reason="Upgrading", updated_by=9)
    await DevAnnouncement.create(message="old", created_by=1)
    newest = await DevAnnouncement.create(message="new", created_by=2)
    service = _service()

    await service.load()

    assert service._maintenance is True
    assert service._maintenance_reason == "Upgrading"
    assert service._latest_announcement is not None
    assert service._latest_announcement.id == newest.id


@pytest.mark.usefixtures("database")
async def test_load_with_no_saved_state_leaves_the_gates_open() -> None:
    """Verify that an empty dev-notice state loads as disabled with no notice."""
    service = _service()

    await service.load()

    assert service._maintenance is False
    assert service._maintenance_reason is None
    assert service._latest_announcement is None


@pytest.mark.usefixtures("database")
async def test_pending_announcement_surfaces_only_the_newest_unread_row() -> None:
    """Verify that older unread announcements never replace the newest one."""
    old = await DevAnnouncement.create(message="old", created_by=1)
    service = _service()
    await service.load()
    assert (await service.pending_announcement(5)).id == old.id

    newest = await service.publish("new", created_by=2)
    assert (await service.pending_announcement(5)).id == newest.id

    await service.mark_read(5, newest.id)
    assert await service.pending_announcement(5) is None
    assert await DevAnnouncement.filter(id=old.id).exists()
    assert not await DevAnnouncementRead.exists(user_id=5, announcement_id=old.id)


@pytest.mark.usefixtures("database")
async def test_mark_read_is_idempotent() -> None:
    """Verify that marking the same announcement read twice keeps one row."""
    service = _service()
    newest = await service.publish("notice", created_by=1)

    await service.mark_read(5, newest.id)
    await service.mark_read(5, newest.id)

    assert await DevAnnouncementRead.filter(user_id=5).count() == 1


@pytest.mark.usefixtures("database")
async def test_set_maintenance_persists_and_clears_a_stale_reason() -> None:
    """Verify that disabling clears the reason and re-enabling stores none."""
    service = _service()

    await service.set_maintenance(enabled=True, reason="Hotfix", updated_by=11)
    row = await DevMaintenance.get(id=1)
    assert (row.enabled, row.reason, row.updated_by) == (True, "Hotfix", 11)
    assert service._maintenance is True
    assert service._maintenance_reason == "Hotfix"

    await service.set_maintenance(enabled=False, reason="stale", updated_by=12)
    row = await DevMaintenance.get(id=1)
    assert (row.enabled, row.reason, row.updated_by) == (False, None, 12)
    assert service._maintenance is False
    assert service._maintenance_reason is None

    await service.set_maintenance(enabled=True, reason=None, updated_by=13)
    row = await DevMaintenance.get(id=1)
    assert (row.enabled, row.reason) == (True, None)
    assert service._maintenance is True
    assert service._maintenance_reason is None


@pytest.mark.usefixtures("database")
async def test_maintenance_write_failure_keeps_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed maintenance write raises before changing the cache."""
    service = _service()
    await service.set_maintenance(enabled=True, reason="Hotfix", updated_by=1)

    async def fail(**kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(DevMaintenance, "update_or_create", fail)

    with pytest.raises(DBConnectionError):
        await service.set_maintenance(enabled=False, reason=None, updated_by=2)

    assert service._maintenance is True
    assert service._maintenance_reason == "Hotfix"
    assert (await DevMaintenance.get(id=1)).enabled is True


@pytest.mark.usefixtures("database")
async def test_publish_write_failure_keeps_the_cached_announcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed publish raises without replacing the cached row."""
    service = _service()
    first = await service.publish("first", created_by=1)

    async def fail(**kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(DevAnnouncement, "create", fail)

    with pytest.raises(DBConnectionError):
        await service.publish("second", created_by=2)

    assert service._latest_announcement is not None
    assert service._latest_announcement.id == first.id
    assert await DevAnnouncement.filter().count() == 1


@pytest.mark.parametrize(
    "error",
    [
        IntegrityError("synthetic integrity failure"),
        DBConnectionError("synthetic database failure"),
    ],
)
@pytest.mark.usefixtures("database")
async def test_mark_read_write_failure_raises(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Verify that read-marker failures are not swallowed."""
    service = _service()
    newest = await service.publish("notice", created_by=1)

    async def fail(**kwargs: object) -> None:
        raise error

    monkeypatch.setattr(DevAnnouncementRead, "get_or_create", fail)

    with pytest.raises(type(error)):
        await service.mark_read(5, newest.id)


@pytest.mark.usefixtures("database")
async def test_load_failure_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that a failed load resets the cache to an open state."""
    service = _service()
    service._maintenance = True
    service._maintenance_reason = "stale"
    service._latest_announcement = DevAnnouncement(id=1, message="stale", created_by=1)

    async def fail(**kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(DevMaintenance, "get_or_none", fail)

    await service.load()

    assert service._maintenance is False
    assert service._maintenance_reason is None
    assert service._latest_announcement is None


@pytest.mark.usefixtures("database")
async def test_pending_announcement_failure_fails_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed read check hides the announcement instead of raising."""
    service = _service()
    await service.publish("notice", created_by=1)

    async def fail(**kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(DevAnnouncementRead, "exists", fail)

    assert await service.pending_announcement(5) is None


async def test_allow_fails_open_when_the_gate_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that an error while building the block still allows the interaction."""
    service = _service()
    service._maintenance = True

    def fail(locale: object) -> discord.Embed:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(service, "maintenance_embed", fail)

    assert await service.allow(_interaction()[0]) is True


@pytest.mark.usefixtures("database")
async def test_allow_blocks_with_one_private_maintenance_embed() -> None:
    """Verify that maintenance sends one localized private embed and refuses."""
    service = _service()
    await service.set_maintenance(
        enabled=True, reason="Upgrading services", updated_by=1
    )
    interaction, response, followup = _interaction()

    assert await service.allow(interaction) is False

    assert len(response.sent) == 1
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    card = sent["embed"]
    assert card.title == _text("dev-maintenance-title")
    assert card.description == _text("dev-maintenance-description")
    assert [(field.name, field.value) for field in card.fields] == [
        (
            _text("dev-maintenance-reason"),
            "Upgrading services",
        )
    ]
    assert not followup.sent


async def test_allow_bypasses_owner_autocomplete_and_the_read_action() -> None:
    """Verify that the three maintenance bypasses allow without sending."""
    owner_service = _service(owner=True)
    owner_service._maintenance = True
    owner_interaction, owner_response, _ = _interaction()
    assert await owner_service.allow(owner_interaction) is True
    assert not owner_response.sent

    service = _service()
    service._maintenance = True
    autocomplete, autocomplete_response, _ = _interaction(
        kind=discord.InteractionType.autocomplete
    )
    assert await service.allow(autocomplete) is True
    assert not autocomplete_response.sent
    service.bot.is_owner.assert_not_awaited()

    read, read_response, _ = _interaction(
        kind=discord.InteractionType.component,
        data={"custom_id": "botfragg:dev_announce_read:42:7"},
    )
    assert await service.allow(read) is True
    assert not read_response.sent


async def test_allow_with_maintenance_off_never_sends() -> None:
    """Verify that a disabled gate allows interactions without resolving the owner."""
    service = _service()
    interaction, response, _ = _interaction()

    assert await service.allow(interaction) is True

    assert not response.sent
    service.bot.is_owner.assert_not_awaited()


def test_maintenance_embed_omits_the_reason_when_none() -> None:
    """Verify that the maintenance embed only adds a field for a reason."""
    service = _service()
    service._maintenance_reason = None

    assert service.maintenance_embed(TEST_LOCALE).fields == []

    service._maintenance_reason = "Scheduled work"
    card = service.maintenance_embed(TEST_LOCALE)
    assert [(field.name, field.value) for field in card.fields] == [
        (_text("dev-maintenance-reason"), "Scheduled work")
    ]


@pytest.mark.usefixtures("database")
async def test_deliver_sends_the_announcement_with_a_read_button() -> None:
    """Verify that a pending announcement is sent privately with a Mark read button."""
    service = _service()
    newest = await service.publish("Patch incoming", created_by=7)
    interaction, response, followup = _interaction(user_id=42)

    await service.deliver(interaction)

    assert len(response.sent) == 1
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].title == _text("dev-announcement-title")
    assert sent["embed"].description == "Patch incoming"
    button = sent["view"].children[0]
    assert button.item.custom_id == f"botfragg:dev_announce_read:42:{newest.id}"
    assert button.item.label == _text("dev-announcement-read-button")
    assert not followup.sent


@pytest.mark.usefixtures("database")
async def test_deliver_uses_the_followup_after_the_response_is_done() -> None:
    """Verify that delivery falls back to a follow-up once the response is used."""
    service = _service()
    await service.publish("Patch incoming", created_by=7)
    interaction, response, followup = _interaction(done=True)

    await service.deliver(interaction)

    assert not response.sent
    assert len(followup.sent) == 1
    assert followup.sent[0]["ephemeral"] is True


@pytest.mark.usefixtures("database")
async def test_deliver_skips_read_autocomplete_and_blocked_interactions() -> None:
    """Verify that delivery never runs for exempt or maintenance-blocked users."""
    service = _service()
    newest = await service.publish("Patch incoming", created_by=7)

    await service.mark_read(42, newest.id)
    read, read_response, _ = _interaction(user_id=42)
    await service.deliver(read)
    assert not read_response.sent

    autocomplete, autocomplete_response, _ = _interaction(
        kind=discord.InteractionType.autocomplete
    )
    await service.deliver(autocomplete)
    assert not autocomplete_response.sent

    service._maintenance = True
    blocked, blocked_response, _ = _interaction(user_id=99)
    await service.deliver(blocked)
    assert not blocked_response.sent

    service.bot.is_owner.return_value = True
    allowed, allowed_response, _ = _interaction(user_id=99)
    await service.deliver(allowed)
    assert len(allowed_response.sent) == 1


@pytest.mark.usefixtures("database")
async def test_deliver_swallows_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed announcement send never escapes."""
    service = _service()
    await service.publish("Patch incoming", created_by=7)
    interaction, response, _ = _interaction()

    async def fail(**kwargs: object) -> None:
        raise RuntimeError("synthetic delivery failure")

    monkeypatch.setattr(response, "send_message", fail)

    await service.deliver(interaction)


def _tree() -> tuple[BotFraggCommandTree, SimpleNamespace]:
    """Build a real command tree whose fake client records notice calls."""
    notices = SimpleNamespace(allow=AsyncMock(return_value=True), deliver=AsyncMock())
    client = SimpleNamespace(
        http=object(),
        _connection=SimpleNamespace(_command_tree=None),
        dev_notices=notices,
        dispatch=AsyncMock(),
    )
    return BotFraggCommandTree(client), notices


def _tree_interaction(
    *,
    kind: discord.InteractionType = discord.InteractionType.application_command,
    data: dict[str, object] | None = None,
    done: bool = False,
) -> tuple[SimpleNamespace, RecordingResponse]:
    """Build an unanswered fake interaction for tree dispatch."""
    response = RecordingResponse(done=done)
    interaction = _localized_interaction(
        type=kind,
        user=_user(42),
        guild_id=None,
        channel_id=None,
        data=data or {"name": "ping", "type": 1},
        response=response,
        followup=RecordingFollowup(),
        command_failed=False,
        command=None,
    )
    return interaction, response


async def test_tree_gate_blocks_before_the_command_body_runs() -> None:
    """Verify that a refused gate skips the command body on an unanswered interaction."""
    tree, notices = _tree()
    ran = False

    @tree.command(name="ping", description="Ping")
    async def ping(interaction: discord.Interaction) -> None:
        """Record that the command body ran."""
        nonlocal ran
        ran = True

    seen: list[bool] = []

    async def refuse(interaction: SimpleNamespace) -> bool:
        seen.append(interaction.response.is_done())
        return False

    notices.allow.side_effect = refuse
    interaction, response = _tree_interaction()

    await tree._call(interaction)

    assert ran is False
    assert interaction.command_failed is True
    assert seen == [False]
    notices.allow.assert_awaited_once_with(interaction)
    assert not response.sent


async def test_tree_gate_is_called_for_context_menus() -> None:
    """Verify that the gate runs for context-menu payloads before dispatch."""
    tree, notices = _tree()
    notices.allow.return_value = False
    interaction, _ = _tree_interaction(data={"name": "Inspect", "type": 3})

    await tree._call(interaction)

    notices.allow.assert_awaited_once_with(interaction)
    assert interaction.command_failed is True


async def test_tree_gate_skips_autocomplete_without_the_service() -> None:
    """Verify that autocomplete passes the check without consulting the service."""
    tree, notices = _tree()
    interaction, _ = _tree_interaction(kind=discord.InteractionType.autocomplete)

    assert await tree.interaction_check(interaction) is True

    notices.allow.assert_not_awaited()


async def test_tree_allows_deletedata_during_maintenance() -> None:
    """Verify /deletedata bypasses maintenance while other commands stay blocked."""
    tree, notices = _tree()
    notices.allow.return_value = False
    deleting, _ = _tree_interaction(data={"name": "deletedata", "type": 1})
    other, _ = _tree_interaction()

    assert await tree.interaction_check(deleting) is True
    notices.allow.assert_not_awaited()
    assert await tree.interaction_check(other) is False
    notices.allow.assert_awaited_once_with(other)


async def test_tree_skips_delivery_for_an_unresolved_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an unknown command that never resolved gets no announcement."""
    tree, notices = _tree()
    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", AsyncMock())
    interaction, _ = _tree_interaction()

    await tree._call(interaction)

    notices.deliver.assert_not_awaited()


@pytest.mark.usefixtures("database")
async def test_tree_delivers_after_a_successful_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that delivery happens after a successful command and analytics still record."""
    tree, notices = _tree()
    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", AsyncMock())
    interaction, _ = _tree_interaction()
    interaction.command = SimpleNamespace(qualified_name="ping")

    await tree._call(interaction)

    notices.deliver.assert_awaited_once_with(interaction)
    assert await CommandInvocation.filter(user_id=42, command="ping").exists()


async def test_tree_skips_delivery_after_a_failed_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that delivery is skipped when the command failed."""
    tree, notices = _tree()
    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", AsyncMock())
    interaction, _ = _tree_interaction()
    interaction.command_failed = True
    interaction.command = SimpleNamespace(qualified_name="ping")

    await tree._call(interaction)

    notices.deliver.assert_not_awaited()


async def test_tree_skips_delivery_when_the_command_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an unexpected command error escapes without delivering a notice."""
    tree, notices = _tree()
    monkeypatch.setattr(
        discord.app_commands.CommandTree,
        "_call",
        AsyncMock(side_effect=RuntimeError("synthetic command failure")),
    )
    interaction, _ = _tree_interaction()

    with pytest.raises(RuntimeError):
        await tree._call(interaction)

    notices.deliver.assert_not_awaited()


async def test_tree_skips_delivery_for_the_deletedata_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify /deletedata never recreates read state by delivering a notice."""
    tree, notices = _tree()
    monkeypatch.setattr(discord.app_commands.CommandTree, "_call", AsyncMock())
    interaction, _ = _tree_interaction()
    interaction.command = SimpleNamespace(qualified_name="deletedata")

    await tree._call(interaction)

    notices.deliver.assert_not_awaited()


@pytest.mark.usefixtures("database")
async def test_mark_read_is_skipped_after_deletion_cancels_the_command() -> None:
    """Verify a read marker is not written for a command cancelled by deletion."""
    service = _service()
    newest = await service.publish("notice", created_by=1)

    async with command_analytics(5) as cancelled:
        cancelled.set()
        await service.mark_read(5, newest.id)

    assert not await DevAnnouncementRead.exists(user_id=5, announcement_id=newest.id)


async def test_bot_constructs_the_notices_service() -> None:
    """Verify that the bot owns a notices service bound to itself."""
    config = SimpleNamespace(
        shard_count=None, token_encryption_key=Fernet.generate_key().decode()
    )

    async with BotFraggBot(config) as bot:
        assert isinstance(bot.dev_notices, DevNotices)
        assert bot.dev_notices.bot is bot
