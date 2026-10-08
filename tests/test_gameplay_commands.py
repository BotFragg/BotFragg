"""Behavior checks for gameplay commands."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest

from src.cogs.valorant.battlepass import BattlepassCog
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


async def test_battlepass_hides_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that battlepass hides name when preference enabled."""
    account = SimpleNamespace(username="SecretName#NA")
    data = {
        "act": "Act",
        "level": 1,
        "progress": 1,
        "next_level_xp": 10,
        "end": datetime.now(UTC),
        "next_reward": {"name": "Reward", "type": "Reward", "icon": None},
    }
    sent: list[discord.Embed] = []

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account for the command under test."""
        return account

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Return the configured user fixture for the requested Discord ID."""
        return SimpleNamespace(hide_ign=True)

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent.append(embed)

    class Gameplay:
        """Return controlled battlepass or mission data without making Riot requests."""

        async def battlepass(
            self, _account: object, *, locale: str | None = None
        ) -> dict[str, object]:
            """Return the configured battlepass progression fixture."""
            return data

    class EmojiService:
        """Return deterministic currency and progress markers for embed assertions."""

        async def battlepass_bars(self) -> tuple[str, str]:
            """Return progress-bar markers used by embed assertions."""
            return "█", "░"

    monkeypatch.setattr(
        "src.cogs.valorant.battlepass.selected_account", selected_account
    )
    monkeypatch.setattr("src.cogs.valorant.battlepass.get_user", get_user)
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await BattlepassCog.battlepass.callback(
        BattlepassCog(
            _localized_bot(gameplay=Gameplay(), emoji_service=EmojiService())
        ),
        interaction,
    )

    assert sent[0].title == "Account"
    assert "SecretName" not in sent[0].title


async def test_missions_command_shows_weekly_progress_privately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that missions command shows weekly progress privately."""
    account = SimpleNamespace(username="Player#NA")
    sent: list[tuple[discord.Embed, bool]] = []

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account for the command under test."""
        return account

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking and ephemeral

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent.append((embed, ephemeral))

    class Gameplay:
        """Return controlled battlepass or mission data without making Riot requests."""

        async def missions(
            self, selected: object, *, locale: str | None = None
        ) -> list[dict[str, object]]:
            """Return the configured mission-progress fixture."""
            assert selected is account
            return [
                {
                    "type": "Weekly Missions",
                    "title": "Purchase Items from the Armory",
                    "xp": 23400,
                    "complete": False,
                    "expires": datetime(2026, 9, 28, tzinfo=UTC),
                    "tasks": [
                        {
                            "title": "Purchase {Num} {Num}plural(one=Item,other=Items) from the Armory",
                            "progress": 54,
                            "target": 200,
                        }
                    ],
                },
                {
                    "type": "Weekly Missions",
                    "title": "Use Your Ultimate",
                    "xp": 23400,
                    "complete": False,
                    "expires": datetime(2026, 9, 28, tzinfo=UTC),
                    "tasks": [
                        {
                            "title": "Use Ultimate {Num} {Num}plural(one=Time,other=Times)",
                            "progress": 3,
                            "target": 15,
                        }
                    ],
                },
                {
                    "type": "Weekly Missions",
                    "title": "Use Your Ability",
                    "xp": 23400,
                    "complete": True,
                    "expires": datetime(2026, 9, 28, tzinfo=UTC),
                    "tasks": [
                        {
                            "title": "Use {Num} {Num}plural(one=Ability,other=Abilities)",
                            "progress": 0,
                            "target": 1,
                        }
                    ],
                },
                {
                    "type": "Weekly Missions",
                    "title": "Mission Without Progress Details",
                    "xp": 23400,
                    "complete": True,
                    "expires": datetime(2026, 9, 28, tzinfo=UTC),
                    "tasks": [],
                },
            ]

    class EmojiService:
        """Return deterministic currency and progress markers for embed assertions."""

        async def battlepass_bars(self) -> tuple[str, str]:
            """Return progress-bar markers used by embed assertions."""
            return "<:fbar:1>", "<:ebar:2>"

    monkeypatch.setattr(
        "src.cogs.valorant.battlepass.selected_account", selected_account
    )
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await BattlepassCog.missions.callback(
        BattlepassCog(
            _localized_bot(gameplay=Gameplay(), emoji_service=EmojiService())
        ),
        interaction,
    )

    card, ephemeral = sent[0]
    assert card.title == "Your Missions"
    assert ephemeral is True
    assert len(card.fields) == 1
    assert card.fields[0].name.startswith("Weekly missions · Expires <t:")
    assert card.fields[0].name.count("Expires") == 1
    assert card.fields[0].value.count("23,400 XP") == 4
    assert "**Purchase Items from the Armory · 23,400 XP**" in card.fields[0].value
    assert "`54/200`" in card.fields[0].value
    assert "`3/15`" in card.fields[0].value
    assert "`1/1`" in card.fields[0].value
    assert card.fields[0].value.count("<:fbar:1>" * 10) == 2
    assert "✅ Complete" not in card.fields[0].value
    assert "<:fbar:1>" in card.fields[0].value
    assert "Purchase 200" not in card.fields[0].value
    assert "Use Ultimate" not in card.fields[0].value
    assert "plural(" not in card.fields[0].value
    assert "{Num}" not in card.fields[0].value
    assert "Expires" not in card.fields[0].value


def test_battlepass_uses_qotix_progress_hierarchy() -> None:
    """Verify that battlepass uses Qotix progress hierarchy."""
    card = BattlepassCog._battlepass_card(
        "Agent#NA1",
        {
            "act": "Episode 10 Act 1",
            "level": 12,
            "progress": 500,
            "next_level_xp": 9500,
            "end": datetime.now(UTC),
            "next_reward": {
                "name": "Prime Vandal",
                "type": "EquippableSkinLevel",
                "icon": "https://example.com/prime.png",
            },
        },
        "<:fbar:1>",
        "<:ebar:2>",
        translator=TEST_TRANSLATOR,
        locale=TEST_LOCALE,
    )
    assert [field.name for field in card.fields] == [
        "Current Tier",
        "Next Reward",
        "Type",
        "XP",
    ]
    assert card.image.url == "https://example.com/prime.png"
    assert card.fields[-1].value.endswith("<:ebar:2>" * 10)
