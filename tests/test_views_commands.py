"""Tests for Discord command responses, privacy, component controls, and lifecycle behavior."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import discord
import pytest
from cryptography.fernet import Fernet
from discord.ext import commands

from src.bot import BotfraggBot, BotfraggCommandTree
from src.cogs.extra import ExtraCog
from src.cogs.staff import StaffCog
from src.cogs.tasks import TasksCog
from src.cogs.valorant import shop as shop_module
from src.cogs.valorant.accounts import AccountsCog
from src.cogs.valorant.alerts import AlertsCog
from src.cogs.valorant.battlepass import BattlepassCog
from src.cogs.valorant.login import LoginCog
from src.cogs.valorant.logout import LogoutCog
from src.cogs.valorant.settings import SettingsCog
from src.cogs.valorant.shop import (
    BalanceCog,
    NightMarketCog,
    ShopCog,
    add_skin_selector,
    offer_cards,
)
from src.config import Settings
from src.services.catalog import Accessory, Skin
from src.services.http import HTTPFailure
from src.services.shop import KC_UUID, Offer, ShopData, ShopService
from src.views import OwnedActionButton, OwnedSelect


def test_dynamic_component_ids_fit_discord_limit() -> None:
    """Verify that dynamic component IDs fit Discord limit."""
    owner_id = 12345678901234567890
    assert (
        len(
            OwnedSelect(
                "alert_create",
                owner_id,
                "12345678-1234-1234-1234-123456789012",
            ).item.custom_id
        )
        <= 100
    )
    assert (
        len(
            OwnedSelect(
                "shop_variant",
                owner_id,
                "4000000000|12345678-1234-1234-1234-123456789012",
            ).item.custom_id
        )
        <= 100
    )


@pytest.mark.asyncio
async def test_unhandled_app_command_error_returns_ephemeral_response() -> None:
    """Verify that unhandled app command error returns ephemeral response."""
    sent: list[tuple[object, bool]] = []

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        def is_done(self) -> bool:
            """Report whether the fake interaction response has been sent."""
            return False

        async def send_message(self, *, embed, ephemeral: bool) -> None:
            """Record the initial message sent through the fake interaction."""
            sent.append((embed, ephemeral))

    interaction = SimpleNamespace(command=None, data={}, response=Response())
    await BotfraggCommandTree.on_error(
        object.__new__(BotfraggCommandTree), interaction, RuntimeError("unexpected")
    )

    assert sent[0][0].description.startswith("Something went wrong")
    assert sent[0][1] is True


@pytest.mark.asyncio
async def test_unhandled_prefix_command_error_returns_generic_response() -> None:
    """Verify that unhandled prefix command error returns generic response."""
    sent: list[discord.Embed] = []

    async def send(*, embed: discord.Embed) -> None:
        """Record the follow-up message sent through the fake interaction."""
        sent.append(embed)

    context = SimpleNamespace(
        command=SimpleNamespace(qualified_name="debug"), send=send
    )
    error = commands.CommandInvokeError(RuntimeError("private detail"))

    assert "on_command_error" in BotfraggBot.__dict__
    await BotfraggBot.on_command_error(object.__new__(BotfraggBot), context, error)

    assert sent[0].description.startswith("Something went wrong")
    assert "private detail" not in sent[0].description


@pytest.mark.asyncio
async def test_links_invite_preserves_zero_permissions() -> None:
    """Verify that links invite preserves zero permissions."""
    sent: dict[str, object] = {}

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, **kwargs: object) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent.update(kwargs)

    user = SimpleNamespace(
        id=123,
        name="Botfragg",
        display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
    )
    bot = SimpleNamespace(
        user=user,
        config=SimpleNamespace(support_url=None, vote_url=None, website_url=None),
    )
    interaction = SimpleNamespace(response=Response(), followup=Followup())

    cog = ExtraCog(bot)
    await ExtraCog.links.callback(cog, interaction)

    controls = sent["view"]
    invite = controls.children[0]
    query = parse_qs(urlparse(invite.url).query)
    assert query["scope"] == ["bot applications.commands"]
    assert query["permissions"] == ["0"]


@pytest.mark.asyncio
async def test_accessory_shop_renders_catalog_item_without_changing_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that accessory shop renders catalog item without changing output."""
    item = Accessory("Buddy", "https://example.com/buddy.png", "Limited edition")
    data = ShopData(
        offers=[],
        accessory=[
            {
                "Offer": {
                    "Cost": {KC_UUID: 1500},
                    "Rewards": [{"ItemTypeID": "buddy", "ItemID": "buddy-id"}],
                }
            }
        ],
        night_market=[],
        expires=4_000_000_000,
        night_market_expires=None,
    )
    account = SimpleNamespace(puuid="account", username="One#NA")
    rendered: dict[str, object] = {}

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def storefront(self, _account):
            """Return the configured storefront fixture for the requested account."""
            return data

        async def accessory_offers(self, shop_data):
            """Return the configured accessory-shop offers."""
            assert shop_data is data
            return [SimpleNamespace(item=item, price=1500)]

    class EmojiService:
        """Return deterministic currency and progress markers for embed assertions."""

        async def currency(self, key: str) -> str:
            """Return a stable currency marker for embed assertions."""
            assert key == "kc"
            return "KC"

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self) -> None:
            """Record that the fake interaction response was deferred."""
            return None

    async def account_for_user(_owner_id: int, _puuid: str):
        """Return the test account only for the matching user and PUUID."""
        return account

    async def get_user(_owner_id: int):
        """Return the configured user fixture for the requested Discord ID."""
        return None

    async def list_accounts(_owner_id: int):
        """Return the configured accounts for the requested Discord user."""
        return [account, SimpleNamespace(puuid="two", username="Two#EU")]

    async def edit_original_response(*, embeds, view) -> None:
        """Record edits to the fake interaction's original response."""
        rendered["embeds"] = embeds
        rendered["view"] = view

    monkeypatch.setattr(shop_module, "account_for_user", account_for_user)
    monkeypatch.setattr(shop_module, "get_user", get_user)
    monkeypatch.setattr(shop_module, "list_accounts", list_accounts)
    bot = SimpleNamespace(
        shop=Shop(),
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=True),
        register_component=lambda *_args: None,
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        response=Response(),
        edit_original_response=edit_original_response,
    )
    await ShopCog(bot).shop_mode(interaction, "accessory,account")

    embeds = rendered["embeds"]
    assert len(embeds) == 2
    assert embeds[1].title == "Buddy"
    assert embeds[1].description == "`Limited edition`\n\nKC **1,500**"
    assert embeds[1].url == item.icon
    assert embeds[1].thumbnail.url == item.icon
    controls = rendered["view"]
    assert isinstance(controls, discord.ui.View)
    assert [child.item.custom_id.split(":")[1] for child in controls.children] == [
        "shop_account",
        "shop_mode",
    ]


def test_glitchtip_groups_subcommands_separately() -> None:
    """Verify that GlitchTip groups subcommands separately."""
    assert (
        BotfraggCommandTree._command_name(
            {"name": "suggestion", "options": [{"type": 1, "name": "track"}]}
        )
        == "suggestion.track"
    )


def test_shop_offer_layout_uses_tier_colour_and_discount_price() -> None:
    """Verify tier colour and Night Market discount formatting."""
    skin = Skin(
        "skin",
        "offer",
        "Prime Vandal",
        "https://example.com/prime.png",
        "0cebb8be-46d7-c12a-d306-e9907bfc5a25",
    )
    cards = offer_cards(
        "Daily shop", [Offer(skin, 1775, 1)], "VP", link_item_image=True
    )
    assert (len(cards), cards[1].colour.value, cards[1].thumbnail.url) == (
        2,
        0x009984,
        "https://example.com/prime.png",
    )
    discounted = offer_cards(
        "Night Market", [Offer(skin, 1775, 1, 1000, 44)], "VP", link_item_image=False
    )
    assert discounted[1].description == "VP **1,000**\nVP ~~1,775~~ (-44%)"


@pytest.mark.asyncio
async def test_shop_skin_menu_selects_tiered_skin_and_returns_private_video() -> None:
    """Verify tier emoji options and private level/chroma video delivery."""
    skin = Skin(
        "skin",
        "offer",
        "Prime Vandal",
        None,
        "0cebb8be-46d7-c12a-d306-e9907bfc5a25",
        levels=[
            {
                "uuid": "level",
                "displayName": "Prime Vandal Level 2",
                "streamedVideo": "https://example.com/level.mp4",
            }
        ],
        chromas=[
            {
                "uuid": "chroma",
                "displayName": "Prime Vandal Green",
                "streamedVideo": "https://example.com/chroma.mp4",
            },
            {"uuid": "unavailable", "displayName": "No video"},
        ],
    )

    class EmojiService:
        """Return stable tier emoji labels for the shop selector test."""

        def skin_emoji(self, _tier_uuid: str) -> str:
            """Return the fixture's tier emoji."""
            return "<:tier_deluxe:123456>"

        def skin_name(self, name: str, _tier_uuid: str) -> str:
            """Prefix the fixture's tier emoji to a displayed name."""
            return f"<:tier_deluxe:123456> {name}"

    class Response:
        """Capture private interaction replies for response assertions."""

        def __init__(self) -> None:
            """Initialize the captured response list."""
            self.messages: list[dict[str, object]] = []

        async def send_message(self, content: str, **kwargs: object) -> None:
            """Record a response's content and keyword arguments."""
            self.messages.append({"content": content, **kwargs})

    bot = SimpleNamespace(
        register_component=lambda *_args: None,
        catalog=SimpleNamespace(get_skin=lambda uuid: skin if uuid == "skin" else None),
        emoji_service=EmojiService(),
    )
    cog = ShopCog(bot)
    controls = discord.ui.View(timeout=None)
    add_skin_selector(
        controls, 123, [Offer(skin, 1775, 1)], 4_000_000_000, bot.emoji_service
    )
    selector = controls.children[0]

    assert selector.item.options[0].label == "Prime Vandal"
    assert str(selector.item.options[0].emoji) == "<:tier_deluxe:123456>"

    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        message=SimpleNamespace(components=[SimpleNamespace(children=[selector.item])]),
        response=Response(),
    )
    await cog.shop_skin(interaction, "4000000000|skin")

    detail_view = interaction.response.messages[-1]["view"]
    detail_selector = detail_view.children[0]
    assert [option.label for option in detail_selector.item.options] == [
        "Level: Prime Vandal Level 2",
        "Chroma: Prime Vandal Green",
    ]

    interaction.message = SimpleNamespace(
        components=[SimpleNamespace(children=[detail_selector.item])]
    )
    await cog.shop_variant(interaction, "4000000000|skin|level")

    assert interaction.response.messages[-1] == {
        "content": "[<:tier_deluxe:123456> Prime Vandal](https://example.com/level.mp4)",
        "ephemeral": True,
    }

    await cog.shop_variant(interaction, "4000000000|skin|chroma")

    assert interaction.response.messages[-1] == {
        "content": "[<:tier_deluxe:123456> Prime Vandal Green](https://example.com/chroma.mp4)",
        "ephemeral": True,
    }


@pytest.mark.asyncio
async def test_daily_shop_view_includes_only_its_offers_in_skin_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the standard daily shop view exposes its current offer choices."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)

    async def list_accounts(_owner_id: int) -> list[object]:
        """Return two accounts so selector ordering is visible in the view."""
        return [
            SimpleNamespace(puuid="account", username="Player#NA"),
            SimpleNamespace(puuid="another", username="Other#EU"),
        ]

    class EmojiService:
        """Return stable currency and tier emoji markers for shop cards."""

        async def currency(self, _kind: str) -> str:
            """Return the fixture currency marker."""
            return "VP"

        def skin_name(self, name: str, _tier_uuid: str | None) -> str:
            """Return skin names without a tier prefix for this fixture."""
            return name

        def skin_emoji(self, _tier_uuid: str | None) -> str:
            """Report that no custom tier emoji is available."""
            return ""

    monkeypatch.setattr("src.cogs.valorant.shop.list_accounts", list_accounts)
    bot = SimpleNamespace(
        register_component=lambda *_args: None,
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=False),
    )
    cog = ShopCog(bot)
    embeds, controls = await cog.shop_view(
        ShopData(
            [Offer(skin, 1775, 1)],
            [],
            [Offer(skin, 1775, 1)],
            4_000_000_000,
            4_000_000_000,
        ),
        "Player",
        123,
        "account",
    )

    selector = next(
        child
        for child in controls.children
        if child.item.custom_id.startswith("botfragg_select:shop_skin:")
    )
    assert embeds[1].title == "Prime Vandal"
    assert [option.value for option in selector.item.options] == ["skin"]
    assert [child.item.custom_id.split(":")[1] for child in controls.children] == [
        "shop_skin",
        "shop_account",
        "shop_mode",
        "shop_mode",
    ]


@pytest.mark.asyncio
async def test_shop_video_selector_rejects_forged_and_mismatched_values() -> None:
    """Verify menu values and cached skin ownership gate video delivery."""
    skin = Skin("skin", "offer", "Skin", None, None, levels=[])
    other = Skin(
        "other",
        "other-offer",
        "Other Skin",
        None,
        None,
        levels=[
            {
                "uuid": "foreign-level",
                "displayName": "Other Skin Level",
                "streamedVideo": "https://example.com/foreign.mp4",
            }
        ],
    )
    empty = Skin("empty", "empty-offer", "Empty Skin", None, None)

    class Response:
        """Capture invalid selector messages for assertions."""

        def __init__(self) -> None:
            """Initialize the response history."""
            self.messages: list[dict[str, object]] = []

        async def send_message(self, content: str, **kwargs: object) -> None:
            """Record a message and its response options."""
            self.messages.append({"content": content, **kwargs})

    bot = SimpleNamespace(
        register_component=lambda *_args: None,
        catalog=SimpleNamespace(
            get_skin=lambda uuid: {"skin": skin, "other": other, "empty": empty}.get(
                uuid
            )
        ),
        emoji_service=SimpleNamespace(
            skin_emoji=lambda _tier_uuid: "",
            skin_name=lambda name, _tier_uuid: name,
        ),
    )
    cog = ShopCog(bot)
    selector = OwnedSelect(
        "shop_skin",
        123,
        "4000000000",
        options=[
            discord.SelectOption(label="Skin", value="skin"),
            discord.SelectOption(label="Empty Skin", value="empty"),
        ],
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        message=SimpleNamespace(components=[SimpleNamespace(children=[selector.item])]),
        response=Response(),
    )

    await cog.shop_skin(interaction, "1|skin")
    assert interaction.response.messages[-1]["ephemeral"] is True
    assert "no longer available" in str(interaction.response.messages[-1]["content"])

    await cog.shop_skin(interaction, "4000000000|other")
    assert interaction.response.messages[-1]["ephemeral"] is True
    assert "no longer available" in str(interaction.response.messages[-1]["content"])

    await cog.shop_skin(interaction, "4000000000|empty")
    assert interaction.response.messages[-1]["ephemeral"] is True
    assert "No level or chroma videos" in str(
        interaction.response.messages[-1]["content"]
    )

    forged_variant_menu = OwnedSelect(
        "shop_variant",
        123,
        "4000000000|skin",
        options=[discord.SelectOption(label="Foreign video", value="foreign-level")],
    )
    interaction.message = SimpleNamespace(
        components=[SimpleNamespace(children=[forged_variant_menu.item])]
    )
    await cog.shop_variant(interaction, "4000000000|skin|foreign-level")

    assert interaction.response.messages[-1]["ephemeral"] is True
    assert "no longer available" in str(interaction.response.messages[-1]["content"])


@pytest.mark.asyncio
async def test_nightmarket_command_includes_skin_video_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Night Market slash-command offers receive their selector."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)
    data = ShopData([], [], [Offer(skin, 1775, 1, 1000, 44)], 4_000_000_000, None)
    account = SimpleNamespace(puuid="account", username="Player#NA")

    async def selected_account(_owner_id: int) -> SimpleNamespace:
        """Return the account fixture for the Night Market command."""
        return account

    async def get_user(_owner_id: int) -> None:
        """Report default visibility preferences for the fixture user."""
        return None

    monkeypatch.setattr("src.cogs.valorant.shop.selected_account", selected_account)
    monkeypatch.setattr("src.cogs.valorant.shop.get_user", get_user)

    class EmojiService:
        """Provide stable currency and tier emoji values for embeds."""

        async def currency(self, _kind: str) -> str:
            """Return the fixture's VP marker."""
            return "VP"

        def skin_name(self, name: str, _tier_uuid: str | None) -> str:
            """Return a skin name without a tier marker."""
            return name

        def skin_emoji(self, _tier_uuid: str | None) -> str:
            """Report no custom tier emoji for the fixture skin."""
            return ""

    class Shop:
        """Return the fixture storefront for command rendering."""

        async def storefront(self, _account: object) -> ShopData:
            """Return the configured Night Market data."""
            return data

    class Response:
        """Verify the command defers before sending its follow-up."""

        async def defer(self, *, thinking: bool) -> None:
            """Assert that the command uses a thinking response."""
            assert thinking

    class Followup:
        """Capture the Night Market message and its controls."""

        def __init__(self) -> None:
            """Initialize the captured follow-up payload."""
            self.message: dict[str, object] = {}

        async def send(self, **kwargs: object) -> None:
            """Store the follow-up message arguments."""
            self.message.update(kwargs)

    bot = SimpleNamespace(
        shop=Shop(),
        emoji_service=EmojiService(),
        register_component=lambda *_args: None,
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        response=Response(),
        followup=Followup(),
    )

    await NightMarketCog.nightmarket.callback(NightMarketCog(bot), interaction)

    controls = interaction.followup.message["view"]
    selector = next(
        child
        for child in controls.children
        if child.item.custom_id.startswith("botfragg_select:shop_skin:")
    )
    assert [option.value for option in selector.item.options] == ["skin"]


@pytest.mark.asyncio
async def test_daily_shop_dm_includes_skin_video_menu() -> None:
    """Verify daily-shop notification DMs include the shared skin selector."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)
    sent: dict[str, object] = {}

    class Target:
        """Capture the daily-shop DM sent by the task notification."""

        async def send(self, **kwargs: object) -> None:
            """Store the DM arguments."""
            sent.update(kwargs)

    class EmojiService:
        """Provide stable currency and tier emoji values for the DM."""

        async def currency(self, _kind: str) -> str:
            """Return the fixture's VP marker."""
            return "VP"

        def skin_name(self, name: str, _tier_uuid: str | None) -> str:
            """Return a skin name without a tier marker."""
            return name

        def skin_emoji(self, _tier_uuid: str | None) -> str:
            """Report no custom tier emoji for the fixture skin."""
            return ""

    target = Target()
    bot = SimpleNamespace(
        get_user=lambda _user_id: target,
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=False),
        register_component=lambda *_args: None,
    )

    await TasksCog._send_daily_shop(
        SimpleNamespace(bot=bot),
        SimpleNamespace(id=123),
        SimpleNamespace(username="Player#NA"),
        ShopData([Offer(skin, 1775, 1)], [], [], 4_000_000_000, None),
    )

    controls = sent["view"]
    selector = next(
        child
        for child in controls.children
        if child.item.custom_id.startswith("botfragg_select:shop_skin:")
    )
    assert [option.value for option in selector.item.options] == ["skin"]


@pytest.mark.asyncio
async def test_shop_account_selector_hides_names_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that shop account selector hides names when requested."""
    accounts = [
        SimpleNamespace(puuid="one", username="SecretOne#NA"),
        SimpleNamespace(puuid="two", username="SecretTwo#EU"),
    ]

    async def list_accounts(_: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        return accounts

    monkeypatch.setattr("src.cogs.valorant.shop.list_accounts", list_accounts)
    cog = ShopCog(SimpleNamespace(register_component=lambda *_: None))
    controls = discord.ui.View(timeout=None)
    await cog._add_accounts(controls, 123, "daily", "one", hide_ign=True)

    selector = controls.children[0]
    assert [option.label for option in selector.item.options] == [
        "Account 1",
        "Account 2",
    ]


@pytest.mark.asyncio
async def test_shop_hides_full_in_game_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that shop hides full in game name when preference enabled."""
    account = SimpleNamespace(puuid="one", username="SecretName#NA")

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Return the configured user fixture for the requested Discord ID."""
        return SimpleNamespace(hide_ign=True, others_can_view_shop=False)

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account for the command under test."""
        return account

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embeds: list[discord.Embed], view: object) -> None:
            """Record the follow-up message sent through the fake interaction."""
            pass

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def storefront(self, _account: object) -> ShopData:
            """Return the configured storefront fixture for the requested account."""
            return ShopData([], [], [], 1, None)

    monkeypatch.setattr("src.cogs.valorant.shop.get_user", get_user)
    monkeypatch.setattr("src.cogs.valorant.shop.selected_account", selected_account)
    bot = SimpleNamespace(
        shop=Shop(),
        register_component=lambda *_args: None,
    )
    cog = ShopCog(bot)
    rendered: dict[str, object] = {}

    async def shop_view(_data, username, _owner_id, _puuid, *, hide_ign=False):
        """Return the expected shop embeds and interactive controls."""
        rendered["username"] = username
        rendered["hide_ign"] = hide_ign
        return [], None

    cog.shop_view = shop_view
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        response=Response(),
        followup=Followup(),
    )

    await ShopCog.shop.callback(cog, interaction, None)

    assert rendered == {"username": "Account", "hide_ign": True}


@pytest.mark.asyncio
async def test_account_switch_hides_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that account switch hides name when preference enabled."""
    target = SimpleNamespace(puuid="target", username="SecretName#NA")
    user = SimpleNamespace(hide_ign=True, current_account_id="current")
    sent: list[discord.Embed] = []

    async def list_accounts(_user_id: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        return [target]

    async def resolve_account(_user_id: int, _value: str) -> SimpleNamespace:
        """Resolve the requested account from the fixture list."""
        return target

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Return the configured user fixture for the requested Discord ID."""
        return user

    async def select_account(_user_id: int, _account: object) -> None:
        """Record the account selected by the command under test."""
        return None

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

    monkeypatch.setattr("src.cogs.valorant.accounts.list_accounts", list_accounts)
    monkeypatch.setattr("src.cogs.valorant.accounts.resolve_account", resolve_account)
    monkeypatch.setattr("src.cogs.valorant.accounts.get_user", get_user)
    monkeypatch.setattr("src.cogs.valorant.accounts.select_account", select_account)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    cog = AccountsCog(SimpleNamespace(register_component=lambda *_args: None))
    await AccountsCog.account.callback(cog, interaction, "target")

    assert "SecretName" not in sent[0].description
    assert "Account" in sent[0].description


@pytest.mark.asyncio
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

        async def battlepass(self, _account: object) -> dict[str, object]:
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
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await BattlepassCog.battlepass.callback(
        BattlepassCog(
            SimpleNamespace(gameplay=Gameplay(), emoji_service=EmojiService())
        ),
        interaction,
    )

    assert sent[0].title == "Account"
    assert "SecretName" not in sent[0].title


@pytest.mark.asyncio
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

        async def missions(self, selected: object) -> list[dict[str, object]]:
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
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await BattlepassCog.missions.callback(
        BattlepassCog(
            SimpleNamespace(gameplay=Gameplay(), emoji_service=EmojiService())
        ),
        interaction,
    )

    card, ephemeral = sent[0]
    assert card.title == "Your Missions"
    assert ephemeral is True
    assert len(card.fields) == 1
    assert card.fields[0].name.startswith("Weekly Missions · Expires <t:")
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


@pytest.mark.asyncio
async def test_testalerts_reports_temporary_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that testalerts reports temporary auth failure."""
    account = SimpleNamespace(username="Player#NA")
    alert = SimpleNamespace(account=account)
    sent: list[discord.Embed] = []

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account for the command under test."""
        return account

    async def first_alert(_user_id: int) -> SimpleNamespace:
        """Return the alert fixture used by the command under test."""
        return alert

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking and ephemeral

        def is_done(self) -> bool:
            """Report whether the fake interaction response has been sent."""
            return True

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
            """Record the follow-up message sent through the fake interaction."""
            assert ephemeral
            sent.append(embed)

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def ensure(self, _account: object) -> None:
            """Return the configured fake authentication result."""
            raise HTTPFailure("temporarily unavailable")

    monkeypatch.setattr("src.cogs.valorant.alerts.selected_account", selected_account)
    monkeypatch.setattr("src.cogs.valorant.alerts.first_alert", first_alert)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await AlertsCog.testalerts.callback(
        AlertsCog(SimpleNamespace(auth=Auth(), register_component=lambda *_args: None)),
        interaction,
    )

    assert "temporarily unavailable" in sent[0].description.lower()


def test_accounts_layout_marks_selected_account() -> None:
    """Verify that accounts layout marks selected account."""
    first = type("Account", (), {"puuid": "one", "username": "One#NA"})()
    second = type("Account", (), {"puuid": "two", "username": "Two#EU"})()
    card = AccountsCog._accounts_embed([first, second], "two")
    assert (card.description, card.fields) == ("1. One#NA\n2. **Two#EU**", [])


def test_accounts_paginate_after_discord_embed_field_limit() -> None:
    """Verify that accounts paginate after Discord embed field limit."""
    accounts = [
        type("Account", (), {"puuid": str(index), "username": f"Account {index}"})()
        for index in range(26)
    ]
    card = AccountsCog._accounts_embed(accounts, "25", 1)
    controls = AccountsCog._accounts_view(1, len(accounts), 1)
    assert (card.title, card.description, card.footer.text, controls is not None) == (
        "All your accounts with the bot:",
        "26. **Account 25**",
        "Page 2/2",
        True,
    )


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
    )
    assert [field.name for field in card.fields] == [
        "Current Tier",
        "Next Reward",
        "Type",
        "XP",
    ]
    assert card.image.url == "https://example.com/prime.png"
    assert card.fields[-1].value.endswith("<:ebar:2>" * 10)


def test_alert_keeps_qotix_direct_skin_input() -> None:
    """Verify that alert keeps Qotix direct skin input."""
    command = AlertsCog.alert
    assert [parameter.name for parameter in command.parameters] == ["skin"]


def test_alert_removal_control_fits_a_persistent_dm() -> None:
    """Verify that alert removal control fits a persistent DM."""
    button = OwnedActionButton("remove_alert", 123456789012345678, "12345678")
    assert len(button.item.custom_id) <= 100


def test_bot_preserves_discord_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that bot preserves Discord HTTP client."""
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotfraggBot(Settings.from_env())
    assert hasattr(bot.http, "static_login")
    assert bot.intents.dm_messages and bot.intents.guild_messages
    assert not bot.intents.message_content


@pytest.mark.asyncio
async def test_bot_stops_extensions_before_closing_shared_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that bot stops extensions before closing shared resources."""
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotfraggBot(Settings.from_env())
    events: list[str] = []

    class HTTP:
        """Stub the shared Riot client so request handling and shutdown can be observed."""

        async def close(self) -> None:
            """Record that the fake client or database connection was closed."""
            events.append("http")

    bot.riot_http = HTTP()

    async def close_database() -> None:
        """Record database shutdown during bot cleanup."""
        events.append("database")

    async def close_discord(_bot) -> None:
        """Record Discord client shutdown during bot cleanup."""
        events.append("extensions")

    monkeypatch.setattr("src.bot.close_database", close_database)
    monkeypatch.setattr("src.bot.flush_monitoring", lambda: events.append("monitoring"))
    monkeypatch.setattr(commands.AutoShardedBot, "close", close_discord)

    await bot.close()

    assert events == ["extensions", "http", "database", "monitoring"]


@pytest.mark.asyncio
async def test_deletedata_clears_cached_shops_after_database_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that deletedata clears cached shops after database delete."""
    events: list[object] = []
    accounts = [SimpleNamespace(puuid="first"), SimpleNamespace(puuid="second")]

    async def list_accounts(user_id: int) -> list[SimpleNamespace]:
        """Return the configured accounts for the requested Discord user."""
        events.append(("list", user_id))
        return accounts

    async def delete_user_data(user_id: int) -> bool:
        """Record deletion of the user's stored data."""
        events.append(("delete", user_id))
        return True

    class Shop:
        """Return deterministic storefront data and record account lookups for alert and command assertions."""

        async def clear_cached_storefront(self, account_id: str) -> None:
            """Record removal of the account's cached storefront."""
            events.append(("clear", account_id))

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking and ephemeral

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
            """Record the follow-up message sent through the fake interaction."""
            assert ephemeral

    monkeypatch.setattr("src.cogs.valorant.logout.list_accounts", list_accounts)
    monkeypatch.setattr("src.cogs.valorant.logout.delete_user_data", delete_user_data)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await LogoutCog.deletedata.callback(
        LogoutCog(SimpleNamespace(shop=Shop())), interaction, True
    )

    assert events == [
        ("list", 123),
        ("delete", 123),
        ("clear", "first"),
        ("clear", "second"),
    ]


@pytest.mark.asyncio
async def test_shop_deletion_cleanup_waits_for_storefront_headers_in_flight() -> None:
    """Verify that shop deletion cleanup waits for storefront headers in flight."""
    headers_started = asyncio.Event()
    release_headers = asyncio.Event()

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            headers_started.set()
            await release_headers.wait()
            return {"Authorization": "Bearer stale"}

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="deleted-account")
    data = SimpleNamespace(expires=datetime.now(UTC).timestamp() + 60)

    async def fetch(_account, _headers):
        """Return the configured result from the fake query or HTTP client."""
        service._cache[account.puuid] = data
        return data

    service._fetch_storefront = fetch
    storefront = asyncio.create_task(service.storefront(account))
    await asyncio.wait_for(headers_started.wait(), timeout=1)
    cleanup = asyncio.create_task(service.clear_cached_storefront(account.puuid))
    await asyncio.sleep(0)
    assert not cleanup.done()

    release_headers.set()
    await asyncio.wait_for(storefront, timeout=1)
    await asyncio.wait_for(cleanup, timeout=1)

    assert account.puuid not in service._cache


@pytest.mark.asyncio
async def test_tasks_cog_awaits_cancelled_background_loops() -> None:
    """Verify that tasks cog awaits cancelled background loops."""
    finished = 0

    async def worker() -> None:
        """Simulate the cancellable background task used by the test."""
        nonlocal finished
        try:
            await asyncio.Event().wait()
        finally:
            finished += 1

    class Loop:
        """Expose a running task and record cancellation for cog-shutdown assertions."""

        def __init__(self, task: asyncio.Task[None]) -> None:
            """Retain the worker task whose shutdown and cancellation are asserted."""
            self.task = task

        def get_task(self) -> asyncio.Task[None]:
            """Return the fake background loop's current task."""
            return self.task

        def cancel(self) -> None:
            """Cancel the fake task and record the cancellation."""
            self.task.cancel()

    loops = [Loop(asyncio.create_task(worker())) for _ in range(4)]
    await asyncio.sleep(0)
    cog = SimpleNamespace(
        daily_alerts=loops[0],
        version_refresh=loops[1],
        catalog_refresh=loops[2],
        log_flush=loops[3],
        discord_log_handler=logging.NullHandler(),
    )

    await TasksCog.cog_unload(cog)

    assert finished == 4
    assert all(loop.get_task().done() for loop in loops)


@pytest.mark.asyncio
async def test_task_notifications_handle_http_errors_while_fetching_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that task notifications handle HTTP errors while fetching user."""
    fetched_ids: list[int] = []

    async def fetch_user(user_id: int) -> None:
        """Return the configured Discord user fixture."""
        fetched_ids.append(user_id)
        raise discord.HTTPException(
            SimpleNamespace(status=503, reason="Unavailable"), "unavailable"
        )

    async def currency(_name: str) -> str:
        """Return a stable currency marker for embed assertions."""
        return "VP"

    bot = SimpleNamespace(
        get_user=lambda _user_id: None,
        fetch_user=fetch_user,
        emoji_service=SimpleNamespace(currency=currency),
        config=SimpleNamespace(link_item_image=False),
    )
    cog = SimpleNamespace(bot=bot)
    user_id = 123

    monkeypatch.setattr("src.cogs.tasks.offer_cards", lambda *_args, **_kwargs: [])

    await TasksCog._send_alert(
        cog,
        user_id,
        SimpleNamespace(id=1, account=SimpleNamespace(username="Player#NA")),
        SimpleNamespace(
            skin=SimpleNamespace(name="Skin", icon=None),
            expires=0,
        ),
    )
    await TasksCog._send_daily_shop(
        cog,
        SimpleNamespace(id=user_id),
        SimpleNamespace(username="Player#NA"),
        SimpleNamespace(offers=[], expires=0),
    )
    await TasksCog._credentials_expired(cog, user_id)

    assert fetched_ids == [user_id, user_id, user_id]


@pytest.mark.asyncio
async def test_extra_cog_awaits_cancelled_background_loop() -> None:
    """Verify that extra cog awaits cancelled background loop."""
    finished = asyncio.Event()

    async def worker() -> None:
        """Simulate the cancellable background task used by the test."""
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    task = asyncio.create_task(worker())
    await asyncio.sleep(0)

    class Loop:
        """Expose a running task and record cancellation for cog-shutdown assertions."""

        def get_task(self) -> asyncio.Task[None]:
            """Return the fake background loop's current task."""
            return task

        def cancel(self) -> None:
            """Cancel the fake task and record the cancellation."""
            task.cancel()

    await ExtraCog.cog_unload(SimpleNamespace(shard_status=Loop()))

    assert finished.is_set()
    assert task.done()


@pytest.mark.asyncio
async def test_initial_release_command_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the initial release command groups remain available."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotfraggBot(Settings.from_env())
    for cog in (
        LoginCog(bot),
        LogoutCog(bot),
        AccountsCog(bot),
        SettingsCog(bot),
        ShopCog(bot),
        NightMarketCog(bot),
        BalanceCog(bot),
        AlertsCog(bot),
        BattlepassCog(bot),
        ExtraCog(bot),
        StaffCog(bot),
    ):
        await bot.add_cog(cog)
    assert {command.name for command in bot.tree.get_commands()} == {
        "login",
        "logout",
        "deletedata",
        "account",
        "accounts",
        "settings",
        "shop",
        "nightmarket",
        "balance",
        "alert",
        "alerts",
        "testalerts",
        "battlepass",
        "missions",
        "ping",
        "botinfo",
        "links",
        "suggest",
        "suggestion",
        "userinfo",
        "serverinfo",
    }


@pytest.mark.asyncio
async def test_ping_uses_database_probe_and_keeps_latency_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that ping uses database probe and keeps latency embed."""
    sent: dict[str, object] = {}
    probed = False

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool) -> None:
            """Record that the fake interaction response was deferred."""
            sent["thinking"] = thinking

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed) -> None:
            """Record the follow-up message sent through the fake interaction."""
            sent["embed"] = embed

    async def ping_database() -> None:
        """Stub and record the database health check."""
        nonlocal probed
        probed = True

    monkeypatch.setattr("src.cogs.extra.ping_database", ping_database)
    bot = SimpleNamespace(
        get_shard=lambda shard_id: SimpleNamespace(latency=0.041), latency=0.2
    )
    interaction = SimpleNamespace(
        response=Response(),
        followup=Followup(),
        guild=SimpleNamespace(shard_id=3),
    )

    await ExtraCog.ping.callback(ExtraCog(bot), interaction)

    card = sent["embed"]
    assert sent["thinking"] is True
    assert probed
    assert card.title == "🏓 Pong"
    assert [field.name for field in card.fields] == [
        "Websocket latency",
        "Database latency",
    ]
    assert card.fields[0].value == "41ms"
    assert card.fields[1].value.endswith("ms")


@pytest.mark.asyncio
async def test_setup_hook_passes_bot_settings_to_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that setup hook passes bot settings to database."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotfraggBot(Settings.from_env())
    database_call: dict[str, object] = {}

    async def connect_database(settings: Settings, *, generate_schemas: bool) -> None:
        """Capture the settings passed to database initialization."""
        database_call["settings"] = settings
        database_call["generate_schemas"] = generate_schemas

    async def no_op(*args: object, **kwargs: object) -> None:
        """Provide an intentionally empty callback for this test."""
        return None

    monkeypatch.setattr("src.bot.connect_database", connect_database)
    monkeypatch.setattr(bot.riot_http, "start", no_op)
    monkeypatch.setattr(bot.auth, "refresh_version", no_op)
    monkeypatch.setattr(bot.catalog, "load", no_op)
    monkeypatch.setattr(bot.emoji_service, "warm", no_op)
    monkeypatch.setattr(bot, "add_dynamic_items", lambda *_: None)
    monkeypatch.setattr(bot, "load_extension", no_op)
    monkeypatch.setattr(bot.tree, "sync", no_op)

    await bot.setup_hook()

    assert database_call == {
        "settings": bot.config,
        "generate_schemas": True,
    }
