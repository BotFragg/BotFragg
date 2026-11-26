"""Tests for the owner-only dev commands, shop cache clearing, and read marker."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from tortoise.exceptions import DBConnectionError, IntegrityError

from src.cogs.dev import DevCog
from src.localization import BotFraggTranslator
from src.models import DevAnnouncement, DevAnnouncementRead, DevMaintenance
from src.services.dev_notices import DevNotices
from src.services.shop import ShopService
from tests.helpers import TEST_LOCALE, TEST_TRANSLATOR


class _Recorder(BotFraggTranslator):
    """Record translated messages with their formatting arguments."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        super().__init__()
        self.calls: list[tuple[str, dict[str, object]]] = []

    def text(
        self, locale: discord.Locale | str | None, key: str, **arguments: object
    ) -> str:
        """Record one formatting request and keep the real fallback text."""
        self.calls.append((key, arguments))
        return super().text(locale, key, **arguments)


class _Response:
    """Capture the response paths a dev command may use."""

    def __init__(self, *, done: bool = False) -> None:
        """Record whether the initial response was already used."""
        self.done = done
        self.sent: list[dict[str, object]] = []
        self.deferred: list[tuple[bool, bool]] = []
        self.edited: list[dict[str, object]] = []

    def is_done(self) -> bool:
        """Report whether the interaction already responded."""
        return self.done

    async def send_message(self, **kwargs: object) -> None:
        """Record one initial ephemeral response."""
        self.sent.append(kwargs)
        self.done = True

    async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
        """Record a private deferred response."""
        self.deferred.append((thinking, ephemeral))
        self.done = True

    async def edit_message(self, **kwargs: object) -> None:
        """Record one message edit."""
        self.edited.append(kwargs)


class _Followup:
    """Capture follow-up messages sent after a deferred response."""

    def __init__(self) -> None:
        """Start with no recorded follow-ups."""
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record one follow-up message."""
        self.sent.append(kwargs)


def _bot(**attributes: object) -> SimpleNamespace:
    """Build a fake bot with owner authorization and component registration."""
    handlers: dict[str, object] = {}
    values: dict[str, object] = {
        "translator": TEST_TRANSLATOR,
        "is_owner": AsyncMock(return_value=True),
        "component_handlers": handlers,
    }
    values.update(attributes)
    bot = SimpleNamespace(**values)
    bot.register_component = lambda action, handler: handlers.__setitem__(
        action, handler
    )
    return bot


def _interaction(
    *, user_id: int = 1, translator: BotFraggTranslator = TEST_TRANSLATOR
) -> tuple[SimpleNamespace, _Response, _Followup]:
    """Build a fake interaction with recording response paths."""
    response = _Response()
    followup = _Followup()
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        response=response,
        followup=followup,
        client=SimpleNamespace(translator=translator),
        locale=TEST_LOCALE,
    )
    return interaction, response, followup


async def test_clear_all_cached_storefronts_empties_the_snapshot() -> None:
    """Verify every cached or retry-tracked account is cleared and counted."""
    shop = ShopService(Mock(), Mock(), Mock(), Mock())
    shop._cache = {"a": Mock(), "b": Mock()}
    shop._retry_at = {"b": (503, 10.0), "c": (429, 20.0)}

    cleared = await shop.clear_all_cached_storefronts()

    assert cleared == 3
    assert shop._cache == {}
    assert shop._retry_at == {}


def test_dev_group_exposes_the_four_owner_commands() -> None:
    """Verify the group command names and owner-only extras."""
    names = {command.name for command in DevCog.dev.commands}

    assert names == {"maintenance", "announce", "sync-cache", "inspect"}
    assert all(
        command.extras == {"owner_only": True} for command in DevCog.dev.commands
    )


@pytest.mark.parametrize(
    ("attribute", "arguments"),
    [
        ("maintenance", (True, None)),
        ("announce", ("hello",)),
        ("sync_cache", ()),
        ("inspect", ("user", "123")),
    ],
)
async def test_dev_commands_reject_non_owners(
    attribute: str, arguments: tuple[object, ...]
) -> None:
    """Verify a non-owner is rejected before any work happens."""
    bot = _bot(is_owner=AsyncMock(return_value=False))
    cog = DevCog(bot)
    interaction, response, followup = _interaction()

    await getattr(DevCog, attribute).callback(cog, interaction, *arguments)

    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "staff-owner-only"
    )
    assert response.deferred == []
    assert followup.sent == []


@pytest.mark.usefixtures("database")
async def test_maintenance_writes_and_reports_the_enabled_state() -> None:
    """Verify maintenance persists the reason and replies with the enabled embed."""
    notices = DevNotices(_bot())
    cog = DevCog(_bot(dev_notices=notices))
    interaction, response, _ = _interaction(user_id=7)

    await DevCog.maintenance.callback(cog, interaction, True, "Upgrading services")

    row = await DevMaintenance.get(id=1)
    assert (row.enabled, row.reason, row.updated_by) == (
        True,
        "Upgrading services",
        7,
    )
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-maintenance-title"
    )
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-maintenance-enabled"
    )
    assert [(field.name, field.value) for field in sent["embed"].fields] == [
        (
            TEST_TRANSLATOR.text(TEST_LOCALE, "dev-maintenance-reason"),
            "Upgrading services",
        )
    ]


@pytest.mark.usefixtures("database")
async def test_maintenance_disable_reports_the_disabled_state() -> None:
    """Verify disabling clears the stored reason and reports the disabled embed."""
    notices = DevNotices(_bot())
    await notices.set_maintenance(enabled=True, reason="stale", updated_by=1)
    cog = DevCog(_bot(dev_notices=notices))
    interaction, response, _ = _interaction()

    await DevCog.maintenance.callback(cog, interaction, False, "stale")

    row = await DevMaintenance.get(id=1)
    assert (row.enabled, row.reason) == (False, None)
    sent = response.sent[0]
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-maintenance-disabled"
    )
    assert sent["embed"].fields == []


@pytest.mark.usefixtures("database")
async def test_maintenance_write_failure_replies_with_a_private_error() -> None:
    """Verify a failed maintenance write is reported without changing the row."""
    notices = DevNotices(_bot())

    async def fail(**_kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    notices.set_maintenance = fail  # type: ignore[method-assign]
    cog = DevCog(_bot(dev_notices=notices))
    interaction, response, _ = _interaction()

    await DevCog.maintenance.callback(cog, interaction, True, None)

    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-write-failed"
    )
    assert await DevMaintenance.filter().count() == 0


@pytest.mark.usefixtures("database")
async def test_announce_publishes_and_reports_the_announcement_id() -> None:
    """Verify announce inserts a row and replies with its identifier."""
    recorder = _Recorder()
    notices = DevNotices(_bot())
    cog = DevCog(_bot(dev_notices=notices))
    interaction, response, _ = _interaction(user_id=9, translator=recorder)

    await DevCog.announce.callback(cog, interaction, "Scheduled maintenance")

    announcement = await DevAnnouncement.get()
    assert (announcement.message, announcement.created_by) == (
        "Scheduled maintenance",
        9,
    )
    assert notices._latest_announcement is not None
    assert notices._latest_announcement.id == announcement.id
    assert response.sent[0]["ephemeral"] is True
    assert (
        "dev-announcement-published",
        {"id": announcement.id},
    ) in recorder.calls


@pytest.mark.usefixtures("database")
async def test_announce_write_failure_replies_with_a_private_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a failed publish is reported without inserting a row."""
    notices = DevNotices(_bot())

    async def fail(**_kwargs: object) -> None:
        raise DBConnectionError("synthetic database failure")

    monkeypatch.setattr(DevAnnouncement, "create", fail)
    cog = DevCog(_bot(dev_notices=notices))
    interaction, response, _ = _interaction()

    await DevCog.announce.callback(cog, interaction, "notice")

    assert response.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-write-failed"
    )
    assert await DevAnnouncement.filter().count() == 0


async def test_sync_cache_refreshes_the_catalog_and_reports_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify sync-cache times the refresh and reports every cleared account."""
    recorder = _Recorder()
    catalog = SimpleNamespace(
        refresh=AsyncMock(),
        skins={"a": Mock(), "b": Mock()},
        bundles={"x": Mock()},
    )
    shop = SimpleNamespace(clear_all_cached_storefronts=AsyncMock(return_value=3))
    cog = DevCog(_bot(catalog=catalog, shop=shop))
    interaction, response, followup = _interaction(translator=recorder)
    times = iter([100.0, 101.5])
    monkeypatch.setattr("src.cogs.dev.monotonic", lambda: next(times))

    await DevCog.sync_cache.callback(cog, interaction)

    catalog.refresh.assert_awaited_once_with()
    shop.clear_all_cached_storefronts.assert_awaited_once_with()
    assert response.deferred == [(True, True)]
    assert followup.sent[0]["ephemeral"] is True
    assert (
        "dev-sync-complete",
        {"skins": 2, "bundles": 1, "accounts": 3, "seconds": "1.5"},
    ) in recorder.calls


async def test_sync_cache_failure_reports_a_private_error() -> None:
    """Verify a catalog failure surfaces privately and skips the cache clear."""
    catalog = SimpleNamespace(
        refresh=AsyncMock(side_effect=RuntimeError("catalog unavailable")),
        skins={},
        bundles={},
    )
    shop = SimpleNamespace(clear_all_cached_storefronts=AsyncMock())
    cog = DevCog(_bot(catalog=catalog, shop=shop))
    interaction, _, followup = _interaction()

    await DevCog.sync_cache.callback(cog, interaction)

    shop.clear_all_cached_storefronts.assert_not_awaited()
    sent = followup.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-command-failed"
    )


async def test_inspect_user_uses_cached_guild_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify user inspection renders retained stats and labels the cached count."""
    user_id = 123

    class Guild:
        """Represent a guild with a configured cached member and owner."""

        def __init__(self, member_id: int | None, owner_id: int = 1) -> None:
            """Configure member lookup and server ownership results."""
            self.member_id = member_id
            self.owner_id = owner_id

        def get_member(self, requested_id: int) -> object | None:
            """Return the configured cached member when IDs match."""
            return object() if self.member_id == requested_id else None

    class User:
        """Supply the Discord user fields shown by the diagnostic embed."""

        id = user_id
        display_avatar = SimpleNamespace(url="https://example.com/avatar.png")

        def __str__(self) -> str:
            """Return a stable username for the output assertion."""
            return "Player#0001"

    async def command_stats(**_filters: object) -> tuple[int, str]:
        """Return stable command analytics."""
        return 5, "/shop"

    monkeypatch.setattr("src.cogs.dev.command_stats", command_stats)
    bot = _bot(
        get_user=Mock(return_value=User()),
        guilds=[Guild(None, owner_id=user_id), Guild(user_id), Guild(None)],
    )
    cog = DevCog(bot)
    interaction, _, followup = _interaction()

    await DevCog.inspect.callback(cog, interaction, "user", str(user_id))

    card = followup.sent[0]["embed"]
    assert "**Shared servers (cached; may be incomplete):** 2" in card.description
    assert "**Owned servers:** 1" in card.description
    assert "**Commands used (retained):** 5" in card.description
    assert "**Most used command:** /shop" in card.description
    assert followup.sent[0]["ephemeral"] is True


async def test_inspect_user_falls_back_to_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an uncached user is fetched when it is available."""

    async def command_stats(**_filters: object) -> tuple[int, None]:
        """Return empty command analytics."""
        return 0, None

    monkeypatch.setattr("src.cogs.dev.command_stats", command_stats)

    class User:
        """Supply the Discord user fields shown by the diagnostic embed."""

        id = 321
        display_avatar = SimpleNamespace(url="https://example.com/avatar.png")

        def __str__(self) -> str:
            """Return a stable username for the output assertion."""
            return "Fetched#0001"

    bot = _bot(
        get_user=Mock(return_value=None),
        fetch_user=AsyncMock(return_value=User()),
        guilds=[],
    )
    cog = DevCog(bot)
    interaction, _, followup = _interaction()

    await DevCog.inspect.callback(cog, interaction, "user", "321")

    bot.fetch_user.assert_awaited_once_with(321)
    assert "**ID:** 321" in followup.sent[0]["embed"].description


async def test_inspect_server_labels_discord_members_as_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify server inspection reuses the cached membership caveat."""

    async def command_stats(**_filters: object) -> tuple[int, str | None]:
        """Return empty command analytics."""
        return 0, None

    monkeypatch.setattr("src.cogs.dev.command_stats", command_stats)
    server = SimpleNamespace(
        id=456,
        owner_id=789,
        name="Test server",
        member_count=40,
        members=[SimpleNamespace(bot=True)],
        channels=[],
        roles=[],
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        icon=None,
    )
    bot = _bot(get_guild=Mock(return_value=server))
    cog = DevCog(bot)
    interaction, _, followup = _interaction()

    await DevCog.inspect.callback(cog, interaction, "server", "456")

    card = followup.sent[0]["embed"]
    assert "**Members (cached; may be outdated):** 40" in card.fields[0].value
    assert "humans" not in card.fields[0].value
    assert "bots" not in card.fields[0].value
    assert "**Commands used (retained):** 0" in card.fields[1].value
    assert followup.sent[0]["ephemeral"] is True


@pytest.mark.parametrize("target", ["user", "server"])
async def test_inspect_rejects_non_decimal_ids(target: str) -> None:
    """Verify an unparseable ID is rejected before any lookup."""
    bot = _bot(get_user=Mock(), get_guild=Mock())
    cog = DevCog(bot)
    interaction, response, _ = _interaction()

    await DevCog.inspect.callback(cog, interaction, target, "not-a-number")

    bot.get_user.assert_not_called()
    bot.get_guild.assert_not_called()
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-inspect-id-invalid"
    )


@pytest.mark.parametrize("target", ["user", "server"])
async def test_inspect_rejects_ids_over_twenty_digits(target: str) -> None:
    """Verify absurdly long digit strings are rejected before conversion and lookup."""
    bot = _bot(get_user=Mock(), get_guild=Mock())
    cog = DevCog(bot)
    interaction, response, _ = _interaction()

    await DevCog.inspect.callback(cog, interaction, target, "1" * 21)

    bot.get_user.assert_not_called()
    bot.get_guild.assert_not_called()
    assert response.deferred == []
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-inspect-id-invalid"
    )


async def test_inspect_user_defers_before_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the response is deferred before the uncached user fetch starts."""
    order: list[str] = []

    class User:
        """Supply the Discord user fields shown by the diagnostic embed."""

        id = 321
        display_avatar = SimpleNamespace(url="https://example.com/avatar.png")

        def __str__(self) -> str:
            """Return a stable username for the output assertion."""
            return "Fetched#0001"

    async def command_stats(**_filters: object) -> tuple[int, None]:
        """Return empty command analytics."""
        return 0, None

    async def fetch_user(_user_id: int) -> User:
        """Record when the user fetch is awaited."""
        order.append("fetch")
        return User()

    monkeypatch.setattr("src.cogs.dev.command_stats", command_stats)
    bot = _bot(
        get_user=Mock(return_value=None),
        fetch_user=AsyncMock(side_effect=fetch_user),
        guilds=[],
    )
    cog = DevCog(bot)
    interaction, response, followup = _interaction()
    record_defer = response.defer

    async def defer(*, thinking: bool, ephemeral: bool) -> None:
        """Record when the response is deferred."""
        order.append("defer")
        await record_defer(thinking=thinking, ephemeral=ephemeral)

    interaction.response.defer = defer

    await DevCog.inspect.callback(cog, interaction, "user", "321")

    assert order == ["defer", "fetch"]
    assert response.deferred == [(True, True)]
    assert "**ID:** 321" in followup.sent[0]["embed"].description


async def test_inspect_reports_a_missing_user() -> None:
    """Verify a failed cached and REST user lookup is reported privately."""
    bot = _bot(
        get_user=Mock(return_value=None),
        fetch_user=AsyncMock(side_effect=discord.NotFound(Mock(), "Unknown User")),
    )
    cog = DevCog(bot)
    interaction, response, followup = _interaction()

    await DevCog.inspect.callback(cog, interaction, "user", "404")

    assert response.deferred == [(True, True)]
    sent = followup.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-inspect-user-missing"
    )


async def test_inspect_reports_a_missing_server() -> None:
    """Verify an unjoined server is reported privately."""
    bot = _bot(get_guild=Mock(return_value=None))
    cog = DevCog(bot)
    interaction, response, followup = _interaction()

    await DevCog.inspect.callback(cog, interaction, "server", "404")

    assert response.deferred == [(True, True)]
    sent = followup.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-inspect-server-missing"
    )


async def test_announcement_read_marks_the_row_and_removes_the_button() -> None:
    """Verify the read handler records the marker and edits the message."""
    notices = SimpleNamespace(mark_read=AsyncMock())
    bot = _bot(dev_notices=notices)
    cog = DevCog(bot)
    assert bot.component_handlers["dev_announce_read"] == cog.announcement_read
    interaction, response, _ = _interaction(user_id=9)

    await cog.announcement_read(interaction, "7")

    notices.mark_read.assert_awaited_once_with(9, 7)
    edited = response.edited[0]
    assert edited["view"] is None
    assert edited["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-announcement-read"
    )


async def test_announcement_read_failure_keeps_the_button() -> None:
    """Verify a failed read write is reported privately without editing."""
    notices = SimpleNamespace(
        mark_read=AsyncMock(side_effect=DBConnectionError("synthetic failure"))
    )
    bot = _bot(dev_notices=notices)
    cog = DevCog(bot)
    interaction, response, _ = _interaction()

    await cog.announcement_read(interaction, "7")

    assert response.edited == []
    sent = response.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "dev-write-failed"
    )


@pytest.mark.usefixtures("database")
async def test_mark_read_tolerates_a_duplicate_insert_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a losing concurrent mark-read write is treated as already read."""
    service = DevNotices(_bot())
    announcement = await service.publish("notice", created_by=1)
    await service.mark_read(5, announcement.id)

    async def race(**_kwargs: object) -> None:
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(DevAnnouncementRead, "get_or_create", race)

    await service.mark_read(5, announcement.id)

    assert await DevAnnouncementRead.filter(user_id=5).count() == 1


def test_staff_cog_module_is_removed() -> None:
    """Verify the replaced staff module no longer exists."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.cogs.staff")
