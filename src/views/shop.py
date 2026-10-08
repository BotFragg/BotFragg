"""Shared shop presentation for commands and notifications."""

from __future__ import annotations

import discord

from ..localization import BotFraggTranslator
from ..services.accounts import (
    list_accounts,
)
from ..services.emojis import ApplicationEmojiService
from ..services.shop import (
    Offer,
)
from ..views import OwnedSelect
from .ui import embed

TIER_COLOURS = {
    "0cebb8be-46d7-c12a-d306-e9907bfc5a25": 0x009984,
    "e046854e-406c-37f4-6607-19a9ba8426fc": 0xF99358,
    "60bca009-4182-7998-dee7-b8a2558dc369": 0xD1538C,
    "12683d76-48d7-84a3-4e09-6985794f0445": 0x5A9FE1,
    "411e4a55-4e59-7757-41f0-86a53f101bb5": 0xF9D563,
}


def _price_line(
    currency: str,
    final_price: int,
    original_price: int | None = None,
    discount_percent: int | None = None,
) -> str:
    """Format a current price and any original price discount on one line."""
    price = f"{currency} **{final_price:,}**"
    if original_price is None or original_price <= final_price:
        return price
    percent = discount_percent or max(
        1, round((original_price - final_price) * 100 / original_price)
    )
    return f"{price} ~~{original_price:,}~~ (-{percent}%)"


def offer_cards(
    header: str,
    offers: list[Offer],
    currency: str,
    *,
    link_item_image: bool,
    unknown_skin_name: str,
    emoji_service: ApplicationEmojiService | None = None,
    header_colour: int = 0x202225,
    locale: object | None = None,
) -> list[discord.Embed]:
    """Render a heading and one tier-coloured embed for each skin offer."""
    result = [embed(header, colour=header_colour)]
    for offer in offers:
        skin_name = offer.skin.name_for(locale) or unknown_skin_name
        price = _price_line(
            currency,
            offer.discount_price if offer.discount_price is not None else offer.price,
            offer.price,
            offer.discount_percent,
        )
        item = embed(
            price,
            title=(
                emoji_service.skin_name(skin_name, offer.skin.tier_uuid)
                if emoji_service
                else skin_name
            ),
            colour=TIER_COLOURS.get(offer.skin.tier_uuid, 0),
        )
        if offer.skin.icon:
            if link_item_image:
                item.url = offer.skin.icon
            item.set_thumbnail(url=offer.skin.icon)
        result.append(item)
    return result


def add_skin_selector(
    controls: discord.ui.View,
    owner_id: int,
    offers: list[Offer],
    expires: int,
    emoji_service: ApplicationEmojiService,
    translator: BotFraggTranslator,
    locale: discord.Locale,
) -> None:
    """Add a menu containing only the skin offers rendered beside it."""
    options: list[discord.SelectOption] = []
    seen: set[str] = set()
    for offer in offers:
        skin = offer.skin
        if skin.uuid in seen:
            continue
        seen.add(skin.uuid)
        emoji = emoji_service.skin_emoji(skin.tier_uuid) or None
        options.append(
            discord.SelectOption(
                label=(
                    skin.name_for(locale) or translator.text(locale, "common-unknown")
                )[:100],
                value=skin.uuid,
                emoji=emoji,
            )
        )
        if len(options) == 25:
            break
    if options:
        controls.add_item(
            OwnedSelect(
                "shop_skin",
                owner_id,
                str(expires),
                placeholder=translator.text(locale, "shop-skin-select-placeholder"),
                options=options,
                empty_option_label=translator.text(locale, "common-unavailable"),
            )
        )


async def add_account_selector(
    controls: discord.ui.View,
    owner_id: int,
    mode: str,
    current: str,
    *,
    hide_ign: bool = False,
    translator: BotFraggTranslator,
    locale: discord.Locale,
) -> None:
    """Add a private account selector when the owner has multiple accounts."""
    accounts = await list_accounts(owner_id)
    if len(accounts) > 1:
        controls.add_item(
            OwnedSelect(
                "shop_account",
                owner_id,
                mode,
                placeholder=translator.text(locale, "shop-account-select-placeholder"),
                options=[
                    discord.SelectOption(
                        label=(
                            translator.text(locale, "shop-account-label", number=index)
                            if hide_ign
                            else item.username
                        )[:100],
                        value=item.puuid,
                        default=item.puuid == current,
                    )
                    for index, item in enumerate(accounts[:25], start=1)
                ],
                empty_option_label=translator.text(locale, "common-unavailable"),
            )
        )
