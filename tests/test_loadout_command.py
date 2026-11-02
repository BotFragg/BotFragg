"""Behaviour checks for the /loadout command and its inspect-video menus."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from src.cogs.valorant import loadout as loadout_cog
from src.cogs.valorant.loadout import LoadoutCog
from src.services.catalog import (
    BUDDY_ITEM_TYPE_ID,
    PLAYER_CARD_ITEM_TYPE_ID,
    PLAYER_TITLE_ITEM_TYPE_ID,
    Accessory,
    Skin,
    Weapon,
)
from src.services.profile import EquippedSkin, PlayerProfile, ProfileUnavailable
from src.views import select_custom_id
from src.views.ui import RED
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)

ACCOUNT = SimpleNamespace(puuid="puuid-1", region="eu", user=SimpleNamespace())
VANDAL = Weapon(
    uuid="weapon-vandal",
    name="Vandal",
    category="Rifles",
    default_skin_uuid="skin-default-vandal",
    names={"en-US": "Vandal"},
)
CLASSIC = Weapon(
    uuid="weapon-classic",
    name="Classic",
    category="Pistols",
    default_skin_uuid="skin-default-classic",
    names={"en-US": "Classic"},
)
ODIN = Weapon(
    uuid="weapon-odin",
    name="Odin",
    category="Heavy Weapons",
    default_skin_uuid="skin-default-odin",
    names={"en-US": "Odin"},
)
PRIME = Skin(
    uuid="skin-prime",
    offer_uuid="offer-prime",
    name="Prime//2.0 Vandal",
    icon="https://example.invalid/prime.png",
    tier_uuid="tier-premium",
    levels=[
        {
            "uuid": "level-prime",
            "displayName": {"en-US": "Prime//2.0 Vandal"},
            "streamedVideo": "https://example.invalid/level.mp4",
        }
    ],
    chromas=[
        {"uuid": "chroma-base", "displayName": {"en-US": "Prime//2.0 Vandal"}},
        {
            "uuid": "chroma-blue",
            "displayName": {"en-US": "Prime//2.0 Vandal Level 5\n(Variant 2 Blue)"},
            "streamedVideo": "https://example.invalid/blue.mp4",
        },
    ],
    names={"en-US": "Prime//2.0 Vandal"},
)
PLAIN = Skin(
    uuid="skin-plain",
    offer_uuid="offer-plain",
    name="Elderflame Odin",
    icon=None,
    tier_uuid=None,
    levels=[{"uuid": "level-plain", "displayName": {"en-US": "Elderflame Odin"}}],
    chromas=[{"uuid": "chroma-plain", "displayName": {"en-US": "Elderflame Odin"}}],
    names={"en-US": "Elderflame Odin"},
)
WEAPONS = {
    "weapon-vandal": VANDAL,
    "weapon-classic": CLASSIC,
    "weapon-odin": ODIN,
}
SKINS = {"skin-prime": PRIME, "skin-plain": PLAIN}


class Response:
    """Record deferrals and ephemeral replies."""

    def __init__(self) -> None:
        """Start with no recorded responses."""
        self.deferred: bool | None = None
        self.sent: list[dict[str, object]] = []

    async def defer(self, *, thinking: bool = False) -> None:
        """Record whether the command deferred with a thinking state."""
        self.deferred = thinking

    async def send_message(self, content: object = None, **kwargs: object) -> None:
        """Record one private response."""
        self.sent.append({"content": content, **kwargs})

    @staticmethod
    def is_done() -> bool:
        """Report that the interaction already responded."""
        return True


class Followup:
    """Record follow-up messages."""

    def __init__(self) -> None:
        """Start with no recorded messages."""
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record one sent message."""
        self.sent.append(kwargs)


def interaction(*, followup: Followup | None = None) -> SimpleNamespace:
    """Build a fake interaction for the loadout command."""
    return _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup or Followup(),
        locale=TEST_LOCALE,
    )


def menu_interaction(*, custom_id: str, values: list[str]) -> SimpleNamespace:
    """Build an interaction whose message offers the given select values."""
    select = SimpleNamespace(
        custom_id=custom_id,
        options=[SimpleNamespace(value=value) for value in values],
    )
    return _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        message=SimpleNamespace(components=[SimpleNamespace(children=[select])]),
        locale=TEST_LOCALE,
    )


def profile(**overrides: object) -> PlayerProfile:
    """Build one profile record with the equipped guns."""
    values: dict[str, object] = {
        "card_id": "card-1",
        "title_id": "title-1",
        "level": 214,
        "xp": 2500,
        "tier": 19,
        "rr": 47,
        "wins": 29,
        "games": 50,
        "peak_tier": 24,
        "guns": (
            EquippedSkin("weapon-vandal", "skin-prime", "chroma-blue", "charm-1"),
            EquippedSkin("weapon-classic", "skin-default-classic", "chroma-default"),
        ),
    }
    values.update(overrides)
    return PlayerProfile(**values)  # type: ignore[arg-type]


def accessory_service() -> AsyncMock:
    """Resolve the card, title, and buddy accessories the card asks for."""

    async def resolve(item_type: str, identifier: str) -> Accessory | None:
        if item_type == PLAYER_CARD_ITEM_TYPE_ID:
            return Accessory(
                "Card",
                "https://example.invalid/card.png",
                names={"en-US": "Card"},
                small_icon="https://example.invalid/card-small.png",
            )
        if item_type == PLAYER_TITLE_ITEM_TYPE_ID:
            return Accessory("Title", None, title_texts={"en-US": "V1.0"})
        if item_type == BUDDY_ITEM_TYPE_ID:
            return Accessory("Beckoner Buddy", None, names={"en-US": "Beckoner Buddy"})
        return None

    return AsyncMock(side_effect=resolve)


def build_bot(*, profile_data: PlayerProfile | None = None) -> SimpleNamespace:
    """Build a localized bot with fake profile, catalog, and emoji services."""
    catalog = SimpleNamespace(
        get_weapon=lambda uuid: WEAPONS.get(uuid),
        get_skin=lambda uuid: SKINS.get(uuid),
        accessory=accessory_service(),
    )
    emoji_service = SimpleNamespace(
        skin_emoji=lambda tier: "<premium>" if tier else "",
        skin_name=lambda name, tier: f"<tier> {name}",
    )
    return _localized_bot(
        profiles=SimpleNamespace(
            profile=AsyncMock(return_value=profile_data or profile())
        ),
        catalog=catalog,
        emoji_service=emoji_service,
        register_component=lambda *_args: None,
    )


async def run(
    monkeypatch: pytest.MonkeyPatch, bot: SimpleNamespace, *, viewer=None
) -> Followup:
    """Run the loadout command with an authenticated account."""
    monkeypatch.setattr(
        loadout_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        loadout_cog,
        "account_viewer",
        AsyncMock(return_value=viewer or (ACCOUNT, False, "KumKaShree#Shree")),
    )
    followup = Followup()
    cog = LoadoutCog(bot)
    await cog.loadout.callback(cog, interaction(followup=followup))
    return followup


async def test_loadout_lists_themed_skins_and_hides_defaults(monkeypatch):
    """Only equipped themed skins render, with their variant and buddy."""
    followup = await run(monkeypatch, build_bot())

    card = followup.sent[0]["embed"]
    assert card.colour == discord.Colour(RED)
    assert card.description == "**KumKaShree#Shree**\n-# V1.0"
    assert len(card.fields) == 1
    assert card.fields[0].name == TEST_TRANSLATOR.text(
        TEST_LOCALE, "loadout-group-rifles"
    )
    assert card.fields[0].value == (
        "<premium> **Prime//2.0 Vandal** *(Variant 2 Blue)* · `Beckoner Buddy`"
    )
    assert card.thumbnail.url == "https://example.invalid/card-small.png"


async def test_loadout_states_when_nothing_themed_is_equipped(monkeypatch):
    """A loadout with only defaults shows the empty state and no controls."""
    followup = await run(
        monkeypatch,
        build_bot(
            profile_data=profile(
                guns=(EquippedSkin("weapon-classic", "skin-default-classic"),)
            )
        ),
    )

    card = followup.sent[0]["embed"]
    assert card.fields == []
    assert TEST_TRANSLATOR.text(TEST_LOCALE, "loadout-empty") in card.description
    assert "view" not in followup.sent[0]


async def test_loadout_offers_a_menu_for_skins_with_videos(monkeypatch):
    """The inspect menu lists only equipped skins that have a video."""
    followup = await run(monkeypatch, build_bot())

    select = followup.sent[0]["view"].children[0].item
    assert [option.value for option in select.options] == ["skin-prime"]
    assert select.options[0].label == "Prime//2.0 Vandal"


async def test_missing_account_asks_for_login(monkeypatch):
    """An unlinked caller must be told to log in."""
    monkeypatch.setattr(loadout_cog, "selected_account", AsyncMock(return_value=None))
    followup = Followup()

    await LoadoutCog(build_bot()).loadout.callback(
        LoadoutCog(build_bot()), interaction(followup=followup)
    )

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-not-registered"
    )


async def test_unavailable_profile_uses_the_riot_error(monkeypatch):
    """A failed profile fetch must use the existing Riot-unavailable message."""
    bot = build_bot()
    bot.profiles.profile = AsyncMock(side_effect=ProfileUnavailable("down"))

    followup = await run(monkeypatch, bot)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-riot-services-unavailable"
    )


async def test_selecting_a_skin_opens_the_variant_menu():
    """Picking an equipped skin lists its levels and chromas with videos."""
    expires = int(time.time()) + 60
    interaction = menu_interaction(
        custom_id=select_custom_id("loadout_video", 1, str(expires)),
        values=["skin-prime"],
    )

    await LoadoutCog(build_bot()).loadout_video(interaction, f"{expires}|skin-prime")

    sent = interaction.response.sent[0]
    options = sent["view"].children[0].item.options
    assert [option.value for option in options] == ["level-prime", "chroma-blue"]
    assert "Prime//2.0 Vandal" in sent["content"]
    assert sent["ephemeral"] is True


async def test_a_forged_or_expired_skin_selection_is_refused():
    """Values not offered by the menu are rejected, including expired menus."""
    expires = int(time.time()) + 60
    forged = menu_interaction(
        custom_id=select_custom_id("loadout_video", 1, str(expires)),
        values=["skin-other"],
    )
    expired_at = int(time.time()) - 10
    expired = menu_interaction(
        custom_id=select_custom_id("loadout_video", 1, str(expired_at)),
        values=["skin-prime"],
    )
    cog = LoadoutCog(build_bot())

    await cog.loadout_video(forged, f"{expires}|skin-prime")
    await cog.loadout_video(expired, f"{expired_at}|skin-prime")

    expected = TEST_TRANSLATOR.text(TEST_LOCALE, "loadout-video-selection-invalid")
    assert forged.response.sent[0]["content"] == expected
    assert expired.response.sent[0]["content"] == expected


async def test_selecting_a_variant_returns_the_private_video():
    """A valid variant selection returns the one-line video link."""
    expires = int(time.time()) + 60
    interaction = menu_interaction(
        custom_id=select_custom_id("loadout_variant", 1, f"{expires}|skin-prime"),
        values=["level-prime", "chroma-blue"],
    )

    await LoadoutCog(build_bot()).loadout_variant(
        interaction, f"{expires}|skin-prime|chroma-blue"
    )

    assert interaction.response.sent[0]["content"] == (
        "[<tier> Prime//2.0 Vandal Level 5 (Variant 2 Blue)]"
        "(https://example.invalid/blue.mp4)"
    )
    assert interaction.response.sent[0]["ephemeral"] is True


async def test_a_forged_variant_is_refused():
    """Levels and chromas not offered by the menu are rejected."""
    expires = int(time.time()) + 60
    interaction = menu_interaction(
        custom_id=select_custom_id("loadout_variant", 1, f"{expires}|skin-prime"),
        values=["level-prime"],
    )

    await LoadoutCog(build_bot()).loadout_variant(
        interaction, f"{expires}|skin-prime|chroma-blue"
    )

    assert interaction.response.sent[0]["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "loadout-video-selection-invalid"
    )


async def test_skins_without_videos_are_not_offered(monkeypatch):
    """The inspect menu must skip equipped skins that have no video."""
    followup = await run(
        monkeypatch,
        build_bot(
            profile_data=profile(guns=(EquippedSkin("weapon-odin", "skin-plain"),))
        ),
    )

    card = followup.sent[0]["embed"]
    assert card.fields[0].name == TEST_TRANSLATOR.text(
        TEST_LOCALE, "loadout-group-snipers-heavy"
    )
    assert "view" not in followup.sent[0]


async def test_a_missing_skin_reports_unavailable():
    """A selected skin that left the catalog reports the shared message."""
    expires = int(time.time()) + 60
    interaction = menu_interaction(
        custom_id=select_custom_id("loadout_video", 1, str(expires)),
        values=["skin-gone"],
    )

    await LoadoutCog(build_bot()).loadout_video(interaction, f"{expires}|skin-gone")

    assert interaction.response.sent[0]["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "skin-video-unavailable"
    )


async def test_an_expired_variant_selection_is_refused():
    """A variant menu selection must not outlive its expiry."""
    expires = int(time.time()) - 10
    interaction = menu_interaction(
        custom_id=select_custom_id("loadout_variant", 1, f"{expires}|skin-prime"),
        values=["level-prime", "chroma-blue"],
    )

    await LoadoutCog(build_bot()).loadout_variant(
        interaction, f"{expires}|skin-prime|chroma-blue"
    )

    assert interaction.response.sent[0]["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "loadout-video-selection-invalid"
    )
