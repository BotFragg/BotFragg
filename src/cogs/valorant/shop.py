"""Commands for daily, accessory, and Night Market shops and wallet balances."""

from __future__ import annotations

import time

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
from ...services.catalog import Skin
from ...services.emojis import ApplicationEmojiService
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
    header: str,
    offers: list[Offer],
    currency: str,
    *,
    link_item_image: bool,
    emoji_service: ApplicationEmojiService | None = None,
) -> list[discord.Embed]:
    """Render a heading and one tier-coloured embed for each skin offer."""
    result = [embed(header, colour=0x202225)]
    for offer in offers:
        price = (
            f"{currency} **{offer.discount_price:,}**\n"
            f"{currency} ~~{offer.price:,}~~ (-{offer.discount_percent or 0}%)"
            if offer.discount_price
            else f"{currency} **{offer.price:,}**"
        )
        item = embed(
            price,
            title=(
                emoji_service.skin_name(offer.skin.name, offer.skin.tier_uuid)
                if emoji_service
                else offer.skin.name
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
            discord.SelectOption(label=skin.name[:100], value=skin.uuid, emoji=emoji)
        )
        if len(options) == 25:
            break
    if options:
        controls.add_item(
            OwnedSelect(
                "shop_skin",
                owner_id,
                str(expires),
                placeholder="Choose a skin to view its videos",
                options=options,
            )
        )


class ShopCog(commands.Cog):
    """Show the caller's daily shop and handle its account and mode controls."""

    def __init__(self, bot: BotfraggBot) -> None:
        """Bind the bot and register persistent shop-mode and account actions."""
        self.bot = bot
        bot.register_component("shop_mode", self.shop_mode)
        bot.register_component("shop_account", self.shop_account)
        bot.register_component("shop_skin", self.shop_skin)
        bot.register_component("shop_variant", self.shop_variant)

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
            controls = view()
            add_skin_selector(
                controls,
                interaction.user.id,
                data.offers,
                data.expires,
                self.bot.emoji_service,
            )
            await interaction.followup.send(
                embeds=offer_cards(
                    f"Daily shop for **{username}** (new shop {timestamp(data.expires)})",
                    data.offers,
                    await self.bot.emoji_service.currency("vp") or "VP",
                    link_item_image=self.bot.config.link_item_image,
                    emoji_service=self.bot.emoji_service,
                ),
                view=controls if controls.children else None,
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
        controls = view()
        add_skin_selector(
            controls, owner_id, data.offers, data.expires, self.bot.emoji_service
        )
        await self._add_accounts(controls, owner_id, "daily", puuid, hide_ign=hide_ign)
        if data.night_market:
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    owner_id,
                    f"night,{puuid}",
                    label="Night Market",
                )
            )
        controls.add_item(
            OwnedActionButton(
                "shop_mode",
                owner_id,
                f"accessory,{puuid}",
                label="Accessory shop",
            )
        )
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        return (
            offer_cards(
                f"Daily shop for **{username}** (new shop {timestamp(data.expires)})",
                data.offers,
                vp,
                link_item_image=self.bot.config.link_item_image,
                emoji_service=self.bot.emoji_service,
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
                emoji_service=self.bot.emoji_service,
            )
            controls = view()
            add_skin_selector(
                controls,
                interaction.user.id,
                data.night_market,
                data.night_market_expires or data.expires,
                self.bot.emoji_service,
            )
            await self._add_accounts(
                controls,
                interaction.user.id,
                "night",
                puuid,
                hide_ign=hide_ign,
            )
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    interaction.user.id,
                    f"daily,{puuid}",
                    label="Skin shop",
                )
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
            controls = view()
            await self._add_accounts(
                controls,
                interaction.user.id,
                "accessory",
                puuid,
                hide_ign=hide_ign,
            )
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    interaction.user.id,
                    f"daily,{puuid}",
                    label="Skin shop",
                )
            )
        await interaction.edit_original_response(embeds=embeds, view=controls)

    @staticmethod
    def _selection_values(interaction: discord.Interaction, custom_id: str) -> set[str]:
        """Read the values actually offered by this message's matching select menu."""
        message = getattr(interaction, "message", None)
        values: set[str] = set()
        for row in getattr(message, "components", ()):
            for component in getattr(row, "children", ()):
                if getattr(component, "custom_id", None) == custom_id:
                    values.update(
                        str(option.value)
                        for option in getattr(component, "options", ())
                    )
                    return values
        return values

    @staticmethod
    def _video_options(skin: Skin) -> list[discord.SelectOption]:
        """List playable levels and chromas within Discord's select-menu limit."""
        options: list[discord.SelectOption] = []
        seen: set[str] = set()
        for kind, items in (("Level", skin.levels), ("Chroma", skin.chromas)):
            for item in items:
                uuid = str(item.get("uuid") or "")
                video = item.get("streamedVideo")
                if (
                    not uuid
                    or uuid in seen
                    or not isinstance(video, str)
                    or not video.startswith("https://")
                ):
                    continue
                name = str(item.get("displayName") or skin.name)
                options.append(
                    discord.SelectOption(label=f"{kind}: {name}"[:100], value=uuid)
                )
                seen.add(uuid)
                if len(options) == 25:
                    return options
        return options

    async def shop_skin(self, interaction: discord.Interaction, payload: str) -> None:
        """Open a private level/chroma menu for a skin offered in this message."""
        expiry, separator, skin_uuid = payload.rpartition("|")
        try:
            expires = int(expiry)
        except ValueError:
            expires = 0
        skin_menu_id = f"botfragg_select:shop_skin:{interaction.user.id}:{expiry}"
        if (
            not separator
            or expires <= time.time()
            or not skin_uuid
            or skin_uuid not in self._selection_values(interaction, skin_menu_id)
        ):
            await interaction.response.send_message(
                "That skin selection is no longer available. Run `/shop` again.",
                ephemeral=True,
            )
            return
        skin = self.bot.catalog.get_skin(skin_uuid)
        if skin is None:
            await interaction.response.send_message(
                "That skin is no longer in the catalog. Run `/shop` again.",
                ephemeral=True,
            )
            return
        options = self._video_options(skin)
        if not options:
            await interaction.response.send_message(
                "No level or chroma videos are available for this skin.",
                ephemeral=True,
            )
            return
        controls = view(
            OwnedSelect(
                "shop_variant",
                interaction.user.id,
                f"{expires}|{skin.uuid}",
                placeholder="Choose a level or chroma",
                options=options,
            )
        )
        skin_name = self.bot.emoji_service.skin_name(skin.name, skin.tier_uuid)
        await interaction.response.send_message(
            f"Choose a level or chroma video for {skin_name}.",
            view=controls,
            ephemeral=True,
        )

    async def shop_variant(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Privately return a selected video only when it belongs to that skin."""
        skin_context, separator, variant_uuid = payload.rpartition("|")
        expiry, skin_separator, skin_uuid = skin_context.partition("|")
        try:
            expires = int(expiry)
        except ValueError:
            expires = 0
        variant_menu_id = (
            f"botfragg_select:shop_variant:{interaction.user.id}:{expiry}|{skin_uuid}"
        )
        if (
            not separator
            or not skin_separator
            or expires <= time.time()
            or not skin_uuid
            or not variant_uuid
            or variant_uuid not in self._selection_values(interaction, variant_menu_id)
        ):
            await interaction.response.send_message(
                "That video selection is no longer available. Run `/shop` again.",
                ephemeral=True,
            )
            return
        skin = self.bot.catalog.get_skin(skin_uuid)
        selected = next(
            (
                (kind, item)
                for kind, items in (
                    ("level", skin.levels if skin else []),
                    ("chroma", skin.chromas if skin else []),
                )
                for item in items
                if str(item.get("uuid") or "") == variant_uuid
            ),
            None,
        )
        if (
            not selected
            or not isinstance(selected[1].get("streamedVideo"), str)
            or not selected[1]["streamedVideo"].startswith("https://")
        ):
            await interaction.response.send_message(
                "That level or chroma video is no longer available.", ephemeral=True
            )
            return
        kind, item = selected
        display_name = (
            skin.name if kind == "level" else str(item.get("displayName") or skin.name)
        )
        linked_name = self.bot.emoji_service.skin_name(display_name, skin.tier_uuid)
        await interaction.response.send_message(
            f"[{linked_name}]({item['streamedVideo']})", ephemeral=True
        )

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
                title=self.bot.emoji_service.skin_name(
                    offer.skin.name, offer.skin.tier_uuid
                ),
                colour=TIER_COLOURS.get(offer.skin.tier_uuid, 0),
            )
            if offer.skin.icon:
                card.set_thumbnail(url=offer.skin.icon)
            cards.append(card)
        controls = view()
        add_skin_selector(
            controls,
            interaction.user.id,
            data.night_market,
            data.night_market_expires or data.expires,
            self.bot.emoji_service,
        )
        await interaction.followup.send(
            embeds=cards, view=controls if controls.children else None
        )


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
