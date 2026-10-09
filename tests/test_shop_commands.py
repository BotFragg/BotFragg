"""Behavior and regression checks for shop commands."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest

from src.cogs.tasks import TasksCog
from src.cogs.valorant import shop as shop_module
from src.cogs.valorant.shop import (
    NightMarketCog,
    ShopCog,
)
from src.localization import BotFraggTranslator
from src.models import Account, User
from src.services.catalog import (
    Accessory,
    Bundle,
    CatalogService,
    Skin,
)
from src.services.shop import (
    KC_UUID,
    FeaturedBundle,
    FeaturedBundleItem,
    Offer,
    ShopData,
    ShopService,
)
from src.views import OwnedSelect
from src.views import shop as shop_views
from src.views.shop import add_skin_selector, offer_cards
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


@pytest.mark.parametrize("mode", ["command", "night", "nightmarket"])
async def test_incomplete_night_market_reports_unavailable(monkeypatch, mode):
    account = NS(puuid="synthetic")
    monkeypatch.setattr(
        shop_module, "selected_account", AsyncMock(return_value=account)
    )
    monkeypatch.setattr(
        shop_module, "account_for_user", AsyncMock(return_value=account)
    )
    data = ShopData([], [], [], 4_000_000_000, None, night_market_incomplete=True)
    bot = _localized_bot(
        shop=NS(storefront=AsyncMock(return_value=data)),
        register_component=lambda *_args: None,
    )
    interaction = _localized_interaction(
        user=NS(id=1),
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    if mode == "command":
        cog = NightMarketCog(bot)
        await cog.nightmarket.callback(cog, interaction)
    else:
        await ShopCog(bot).shop_mode(interaction, f"{mode},synthetic")
    sent = interaction.followup.send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert sent["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-riot-services-unavailable"
    )


async def test_empty_shared_shop_sends_a_view(monkeypatch):
    from src.cogs.valorant.shop import ShopCog
    from src.services.shop import ShopData

    account = SimpleNamespace(puuid="synthetic", username="Example#NA")
    account.user = NS(others_can_view_shop=True, hide_ign=False)
    account.persisted_row = lambda: NS(
        select_related=lambda *args: NS(get_or_none=AsyncMock(return_value=account))
    )
    monkeypatch.setattr(
        "src.cogs.valorant.shop.get_user",
        AsyncMock(
            return_value=SimpleNamespace(others_can_view_shop=True, hide_ign=False)
        ),
    )
    monkeypatch.setattr(
        "src.cogs.valorant.shop.selected_account", AsyncMock(return_value=account)
    )
    bot = SimpleNamespace(
        translator=BotFraggTranslator(),
        config=SimpleNamespace(link_item_image=False),
        shop=SimpleNamespace(
            storefront=AsyncMock(return_value=ShopData([], [], [], 4000000000, None))
        ),
        emoji_service=SimpleNamespace(currency=AsyncMock(return_value="VP")),
        register_component=lambda *args: None,
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.american_english,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await ShopCog.shop.callback(ShopCog(bot), interaction, SimpleNamespace(id=2))
    controls = interaction.followup.send.call_args.kwargs["view"]
    assert isinstance(controls, discord.ui.View)
    assert not controls.children


@pytest.mark.parametrize(
    ("viewer", "stage"), [(1, "storefront"), (1, "currency"), (2, "storefront")]
)
@pytest.mark.parametrize(
    "change", ["hide", "unshare", "delete", "recreate", "reassign"]
)
async def test_shop_rechecks_privacy_and_original_account(
    database, change, viewer, stage
):
    owner = await User.create(id=2, current_account_id="synthetic")
    account = await Account.create(
        puuid="synthetic", user=owner, username="SecretName#NA"
    )

    async def change_privacy():
        if change == "hide":
            await User.filter(id=owner.id).update(hide_ign=True)
        elif change == "unshare":
            await User.filter(id=owner.id).update(others_can_view_shop=False)
        elif change == "delete":
            await owner.delete()
        else:
            await account.delete()
            recipient = owner if change == "recreate" else await User.create(id=3)
            await Account.create(
                puuid=account.puuid, user=recipient, username="Replacement#NA"
            )

    async def storefront(_account):
        if stage == "storefront":
            await change_privacy()
        return ShopData([], [], [], 4_000_000_000, None)

    async def currency(_kind):
        if stage == "currency":
            await change_privacy()
        return "VP"

    bot = _localized_bot(
        register_component=lambda *args: None,
        config=NS(link_item_image=False),
        shop=NS(storefront=storefront),
        emoji_service=NS(currency=currency),
    )
    interaction = _localized_interaction(
        user=NS(id=viewer),
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await ShopCog.shop.callback(ShopCog(bot), interaction, NS(id=owner.id))

    sent = interaction.followup.send.call_args.kwargs
    if change == "hide" or (change == "unshare" and viewer == owner.id):
        header = sent["embeds"][0].description
        if change == "hide":
            assert "SecretName" not in header
            assert "Account" in header
        else:
            assert "SecretName" in header
        assert not sent.get("ephemeral", False)
    else:
        assert sent["ephemeral"] is True
        assert "view" not in sent


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
        "Daily shop",
        [Offer(skin, 1775, 1)],
        "VP",
        link_item_image=True,
        unknown_skin_name="Unknown",
    )
    assert (len(cards), cards[1].colour.value, cards[1].thumbnail.url) == (
        2,
        0x009984,
        "https://example.com/prime.png",
    )
    discounted = offer_cards(
        "Night Market",
        [Offer(skin, 1775, 1, 1000, 44)],
        "VP",
        link_item_image=False,
        unknown_skin_name="Unknown",
    )
    assert discounted[1].description == "VP **1,000** ~~1,775~~ (-44%)"


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

    bot = _localized_bot(
        register_component=lambda *_args: None,
        catalog=SimpleNamespace(get_skin=lambda uuid: skin if uuid == "skin" else None),
        emoji_service=EmojiService(),
    )
    cog = ShopCog(bot)
    controls = discord.ui.View(timeout=None)
    add_skin_selector(
        controls,
        123,
        [Offer(skin, 1775, 1)],
        4_000_000_000,
        bot.emoji_service,
        TEST_TRANSLATOR,
        TEST_LOCALE,
    )
    selector = controls.children[0]

    assert selector.item.options[0].label == "Prime Vandal"
    assert str(selector.item.options[0].emoji) == "<:tier_deluxe:123456>"

    interaction = _localized_interaction(
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


async def test_daily_shop_view_includes_only_its_offers_in_skin_menu() -> None:
    """Verify the standard daily shop view exposes its current offer choices."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)

    accounts = [
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

    bot = _localized_bot(
        register_component=lambda *_args: None,
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=False),
    )
    cog = ShopCog(bot)
    embeds, controls = cog.shop_view(
        ShopData(
            [Offer(skin, 1775, 1)],
            [],
            [Offer(skin, 1775, 1)],
            4_000_000_000,
            4_000_000_000,
            featured_bundles=[
                FeaturedBundle(
                    "featured-id",
                    "bundle-id",
                    [],
                    1000,
                    800,
                    20,
                    4_000_000_000,
                )
            ],
        ),
        "Player",
        123,
        "account",
        accounts=accounts,
        vp="VP",
        locale=TEST_LOCALE,
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
        "shop_mode",
    ]
    assert controls.children[3].item.label == "Featured Bundles"
    assert controls.children[3].item.custom_id.endswith(":bundles,account")


async def test_bundles_command_renders_live_prices_and_tiered_skin_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the single current bundle includes exact prices and skin tier labels."""
    skin = Skin("skin", "offer", "Prime Phantom", None, "tier-uuid")
    bundle = Bundle("bundle-uuid", "Prime Collection", "Set", None, None)
    account = SimpleNamespace(
        puuid="account", persisted_row=lambda: NS(exists=AsyncMock(return_value=True))
    )
    data = ShopData(
        [],
        [],
        [],
        4_000_000_000,
        None,
        featured_bundles=[
            FeaturedBundle(
                "offer-id",
                "bundle-uuid",
                [FeaturedBundleItem("weapon", "skin", 2, 1000, 600)],
                2000,
                1200,
                40,
                4_000_000_000,
            )
        ],
    )

    async def selected_account(_owner_id: int):
        """Return the account fixture used by the command."""
        return account

    monkeypatch.setattr(shop_module, "selected_account", selected_account)

    class EmojiService:
        """Return stable labels for bundle card assertions."""

        async def currency(self, _kind: str) -> str:
            """Return the fixture's VP currency label."""
            return "VP"

        def skin_name(self, name: str, _tier_uuid: str | None) -> str:
            """Prefix skin names with a fixture tier emoji."""
            return f"<:tier:1> {name}"

    class Shop:
        """Return the configured live bundle data."""

        async def storefront(self, _account):
            """Return the fixture's one featured bundle."""
            return data

    class Response:
        """Require the bundle command to defer before fetching the shop."""

        async def defer(self, *, thinking: bool) -> None:
            """Require the command to defer while loading the storefront."""
            assert thinking

    class Followup:
        """Record the bundle command response."""

        def __init__(self) -> None:
            """Initialize the captured command response."""
            self.message: dict[str, object] = {}

        async def send(self, **kwargs: object) -> None:
            """Capture the command's embeds and controls."""
            self.message = kwargs

    catalog = SimpleNamespace(
        get_bundle=lambda uuid: bundle if uuid == bundle.uuid else None,
        get_skin=lambda uuid: skin if uuid == skin.uuid else None,
    )
    bot = _localized_bot(
        register_component=lambda *_args: None,
        catalog=catalog,
        config=SimpleNamespace(link_item_image=False),
        emoji_service=EmojiService(),
        shop=Shop(),
    )
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    cog = ShopCog(bot)
    await cog.bundles.callback(cog, interaction)

    card = interaction.followup.message["embeds"][0]
    assert card.title == "Prime Collection"
    assert "Bundle price: VP **1,200** ~~2,000~~ (-40%)" in card.description
    assert len(interaction.followup.message["embeds"]) == 2
    item_card = interaction.followup.message["embeds"][1]
    assert item_card.title == "<:tier:1> Prime Phantom x2"
    assert item_card.description == "VP **600** ~~1,000~~ (-40%)"
    controls = interaction.followup.message["view"]
    assert controls.children == []


async def test_bundles_reports_missing_account_and_empty_featured_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `/bundles` reports unlinked accounts and accounts with no active offers."""

    class Response:
        """Capture command errors and support the normal defer path."""

        def __init__(self) -> None:
            """Initialize the captured response history."""
            self.messages: list[dict[str, object]] = []

        async def defer(self, *, thinking: bool) -> None:
            """Require the command to defer before account lookup."""
            assert thinking

        def is_done(self) -> bool:
            """Report that the initial interaction was already deferred."""
            return True

    class Followup:
        """Capture the command's follow-up response."""

        def __init__(self) -> None:
            """Initialize the captured follow-up payload."""
            self.message: dict[str, object] = {}

        async def send(self, **kwargs: object) -> None:
            """Capture the command's success or error response."""
            self.message = kwargs

    response = Response()
    followup = Followup()

    async def selected_account(_owner_id: int):
        """Report that the caller has no linked account for the first request."""
        return None

    monkeypatch.setattr(shop_module, "selected_account", selected_account)
    unregistered = _localized_interaction(
        user=SimpleNamespace(id=123), response=response, followup=followup
    )
    cog = ShopCog(_localized_bot(register_component=lambda *_args: None))
    await cog.bundles.callback(cog, unregistered)
    assert "`/login`" in followup.message["embed"].description
    assert followup.message["ephemeral"] is True

    account = SimpleNamespace(
        puuid="account", persisted_row=lambda: NS(exists=AsyncMock(return_value=True))
    )

    async def selected(_owner_id: int):
        """Return the linked account for the empty-list response check."""
        return account

    monkeypatch.setattr(shop_module, "selected_account", selected)

    class Shop:
        """Return a storefront without active bundle offers."""

        async def storefront(self, _account):
            """Return a storefront with no active featured bundles."""
            return ShopData([], [], [], 4_000_000_000, None)

    empty_followup = Followup()
    empty_interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=empty_followup
    )
    empty_cog = ShopCog(
        _localized_bot(
            register_component=lambda *_args: None,
            shop=Shop(),
        )
    )
    await empty_cog.bundles.callback(empty_cog, empty_interaction)
    assert (
        empty_followup.message["embeds"][0].description
        == "No bundles are currently featured."
    )


async def test_featured_bundle_view_has_no_account_selector_and_rejects_forged_items():
    """Keep live featured offers owner-scoped without an account selector."""
    offers = [
        FeaturedBundle(f"offer-{index}", f"asset-{index}", [], 1000, 800, 20, None)
        for index in (1, 2)
    ]
    metadata = {
        "asset-1": Bundle("asset-1", "Bundle One", None, None, None),
        "asset-2": Bundle("asset-2", "Bundle Two", None, None, None),
    }

    class EmojiService:
        """Provide the VP marker needed by the featured-bundle summary."""

        async def currency(self, _kind: str) -> str:
            """Return the fixture's VP label."""
            return "VP"

    cog = ShopCog(
        _localized_bot(
            register_component=lambda *_args: None,
            catalog=SimpleNamespace(get_bundle=metadata.get),
            emoji_service=EmojiService(),
        )
    )
    embeds, controls = await cog.featured_bundles_view(
        ShopData([], [], [], 0, None, featured_bundles=offers),
        123,
        "account",
        locale=TEST_LOCALE,
    )

    assert [item.title for item in embeds] == [
        "Featured Bundles",
        "Bundle One",
        "Bundle Two",
    ]
    assert [child.item.custom_id.split(":")[1] for child in controls.children] == [
        "shop_bundle"
    ]
    _, shop_controls = await cog.featured_bundles_view(
        ShopData([], [], [], 0, None, featured_bundles=offers),
        123,
        "account",
        locale=TEST_LOCALE,
        show_shop_button=True,
    )
    assert [child.item.custom_id.split(":")[1] for child in shop_controls.children] == [
        "shop_bundle",
        "shop_mode",
    ]
    assert shop_controls.children[1].item.label == "Skin shop"

    class Response:
        """Capture private rejections for invalid bundle choices."""

        def __init__(self) -> None:
            """Initialize the captured messages."""
            self.messages: list[dict[str, object]] = []

        async def send_message(self, content: str, **kwargs: object) -> None:
            """Record a private validation response."""
            self.messages.append({"content": content, **kwargs})

    selector = OwnedSelect(
        "shop_bundle",
        123,
        "account|command",
        options=[discord.SelectOption(label="Bundle One", value="offer-1")],
    )
    response = Response()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123),
        message=SimpleNamespace(components=[SimpleNamespace(children=[selector.item])]),
        response=response,
    )
    await cog.shop_bundle(interaction, "account|command|forged")
    assert response.messages[-1]["ephemeral"] is True


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

    bot = _localized_bot(
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
    interaction = _localized_interaction(
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


async def test_nightmarket_command_includes_skin_and_account_menus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Night Market slash-command offers receive both selectors."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)
    data = ShopData([], [], [Offer(skin, 1775, 1, 1000, 44)], 4_000_000_000, None)
    account = SimpleNamespace(puuid="account", username="Player#NA")
    other_account = SimpleNamespace(puuid="other", username="Other#NA")
    for item in (account, other_account):
        item.user = NS(hide_ign=False)
        row = NS(get_or_none=AsyncMock(return_value=item))
        item.persisted_row = lambda row=row: NS(select_related=lambda *args: row)

    async def selected_account(_owner_id: int) -> SimpleNamespace:
        """Return the account fixture for the Night Market command."""
        return account

    async def list_accounts(_owner_id: int) -> list[SimpleNamespace]:
        """Return two accounts so the selector is visible."""
        return [account, other_account]

    async def account_for_user(_owner_id: int, puuid: str) -> SimpleNamespace | None:
        """Return the account selected from the Night Market menu."""
        return other_account if puuid == "other" else None

    monkeypatch.setattr("src.cogs.valorant.shop.selected_account", selected_account)
    monkeypatch.setattr("src.cogs.valorant.shop.list_accounts", list_accounts)
    monkeypatch.setattr("src.cogs.valorant.shop.account_for_user", account_for_user)

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

    bot = _localized_bot(
        shop=Shop(),
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=False),
        register_component=lambda *_args: None,
    )
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123),
        response=Response(),
        followup=Followup(),
    )

    await NightMarketCog.nightmarket.callback(NightMarketCog(bot), interaction)

    controls = interaction.followup.message["view"]
    assert [child.item.custom_id.split(":")[1] for child in controls.children] == [
        "shop_skin",
        "shop_account",
    ]
    skin_selector, account_selector = [child.item for child in controls.children]
    assert [option.value for option in skin_selector.options] == ["skin"]
    assert account_selector.custom_id.endswith(":nightmarket")
    assert [option.value for option in account_selector.options] == [
        "account",
        "other",
    ]
    assert account_selector.options[0].default

    class SwitchResponse:
        """Accept the defer used while switching to another account."""

        async def defer(self) -> None:
            """Record the component interaction defer."""

    switched: dict[str, object] = {}

    async def edit_original_response(**kwargs: object) -> None:
        """Capture the Night Market view rendered after account switching."""
        switched.update(kwargs)

    switch_interaction = _localized_interaction(
        user=SimpleNamespace(id=123),
        response=SwitchResponse(),
        edit_original_response=edit_original_response,
    )
    await ShopCog(bot).shop_account(switch_interaction, "nightmarket|other")

    switched_controls = switched["view"]
    assert [
        child.item.custom_id.split(":")[1] for child in switched_controls.children
    ] == ["shop_skin", "shop_account"]
    assert switched_controls.children[1].item.custom_id.endswith(":nightmarket")


@pytest.mark.usefixtures("database")
async def test_daily_shop_dm_includes_skin_video_menu() -> None:
    """Verify daily-shop notification DMs include the shared skin selector."""
    skin = Skin("skin", "offer", "Prime Vandal", None, None)
    sent: dict[str, object] = {}

    class Target:
        """Capture the daily-shop DM sent by the task notification."""

        locale = TEST_LOCALE

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
    owner = await User.create(
        id=123, daily_shop_enabled=True, current_account_id="daily"
    )
    account = await Account.create(puuid="daily", user=owner, username="Player#NA")
    bot = _localized_bot(
        get_user=lambda _user_id: target,
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=False),
        register_component=lambda *_args: None,
    )

    await TasksCog._send_daily_shop(
        SimpleNamespace(bot=bot),
        owner,
        account,
        ShopData([Offer(skin, 1775, 1)], [], [], 4_000_000_000, None),
    )

    controls = sent["view"]
    selector = next(
        child
        for child in controls.children
        if child.item.custom_id.startswith("botfragg_select:shop_skin:")
    )
    assert [option.value for option in selector.item.options] == ["skin"]


async def test_shop_account_selector_hides_names_when_requested() -> None:
    """Verify that shop account selector hides names when requested."""
    accounts = [
        SimpleNamespace(puuid="one", username="SecretOne#NA"),
        SimpleNamespace(puuid="two", username="SecretTwo#EU"),
    ]

    controls = discord.ui.View(timeout=None)
    shop_views.add_account_selector(
        controls,
        123,
        "daily",
        "one",
        accounts=accounts,
        hide_ign=True,
        translator=TEST_TRANSLATOR,
        locale=TEST_LOCALE,
    )

    selector = controls.children[0]
    assert [option.label for option in selector.item.options] == [
        "Account 1",
        "Account 2",
    ]


async def test_shop_hides_full_in_game_name_when_preference_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that shop hides full in game name when preference enabled."""
    account = SimpleNamespace(puuid="one", username="SecretName#NA")
    account.user = NS(others_can_view_shop=False, hide_ign=True)
    account.persisted_row = lambda: NS(
        select_related=lambda *args: NS(get_or_none=AsyncMock(return_value=account))
    )

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
    monkeypatch.setattr(
        "src.cogs.valorant.shop.list_accounts", AsyncMock(return_value=[account])
    )
    bot = _localized_bot(
        shop=Shop(),
        register_component=lambda *_args: None,
        emoji_service=NS(currency=AsyncMock(return_value="VP")),
    )
    cog = ShopCog(bot)
    rendered: dict[str, object] = {}

    def shop_view(
        _data, username, _owner_id, _puuid, *, accounts, vp, hide_ign=False, locale=None
    ):
        """Return the expected shop embeds and interactive controls."""
        rendered["username"] = username
        rendered["hide_ign"] = hide_ign
        return [], None

    cog.shop_view = shop_view
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123),
        response=Response(),
        followup=Followup(),
    )

    await ShopCog.shop.callback(cog, interaction, None)

    assert rendered == {"username": "Account", "hide_ign": True}


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
    account.user = NS(hide_ign=False)
    account.persisted_row = lambda: NS(
        select_related=lambda *args: NS(get_or_none=AsyncMock(return_value=account))
    )
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

    async def list_accounts(_owner_id: int):
        """Return the configured accounts for the requested Discord user."""
        return [account, SimpleNamespace(puuid="two", username="Two#EU")]

    async def edit_original_response(*, embeds, view) -> None:
        """Record edits to the fake interaction's original response."""
        rendered["embeds"] = embeds
        rendered["view"] = view

    monkeypatch.setattr(shop_module, "account_for_user", account_for_user)
    monkeypatch.setattr(shop_module, "list_accounts", list_accounts)
    bot = _localized_bot(
        shop=Shop(),
        emoji_service=EmojiService(),
        config=SimpleNamespace(link_item_image=True),
        register_component=lambda *_args: None,
    )
    interaction = _localized_interaction(
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


@pytest.mark.parametrize(
    ("status", "body"),
    [(503, {}), (403, {}), (200, []), (200, {}), (200, {"data": []})],
)
async def test_accessory_shop_metadata_failure_returns_a_localized_error(
    database, status, body
):
    owner = await User.create(id=101)
    await Account.create(puuid="synthetic", username="Synthetic", user=owner)
    data = ShopData(
        [],
        [
            {
                "Offer": {
                    "Cost": {KC_UUID: 1500},
                    "Rewards": [
                        {
                            "ItemTypeID": "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475",
                            "ItemID": "spray",
                        }
                    ],
                }
            }
        ],
        [],
        4000000000,
        None,
    )
    request = AsyncMock(return_value=NS(status=status, data=body))
    catalog = CatalogService(NS(request=request))
    shop = ShopService(NS(), NS(), NS(), catalog)
    shop.storefront = AsyncMock(return_value=data)
    bot = NS(
        register_component=lambda *args: None,
        translator=BotFraggTranslator(),
        config=NS(link_item_image=True),
        emoji_service=NS(currency=AsyncMock(return_value="KC")),
        shop=shop,
    )
    interaction = NS(
        user=NS(id=101),
        client=bot,
        locale=discord.Locale.french,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    await ShopCog(bot).shop_mode(interaction, "accessory,synthetic")
    assert interaction.followup.send.await_count == 1
    assert interaction.followup.send.call_args.kwargs["ephemeral"] is True
    assert interaction.followup.send.call_args.kwargs["embed"].description == (
        bot.translator.text(interaction.locale, "error-riot-services-unavailable")
    )
    interaction.edit_original_response.assert_not_awaited()
    assert catalog._accessories == {}
    assert request.await_count == 1
