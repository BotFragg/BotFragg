"""Commands for daily, accessory, and Night Market shops and wallet balances."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotfraggBot
from ...services.accounts import (
    account_for_user,
    get_user,
    list_accounts,
    selected_account,
)
from ...services.auth import AuthenticationRequired
from ...services.shop import Offer, ShopData, ShopUnavailable
from ...views import OwnedActionButton, OwnedSelect, timestamp
from ._ui import _account_display_name, embed, error, view

TIER_COLOURS = {
    "0cebb8be-46d7-c12a-d306-e9907bfc5a25": 0x009984,
    "e046854e-406c-37f4-6607-19a9ba8426fc": 0xF99358,
    "60bca009-4182-7998-dee7-b8a2558dc369": 0xD1538C,
    "12683d76-48d7-84a3-4e09-6985794f0445": 0x5A9FE1,
    "411e4a55-4e59-7757-41f0-86a53f101bb5": 0xF9D563,
}


def offer_cards(
    header: str, offers: list[Offer], currency: str, *, link_item_image: bool
) -> list[discord.Embed]:
    """Render a heading and one tier-coloured embed for each skin offer."""
    result = [embed(header, colour=0x202225)]
    for offer in offers:
        item = embed(
            f"{currency} **{offer.price:,}**",
            title=offer.skin.name,
            colour=TIER_COLOURS.get(offer.skin.tier_uuid, 0),
        )
        if offer.skin.icon:
            if link_item_image:
                item.url = offer.skin.icon
            item.set_thumbnail(url=offer.skin.icon)
        result.append(item)
    return result


class ShopCog(commands.Cog):
    """Show the caller's daily shop and handle its account and mode controls."""

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the bot and register persistent shop-mode and account actions."""
        self.bot = bot
        bot.register_component("shop_mode", self.shop_mode)
        bot.register_component("shop_account", self.shop_account)

    @app_commands.command(name="shop", description="Show your current daily shop!")
    async def shop(
        self, interaction: discord.Interaction, user: discord.User | None = None
    ) -> None:
        """Show the caller's shop or a shop another user has chosen to share."""
        await interaction.response.defer(thinking=True)
        target = user or interaction.user
        settings = await get_user(target.id)
        if target.id != interaction.user.id and (
            not settings or not settings.others_can_view_shop
        ):
            await error(
                interaction, "That user is not registered or does not share their shop."
            )
            return
        account = await selected_account(target.id)
        if not account:
            await error(interaction, "That account is not registered. Try `/login`.")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, str(exc))
            return
        hide_ign = bool(settings and settings.hide_ign)
        username = _account_display_name(account.username, hide_ign=hide_ign)
        if target.id != interaction.user.id:
            await interaction.followup.send(
                embeds=offer_cards(
                    f"Daily shop for **{username}** (new shop {timestamp(data.expires)})",
                    data.offers,
                    await self.bot.emoji_service.currency("vp") or "VP",
                    link_item_image=self.bot.config.link_item_image,
                )
            )
            return
        embeds, controls = await self.shop_view(
            data,
            username,
            interaction.user.id,
            account.puuid,
            hide_ign=hide_ign,
        )
        await interaction.followup.send(embeds=embeds, view=controls)

    async def shop_view(
        self,
        data: ShopData,
        username: str,
        owner_id: int,
        puuid: str,
        *,
        hide_ign: bool = False,
    ) -> tuple[list[discord.Embed], discord.ui.View]:
        """Build the daily shop embeds and controls for accessories and other accounts."""
        controls = view(
            OwnedActionButton(
                "shop_mode",
                owner_id,
                f"accessory,{puuid}",
                label="Accessory shop",
            )
        )
        if data.night_market:
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    owner_id,
                    f"night,{puuid}",
                    label="Night Market",
                )
            )
        await self._add_accounts(controls, owner_id, "daily", puuid, hide_ign=hide_ign)
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        return (
            offer_cards(
                f"Daily shop for **{username}** (new shop {timestamp(data.expires)})",
                data.offers,
                vp,
                link_item_image=self.bot.config.link_item_image,
            ),
            controls,
        )

    async def shop_mode(self, interaction: discord.Interaction, payload: str) -> None:
        """Render the selected daily, Night Market, or accessory shop mode."""
        await interaction.response.defer()
        mode, separator, puuid = payload.partition(",")
        if not separator or mode not in {"daily", "night", "accessory"} or not puuid:
            await error(interaction, "That shop control is invalid.")
            return
        account = await account_for_user(interaction.user.id, puuid)
        if not account:
            await error(interaction, "That account is no longer available.")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, str(exc))
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(account.username, hide_ign=hide_ign)
        if mode == "daily":
            embeds, controls = await self.shop_view(
                data,
                username,
                interaction.user.id,
                puuid,
                hide_ign=hide_ign,
            )
        elif mode == "night":
            vp = await self.bot.emoji_service.currency("vp") or "VP"
            embeds = offer_cards(
                f"Night Market for **{username}** (ends {timestamp(data.night_market_expires or data.expires)})",
                data.night_market,
                vp,
                link_item_image=self.bot.config.link_item_image,
            )
            controls = view(
                OwnedActionButton(
                    "shop_mode",
                    interaction.user.id,
                    f"daily,{puuid}",
                    label="Skin shop",
                )
            )
            await self._add_accounts(
                controls,
                interaction.user.id,
                "night",
                puuid,
                hide_ign=hide_ign,
            )
        else:
            kc = await self.bot.emoji_service.currency("kc") or "KC"
            embeds = [
                embed(
                    f"Accessory shop for **{username}** (new shop {timestamp(data.expires)})",
                )
            ]
            for accessory_offer in await self.bot.shop.accessory_offers(data):
                item = accessory_offer.item
                detail = f"`{item.title_text}`\n\n" if item.title_text else ""
                card = embed(
                    f"{detail}{kc} **{accessory_offer.price:,}**",
                    title=item.name,
                )
                if item.icon:
                    if self.bot.config.link_item_image:
                        card.url = item.icon
                    card.set_thumbnail(url=item.icon)
                embeds.append(card)
            if len(embeds) == 1:
                embeds[0].description += "\n\nYou've already got all the swagger!"
            controls = view(
                OwnedActionButton(
                    "shop_mode",
                    interaction.user.id,
                    f"daily,{puuid}",
                    label="Skin shop",
                )
            )
            await self._add_accounts(
                controls,
                interaction.user.id,
                "accessory",
                puuid,
                hide_ign=hide_ign,
            )
        await interaction.edit_original_response(embeds=embeds, view=controls)

    async def _add_accounts(
        self,
        controls: discord.ui.View,
        owner_id: int,
        mode: str,
        current: str,
        *,
        hide_ign: bool = False,
    ) -> None:
        """Add a private account selector when the owner has multiple accounts."""
        accounts = await list_accounts(owner_id)
        if len(accounts) > 1:
            controls.add_item(
                OwnedSelect(
                    "shop_account",
                    owner_id,
                    mode,
                    placeholder="Switch account",
                    options=[
                        discord.SelectOption(
                            label=(f"Account {index}" if hide_ign else item.username)[
                                :100
                            ],
                            value=item.puuid,
                            default=item.puuid == current,
                        )
                        for index, item in enumerate(accounts[:25], start=1)
                    ],
                )
            )

    async def shop_account(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Validate the selected account and reopen the corresponding shop mode."""
        mode, separator, puuid = payload.rpartition("|")
        if not separator or mode not in {"daily", "night", "accessory"} or not puuid:
            await interaction.response.defer()
            await error(interaction, "That account selection is invalid.")
            return
        await self.shop_mode(interaction, f"{mode},{puuid}")


class NightMarketCog(commands.Cog):
    """Display discounted Night Market offers for the selected Riot account."""

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the shared shop, account, and emoji services."""
        self.bot = bot

    @app_commands.command(
        name="nightmarket", description="Show your Night Market if there is one."
    )
    async def nightmarket(self, interaction: discord.Interaction) -> None:
        """Fetch and render Night Market offers or report that none are active."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "You're not registered. Try `/login`.")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, str(exc))
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(account.username, hide_ign=hide_ign)
        if not data.night_market:
            await interaction.followup.send(
                embed=embed("**There is no Night Market currently!**")
            )
            return
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        cards = [
            embed(
                f"Night Market for **{username}** (ends {timestamp(data.night_market_expires or data.expires)})",
                colour=0xEAEEB2,
            )
        ]
        for offer in data.night_market:
            card = embed(
                f"{vp} **{offer.discount_price or offer.price:,}**\n{vp} ~~{offer.price:,}~~ (-{offer.discount_percent or 0}%)",
                title=offer.skin.name,
                colour=TIER_COLOURS.get(offer.skin.tier_uuid, 0),
            )
            if offer.skin.icon:
                card.set_thumbnail(url=offer.skin.icon)
            cards.append(card)
        await interaction.followup.send(embeds=cards)


class BalanceCog(commands.Cog):
    """Display the selected account's three VALORANT wallet balances."""

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the shared shop and user-preference services."""
        self.bot = bot

    @app_commands.command(
        name="balance",
        description="Show your VALORANT Points, Radianite, and Kingdom Credits",
    )
    async def balance(self, interaction: discord.Interaction) -> None:
        """Fetch and display VP, Radianite, and Kingdom Credit balances."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "You're not registered. Try `/login`.")
            return
        try:
            wallet = await self.bot.shop.wallet(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, str(exc))
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(account.username, hide_ign=hide_ign)
        card = embed("Your current balance", title=username)
        for name, key, value in (
            ("VALORANT Points", "vp", wallet["vp"]),
            ("Radianite Points", "rp", wallet["rp"]),
            ("Kingdom Credits", "kc", wallet["kc"]),
        ):
            card.add_field(
                name=name,
                value=f"{await self.bot.emoji_service.currency(key) or key.upper()} **{value:,}**",
                inline=True,
            )
        await interaction.followup.send(embed=card)


async def setup(bot: BotfraggBot) -> None:
    """Register the shop, Night Market, and wallet-balance cogs."""
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(NightMarketCog(bot))
    await bot.add_cog(BalanceCog(bot))
