"""Tests for owner-only staff diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from src.cogs.staff import StaffCog
from src.localization import BotFraggTranslator
from tests.helpers import _localized_bot, _localized_interaction


@pytest.mark.parametrize("command", ["userinfo", "serverinfo"])
async def test_non_owner_staff_commands_reject_before_querying(command, monkeypatch):
    stats = AsyncMock()
    suggestions = AsyncMock()
    monkeypatch.setattr("src.cogs.staff.command_stats", stats)
    monkeypatch.setattr("src.cogs.staff.count_suggestions_by_author", suggestions)
    bot = _localized_bot(is_owner=AsyncMock(return_value=False), get_guild=Mock())
    interaction = _localized_interaction(
        user=SimpleNamespace(id=202),
        response=SimpleNamespace(
            is_done=lambda: False, defer=AsyncMock(), send_message=AsyncMock()
        ),
    )
    target = SimpleNamespace(id=101) if command == "userinfo" else "123"
    await getattr(StaffCog, command).callback(StaffCog(bot), interaction, target)

    stats.assert_not_awaited()
    suggestions.assert_not_awaited()
    bot.get_guild.assert_not_called()
    interaction.response.defer.assert_not_awaited()
    sent = interaction.response.send_message.call_args.kwargs
    assert sent["ephemeral"] is True
    assert sent["embed"].description == bot.translator.text(
        interaction.locale, "staff-owner-only"
    )


TEST_TRANSLATOR = BotFraggTranslator()


class Response:
    """Accept only the private deferred response used by staff commands."""

    async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
        """Verify the staff command uses a private deferred response."""
        assert thinking and ephemeral


class Followup:
    """Capture the private embed sent by a staff command."""

    def __init__(self) -> None:
        """Initialize the captured response fields."""
        self.embed: discord.Embed | None = None
        self.ephemeral = False

    async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
        """Record the command's follow-up embed and privacy flag."""
        self.embed = embed
        self.ephemeral = ephemeral


def interaction() -> SimpleNamespace:
    """Create the private interaction surface used by owner diagnostics."""
    return SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=Followup(),
        client=SimpleNamespace(translator=TEST_TRANSLATOR),
        locale=discord.Locale.american_english,
    )


async def test_userinfo_uses_cached_guild_membership(monkeypatch) -> None:
    """Verify userinfo avoids REST lookups and labels its cached server count."""
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

    owned_guild = Guild(member_id=None, owner_id=user_id)
    shared_guild = Guild(member_id=user_id)
    other_guild = Guild(member_id=None)

    class User:
        """Supply the Discord user fields shown by the diagnostic embed."""

        id = user_id
        display_avatar = SimpleNamespace(url="https://example.com/avatar.png")

        def __str__(self) -> str:
            """Return a stable username for the output assertion."""
            return "Player#0001"

    async def is_owner(_user: object) -> bool:
        """Authorize the diagnostic command in this test."""
        return True

    async def command_stats(**_filters: object) -> tuple[int, str]:
        """Return stable command analytics."""
        return 5, "/shop"

    async def suggestion_count(_author_id: int) -> int:
        """Return stable suggestion analytics."""
        return 2

    monkeypatch.setattr("src.cogs.staff.command_stats", command_stats)
    monkeypatch.setattr("src.cogs.staff.count_suggestions_by_author", suggestion_count)
    bot = SimpleNamespace(
        is_owner=is_owner, guilds=[owned_guild, shared_guild, other_guild]
    )
    command_interaction = interaction()

    await StaffCog.userinfo.callback(StaffCog(bot), command_interaction, User())

    card = command_interaction.followup.embed
    assert card is not None
    assert "**Shared servers (cached; may be incomplete):** 2" in card.description
    assert "**Owned servers:** 1" in card.description
    assert command_interaction.followup.ephemeral


async def test_serverinfo_labels_discord_member_count_as_cached(monkeypatch) -> None:
    """Verify server diagnostics do not infer bot counts from an incomplete cache."""

    async def is_owner(_user: object) -> bool:
        """Authorize the diagnostic command in this test."""
        return True

    async def command_stats(**_filters: object) -> tuple[int, str | None]:
        """Return empty command analytics."""
        return 0, None

    monkeypatch.setattr("src.cogs.staff.command_stats", command_stats)
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
    bot = SimpleNamespace(is_owner=is_owner, get_guild=lambda _guild_id: server)
    command_interaction = interaction()

    await StaffCog.serverinfo.callback(StaffCog(bot), command_interaction, "456")

    card = command_interaction.followup.embed
    assert card is not None
    assert "**Members (cached; may be outdated):** 40" in card.fields[0].value
    assert "humans" not in card.fields[0].value
    assert "bots" not in card.fields[0].value
    assert command_interaction.followup.ephemeral
