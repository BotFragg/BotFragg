"""Public account responses use current privacy after all preparation waits."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
import pytest_asyncio
from tortoise import Tortoise

from src.cogs.valorant import shop as shop_module
from src.cogs.valorant.battlepass import BattlepassCog
from src.cogs.valorant.shop import BalanceCog, NightMarketCog, ShopCog
from src.localization import BotFraggTranslator
from src.models import Account, User
from src.services.accounts import list_accounts
from src.services.catalog import Accessory, Bundle, Skin
from src.services.shop import FeaturedBundle, FeaturedBundleItem, Offer, ShopData

PREPARATION_WAITS = [
    ("shop", "fetch"),
    ("shop", "currency"),
    ("shop", "selector"),
    ("nightmarket", "fetch"),
    ("nightmarket", "currency"),
    ("nightmarket", "selector"),
    ("balance", "fetch"),
    ("balance", "currency"),
    ("battlepass", "fetch"),
    ("battlepass", "bars"),
    ("daily", "fetch"),
    ("daily", "currency"),
    ("daily", "selector"),
    ("night", "fetch"),
    ("night", "currency"),
    ("night", "selector"),
    ("nightmarket_control", "fetch"),
    ("nightmarket_control", "currency"),
    ("nightmarket_control", "selector"),
    ("accessory", "fetch"),
    ("accessory", "currency"),
    ("accessory", "selector"),
    ("accessory", "metadata"),
]
CASES = [
    (route, stage, change)
    for route, stage in PREPARATION_WAITS
    for change in ("hide", "delete", "recreate", "reassign")
] + [
    (route, stage, change)
    for route in ("bundles", "bundle_control", "bundles_control")
    for stage in ("fetch", "currency", "metadata")
    for change in ("delete", "recreate", "reassign")
]


@pytest_asyncio.fixture
async def response_accounts(migration_url):
    await Tortoise.init(
        db_url=migration_url, modules={"models": ["src.models.entities"]}
    )
    await Tortoise.generate_schemas()
    try:
        owner = await User.create(id=101, current_account_id="synthetic")
        account = await Account.create(
            puuid="synthetic", user=owner, username="SecretName#NA"
        )
        await Account.create(puuid="second", user=owner, username="OtherSecret#NA")
        yield owner, account
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize(("route", "stage", "change"), CASES)
async def test_public_response_rechecks_final_account_state(
    response_accounts, monkeypatch, route, stage, change
):
    owner, account = response_accounts
    if change != "hide":
        await User.filter(id=owner.id).update(hide_ign=True)
    changed = False

    async def mutate(wait):
        nonlocal changed
        if wait != stage or changed:
            return
        changed = True
        if change == "hide":
            await User.filter(id=owner.id).update(hide_ign=True)
        elif change == "delete":
            await owner.delete()
        else:
            await account.delete()
            recipient = owner if change == "recreate" else await User.create(id=202)
            await Account.create(
                puuid=account.puuid, user=recipient, username="Replacement#NA"
            )

    skin = Skin("skin", "offer", "Skin", None, None)
    featured = FeaturedBundle(
        "bundle",
        "bundle",
        [FeaturedBundleItem("card", "card", 1, 100, 100)],
        100,
        100,
        0,
        4_000_000_000,
    )
    data = ShopData(
        [Offer(skin, 100, 4_000_000_000)],
        [],
        [Offer(skin, 100, 4_000_000_000)],
        4_000_000_000,
        None,
        featured_bundles=[featured],
    )

    async def storefront(_account):
        await mutate("fetch")
        return data

    async def wallet(_account):
        await mutate("fetch")
        return {"vp": 10, "rp": 20, "kc": 30}

    async def battlepass(_account, **kwargs):
        await mutate("fetch")
        return {
            "act": "Act",
            "level": 1,
            "progress": 1,
            "next_level_xp": 10,
            "end": datetime.now(UTC),
            "next_reward": {"type": "Currency", "name": None, "xp": 10, "icon": None},
        }

    async def currency(_kind):
        await mutate("currency")
        return "VP"

    async def bars():
        await mutate("bars")
        return "F", "E"

    async def accounts(user_id):
        rows = await list_accounts(user_id)
        await mutate("selector")
        return rows

    async def accessory(*args):
        await mutate("metadata")
        return Accessory("Card", None)

    async def accessory_offers(_data):
        await mutate("metadata")
        return []

    monkeypatch.setattr(shop_module, "list_accounts", accounts)
    bot = NS(
        translator=BotFraggTranslator(),
        register_component=lambda *args: None,
        config=NS(link_item_image=False),
        shop=NS(
            storefront=storefront, wallet=wallet, accessory_offers=accessory_offers
        ),
        gameplay=NS(battlepass=battlepass),
        emoji_service=NS(
            currency=currency,
            battlepass_bars=bars,
            skin_name=lambda name, tier: name,
            skin_emoji=lambda tier: "",
        ),
        catalog=NS(
            get_skin=lambda uuid: None,
            accessory=accessory,
            get_bundle=lambda uuid: Bundle("bundle", "Bundle", None, None, None),
        ),
    )
    interaction = NS(
        user=NS(id=owner.id),
        client=bot,
        locale=discord.Locale.american_english,
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    roots = {
        "shop": ShopCog,
        "nightmarket": NightMarketCog,
        "balance": BalanceCog,
        "battlepass": BattlepassCog,
        "bundles": ShopCog,
    }
    if route in roots:
        await getattr(roots[route], route).callback(roots[route](bot), interaction)
    elif route == "bundle_control":
        interaction.message = NS(
            components=[
                NS(
                    children=[
                        NS(
                            custom_id=f"botfragg_select:shop_bundle:{owner.id}:synthetic|command",
                            options=[NS(value="bundle")],
                        )
                    ]
                )
            ]
        )
        await ShopCog(bot).shop_bundle(interaction, "synthetic|command|bundle")
    else:
        mode = route.removesuffix("_control")
        await ShopCog(bot).shop_mode(interaction, f"{mode},synthetic")

    assert changed, (route, stage)
    if change != "hide":
        interaction.edit_original_response.assert_not_awaited()
        sent = interaction.followup.send.call_args.kwargs
        assert sent["ephemeral"] is True
        assert "view" not in sent and "embeds" not in sent
    else:
        call = (
            interaction.followup.send.call_args
            if route in roots
            else interaction.edit_original_response.call_args
        )
        cards = call.kwargs.get("embeds") or [call.kwargs["embed"]]
        assert all("Secret" not in str(card.to_dict()) for card in cards)
        controls = call.kwargs.get("view")
        if controls:
            assert "Secret" not in str(controls.to_components())
