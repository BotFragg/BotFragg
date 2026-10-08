"""Commands for skin shops, featured bundles, and balances."""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...localization import BotFraggTranslator
from ...services.accounts import (
    account_for_user,
    get_user,
    selected_account,
)
from ...services.auth import AuthenticationRequired
from ...services.catalog import Bundle, Skin, localized_text
from ...services.http import HTTPFailure
from ...services.shop import (
    FeaturedBundle,
    FeaturedBundleItem,
    ShopData,
    ShopUnavailable,
)
from ...views import OwnedActionButton, OwnedSelect, timestamp
from ...views.shop import (
    TIER_COLOURS,
    _price_line,
    add_account_selector,
    add_skin_selector,
    offer_cards,
)
from ...views.ui import _account_display_name, embed, error, translated, view

log = logging.getLogger(__name__)


class ShopCog(commands.Cog):
    """Show shops and bundles for the caller's linked account."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register persistent shop-mode and account actions."""
        self.bot = bot
        bot.register_component("shop_mode", self.shop_mode)
        bot.register_component("shop_account", self.shop_account)
        bot.register_component("shop_skin", self.shop_skin)
        bot.register_component("shop_variant", self.shop_variant)
        bot.register_component("shop_bundle", self.shop_bundle)

    @app_commands.command(
        name=app_commands.locale_str("shop", key="command-shop-name"),
        description=app_commands.locale_str(
            "Show your current daily shop!", key="command-shop-description"
        ),
    )
    @app_commands.rename(
        user=app_commands.locale_str("user", key="option-shop-user-name")
    )
    @app_commands.describe(
        user=app_commands.locale_str(
            "User whose shared shop to view",
            key="option-shop-user-description",
        )
    )
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
            await error(interaction, "shop-user-not-sharing")
            return
        account = await selected_account(target.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        hide_ign = bool(settings and settings.hide_ign)
        username = _account_display_name(
            account.username,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        if target.id != interaction.user.id:
            controls = view()
            add_skin_selector(
                controls,
                interaction.user.id,
                data.offers,
                data.expires,
                self.bot.emoji_service,
                self.bot.translator,
                interaction.locale,
            )
            await interaction.followup.send(
                embeds=offer_cards(
                    self.bot.translator.text(
                        interaction.locale,
                        "shop-daily-header",
                        username=username,
                        timestamp=timestamp(data.expires),
                    ),
                    data.offers,
                    await self.bot.emoji_service.currency("vp") or "VP",
                    link_item_image=self.bot.config.link_item_image,
                    unknown_skin_name=self.bot.translator.text(
                        interaction.locale, "common-unknown"
                    ),
                    emoji_service=self.bot.emoji_service,
                    locale=interaction.locale,
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
            locale=interaction.locale,
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
        locale: discord.Locale,
    ) -> tuple[list[discord.Embed], discord.ui.View]:
        """Build daily shop embeds, owned selectors, and available shop controls."""
        controls = view()
        add_skin_selector(
            controls,
            owner_id,
            data.offers,
            data.expires,
            self.bot.emoji_service,
            self.bot.translator,
            locale,
        )
        await add_account_selector(
            controls,
            owner_id,
            "daily",
            puuid,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=locale,
        )
        if data.night_market:
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    owner_id,
                    f"night,{puuid}",
                    label=self.bot.translator.text(locale, "shop-night-market-button"),
                )
            )
        if data.featured_bundles:
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    owner_id,
                    f"bundles,{puuid}",
                    label=self.bot.translator.text(
                        locale, "shop-featured-bundles-button"
                    ),
                )
            )
        controls.add_item(
            OwnedActionButton(
                "shop_mode",
                owner_id,
                f"accessory,{puuid}",
                label=self.bot.translator.text(locale, "shop-accessory-button"),
            )
        )
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        return (
            offer_cards(
                self.bot.translator.text(
                    locale,
                    "shop-daily-header",
                    username=username,
                    timestamp=timestamp(data.expires),
                ),
                data.offers,
                vp,
                link_item_image=self.bot.config.link_item_image,
                unknown_skin_name=self.bot.translator.text(locale, "common-unknown"),
                emoji_service=self.bot.emoji_service,
                locale=locale,
            ),
            controls,
        )

    @app_commands.command(
        name=app_commands.locale_str("bundles", key="command-bundles-name"),
        description=app_commands.locale_str(
            "Show bundles currently featured in your store.",
            key="command-bundles-description",
        ),
    )
    async def bundles(self, interaction: discord.Interaction) -> None:
        """Show the selected account's current featured bundle offers and controls."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        embeds, controls = await self.featured_bundles_view(
            data, interaction.user.id, account.puuid, locale=interaction.locale
        )
        await interaction.followup.send(embeds=embeds, view=controls)

    async def featured_bundles_view(
        self,
        data: ShopData,
        owner_id: int,
        puuid: str,
        *,
        locale: discord.Locale,
        selected_id: str | None = None,
        show_shop_button: bool = False,
    ) -> tuple[list[discord.Embed], discord.ui.View]:
        """Build current featured bundles with shop-style cards and controls."""
        offers = data.featured_bundles
        selected = next((offer for offer in offers if offer.id == selected_id), None)
        if selected or len(offers) == 1:
            cards = await self._featured_bundle_embeds(selected or offers[0], locale)
        elif offers:
            vp = await self.bot.emoji_service.currency("vp") or "VP"
            cards = [
                embed(
                    self.bot.translator.text(locale, "bundles-currently-featured"),
                    title=self.bot.translator.text(locale, "bundles-title"),
                    colour=0x202225,
                )
            ]
            for offer in offers[:9]:
                metadata = self._bundle_metadata(offer, locale)
                details = self._featured_price(offer, vp, locale)
                if offer.expires:
                    details += "\n" + self.bot.translator.text(
                        locale,
                        "shop-available-until",
                        timestamp=timestamp(offer.expires),
                    )
                card = embed(
                    details,
                    title=(
                        metadata.name_for(locale)
                        or self.bot.translator.text(locale, "common-unknown")
                    )[:256],
                    colour=0x202225,
                )
                if metadata.icon:
                    card.set_thumbnail(url=metadata.icon)
                cards.append(card)
            if len(offers) > 9:
                cards[0].description += "\n" + self.bot.translator.text(
                    locale, "bundles-omitted", count=len(offers) - 9
                )
        else:
            cards = [
                embed(
                    self.bot.translator.text(locale, "bundles-none-featured"),
                    title=self.bot.translator.text(locale, "bundles-title"),
                    colour=0x202225,
                )
            ]

        controls = view()
        source = "shop" if show_shop_button else "command"
        if len(offers) > 1:
            controls.add_item(
                OwnedSelect(
                    "shop_bundle",
                    owner_id,
                    f"{puuid}|{source}",
                    placeholder=self.bot.translator.text(
                        locale, "bundles-select-placeholder"
                    ),
                    options=[
                        discord.SelectOption(
                            label=(
                                self._bundle_metadata(offer, locale).name_for(locale)
                                or self.bot.translator.text(locale, "common-unknown")
                            )[:100],
                            value=offer.id,
                            default=offer.id == selected_id,
                        )
                        for offer in offers[:25]
                    ],
                    empty_option_label=self.bot.translator.text(
                        locale, "common-unavailable"
                    ),
                )
            )
        if show_shop_button:
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    owner_id,
                    f"daily,{puuid}",
                    label=self.bot.translator.text(locale, "shop-skin-button"),
                )
            )
        return cards, controls

    def _bundle_metadata(self, offer: FeaturedBundle, locale: discord.Locale) -> Bundle:
        """Resolve static bundle metadata or provide a safe live-offer fallback."""
        return (
            self.bot.catalog.get_bundle(offer.data_asset_id)
            or self.bot.catalog.get_bundle(offer.id)
            or Bundle(
                offer.data_asset_id,
                self.bot.translator.text(locale, "shop-featured-bundle"),
                None,
                None,
                None,
            )
        )

    def _featured_price(
        self, offer: FeaturedBundle, vp: str, locale: discord.Locale
    ) -> str:
        """Format only Riot-supplied VP totals, retaining exact discount values."""
        base = offer.total_base_cost
        discounted = offer.total_discounted_cost
        if discounted is None:
            return (
                f"{vp} **{base:,}**"
                if base is not None
                else self.bot.translator.text(locale, "shop-price-unavailable")
            )
        return _price_line(vp, discounted, base, offer.total_discount_percent)

    async def _featured_item_embed(
        self, item: FeaturedBundleItem, vp: str, locale: discord.Locale
    ) -> discord.Embed | None:
        """Render one live bundle item in the shop's card, tier, and price style."""
        colour = 0x202225
        icon = None
        extra = ""
        if skin := self.bot.catalog.get_skin(item.item_id):
            name = self.bot.emoji_service.skin_name(
                skin.name_for(locale)
                or self.bot.translator.text(locale, "common-unknown"),
                skin.tier_uuid,
            )
            colour = TIER_COLOURS.get(skin.tier_uuid, 0)
            icon = skin.icon
        else:
            try:
                accessory = await self.bot.catalog.accessory(
                    item.item_type_id, item.item_id
                )
            except HTTPFailure as exc:
                log.warning(
                    "Could not fetch featured bundle item metadata "
                    "(type=%s, id=%s): %s",
                    item.item_type_id,
                    item.item_id,
                    exc,
                )
                return None
            if not accessory:
                log.warning(
                    "No catalog metadata for featured bundle item (type=%s, id=%s)",
                    item.item_type_id,
                    item.item_id,
                )
                return None
            name = accessory.name_for(locale)
            icon = accessory.icon
            title_text = accessory.title_text_for(locale)
            extra = f"`{title_text}`\n\n" if title_text else ""
        name = name or self.bot.translator.text(locale, "common-unknown")
        if item.amount > 1:
            name += f" x{item.amount}"
        final_price = (
            item.discounted_price
            if item.discounted_price is not None
            else item.base_price
        )
        price = (
            _price_line(vp, final_price, item.base_price)
            if final_price is not None
            else self.bot.translator.text(locale, "shop-price-unavailable")
        )
        card = embed(extra + price, title=name[:256], colour=colour)
        if icon:
            if self.bot.config.link_item_image:
                card.url = icon
            card.set_thumbnail(url=icon)
        return card

    async def _featured_bundle_embeds(
        self, offer: FeaturedBundle, locale: discord.Locale
    ) -> list[discord.Embed]:
        """Render a bundle summary and up to nine shop-style item cards."""
        metadata = self._bundle_metadata(offer, locale)
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        bundle_name = metadata.name_for(locale) or self.bot.translator.text(
            locale, "common-unknown"
        )
        title = bundle_name.strip().casefold()
        description = [
            "\n".join(
                line for line in value.splitlines() if line.strip().casefold() != title
            ).strip()
            for value in (
                metadata.subtitle_for(locale),
                metadata.description_for(locale),
            )
            if value
        ]
        description.append(
            self.bot.translator.text(
                locale,
                "bundles-price",
                price=self._featured_price(offer, vp, locale),
            )
        )
        if offer.expires:
            description.append(
                self.bot.translator.text(
                    locale,
                    "shop-available-until",
                    timestamp=timestamp(offer.expires),
                )
            )
        card = embed(
            "\n".join(value for value in description if value)[:1000],
            title=bundle_name[:256],
            colour=0x202225,
        )
        if metadata.icon:
            card.set_thumbnail(url=metadata.icon)
        max_items = 9
        visible_items = offer.items[:max_items]
        item_cards = await asyncio.gather(
            *(self._featured_item_embed(item, vp, locale) for item in visible_items)
        )
        displayed = [item_card for item_card in item_cards if item_card is not None]
        unresolved = len(visible_items) - len(displayed)
        hidden = len(offer.items) - len(visible_items)
        if unresolved:
            card.description = (
                (card.description or "")
                + "\n"
                + self.bot.translator.text(
                    locale, "bundles-unmatched-items", count=unresolved
                )
            )
        if hidden:
            card.description = (
                (card.description or "")
                + "\n"
                + self.bot.translator.text(locale, "bundles-hidden-items", count=hidden)
            )
        return [card, *displayed]

    async def shop_mode(self, interaction: discord.Interaction, payload: str) -> None:
        """Render the selected daily, Night Market, accessory, or bundle mode."""
        await interaction.response.defer()
        mode, separator, puuid = payload.partition(",")
        if (
            not separator
            or mode not in {"daily", "night", "nightmarket", "accessory", "bundles"}
            or not puuid
        ):
            await error(interaction, "shop-control-invalid")
            return
        account = await account_for_user(interaction.user.id, puuid)
        if not account:
            await error(interaction, "error-account-unavailable")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(
            account.username,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        if mode == "daily":
            embeds, controls = await self.shop_view(
                data,
                username,
                interaction.user.id,
                puuid,
                hide_ign=hide_ign,
                locale=interaction.locale,
            )
        elif mode == "bundles":
            embeds, controls = await self.featured_bundles_view(
                data,
                interaction.user.id,
                puuid,
                locale=interaction.locale,
                show_shop_button=True,
            )
        elif mode in {"night", "nightmarket"}:
            vp = await self.bot.emoji_service.currency("vp") or "VP"
            embeds = offer_cards(
                self.bot.translator.text(
                    interaction.locale,
                    "shop-night-market-header",
                    username=username,
                    timestamp=timestamp(data.night_market_expires or data.expires),
                ),
                data.night_market,
                vp,
                link_item_image=self.bot.config.link_item_image,
                unknown_skin_name=self.bot.translator.text(
                    interaction.locale, "common-unknown"
                ),
                emoji_service=self.bot.emoji_service,
                locale=interaction.locale,
            )
            controls = view()
            add_skin_selector(
                controls,
                interaction.user.id,
                data.night_market,
                data.night_market_expires or data.expires,
                self.bot.emoji_service,
                self.bot.translator,
                interaction.locale,
            )
            await add_account_selector(
                controls,
                interaction.user.id,
                mode,
                puuid,
                hide_ign=hide_ign,
                translator=self.bot.translator,
                locale=interaction.locale,
            )
            if mode == "night":
                controls.add_item(
                    OwnedActionButton(
                        "shop_mode",
                        interaction.user.id,
                        f"daily,{puuid}",
                        label=self.bot.translator.text(
                            interaction.locale, "shop-skin-button"
                        ),
                    )
                )
        else:
            kc = await self.bot.emoji_service.currency("kc") or "KC"
            embeds = [
                embed(
                    self.bot.translator.text(
                        interaction.locale,
                        "shop-accessory-header",
                        username=username,
                        timestamp=timestamp(data.expires),
                    ),
                )
            ]
            for accessory_offer in await self.bot.shop.accessory_offers(data):
                item = accessory_offer.item
                title_text = item.title_text_for(interaction.locale)
                detail = f"`{title_text}`\n\n" if title_text else ""
                card = embed(
                    f"{detail}{kc} **{accessory_offer.price:,}**",
                    title=item.name_for(interaction.locale)
                    or self.bot.translator.text(interaction.locale, "common-unknown"),
                )
                if item.icon:
                    if self.bot.config.link_item_image:
                        card.url = item.icon
                    card.set_thumbnail(url=item.icon)
                embeds.append(card)
            if len(embeds) == 1:
                embeds[0].description += "\n\n" + self.bot.translator.text(
                    interaction.locale, "shop-accessory-all-owned"
                )
            controls = view()
            await add_account_selector(
                controls,
                interaction.user.id,
                "accessory",
                puuid,
                hide_ign=hide_ign,
                translator=self.bot.translator,
                locale=interaction.locale,
            )
            controls.add_item(
                OwnedActionButton(
                    "shop_mode",
                    interaction.user.id,
                    f"daily,{puuid}",
                    label=self.bot.translator.text(
                        interaction.locale, "shop-skin-button"
                    ),
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

    async def shop_bundle(self, interaction: discord.Interaction, payload: str) -> None:
        """Revalidate a selected featured bundle against the caller's account and view."""
        puuid, separator, remainder = payload.partition("|")
        source, source_separator, bundle_id = remainder.partition("|")
        if not source_separator:
            bundle_id = source
            source = "command"
            selector_payload = puuid
        else:
            selector_payload = f"{puuid}|{source}"
        custom_id = (
            f"botfragg_select:shop_bundle:{interaction.user.id}:{selector_payload}"
        )
        if (
            not separator
            or not puuid
            or not bundle_id
            or source not in {"command", "shop"}
            or bundle_id not in self._selection_values(interaction, custom_id)
        ):
            await interaction.response.send_message(
                translated(interaction, "shop-bundle-selection-invalid"),
                ephemeral=True,
            )
            return
        account = await account_for_user(interaction.user.id, puuid)
        if not account:
            await interaction.response.send_message(
                translated(interaction, "error-account-unavailable"), ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        if not any(offer.id == bundle_id for offer in data.featured_bundles):
            await error(interaction, "shop-featured-bundle-unavailable")
            return
        embeds, controls = await self.featured_bundles_view(
            data,
            interaction.user.id,
            puuid,
            locale=interaction.locale,
            selected_id=bundle_id,
            show_shop_button=source == "shop",
        )
        await interaction.edit_original_response(embeds=embeds, view=controls)

    @staticmethod
    def _video_options(
        skin: Skin, translator: BotFraggTranslator, locale: discord.Locale
    ) -> list[discord.SelectOption]:
        """List playable levels and chromas within Discord's select-menu limit."""
        options: list[discord.SelectOption] = []
        seen: set[str] = set()
        for kind, items in (
            (translator.text(locale, "shop-level"), skin.levels),
            (translator.text(locale, "shop-chroma"), skin.chromas),
        ):
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
                name = (
                    localized_text(item.get("displayName"), locale)
                    or skin.name_for(locale)
                    or translator.text(locale, "common-unknown")
                )
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
                translated(interaction, "shop-skin-selection-invalid"),
                ephemeral=True,
            )
            return
        skin = self.bot.catalog.get_skin(skin_uuid)
        if skin is None:
            await interaction.response.send_message(
                translated(interaction, "shop-skin-unavailable"),
                ephemeral=True,
            )
            return
        options = self._video_options(skin, self.bot.translator, interaction.locale)
        if not options:
            await interaction.response.send_message(
                translated(interaction, "shop-no-variants"),
                ephemeral=True,
            )
            return
        controls = view(
            OwnedSelect(
                "shop_variant",
                interaction.user.id,
                f"{expires}|{skin.uuid}",
                placeholder=translated(interaction, "shop-variant-select-placeholder"),
                options=options,
                empty_option_label=translated(interaction, "common-unavailable"),
            )
        )
        skin_name = self.bot.emoji_service.skin_name(
            skin.name_for(interaction.locale)
            or self.bot.translator.text(interaction.locale, "common-unknown"),
            skin.tier_uuid,
        )
        await interaction.response.send_message(
            translated(interaction, "shop-variant-prompt", skin=skin_name),
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
                translated(interaction, "shop-video-selection-invalid"),
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
                translated(interaction, "shop-video-unavailable"), ephemeral=True
            )
            return
        kind, item = selected
        display_name = (
            skin.name_for(interaction.locale)
            if kind == "level"
            else localized_text(item.get("displayName"), interaction.locale)
            or skin.name_for(interaction.locale)
        ) or self.bot.translator.text(interaction.locale, "common-unknown")
        linked_name = self.bot.emoji_service.skin_name(display_name, skin.tier_uuid)
        await interaction.response.send_message(
            f"[{linked_name}]({item['streamedVideo']})", ephemeral=True
        )

    async def shop_account(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Validate the selected account and reopen the corresponding shop mode."""
        mode, separator, puuid = payload.rpartition("|")
        if (
            not separator
            or mode not in {"daily", "night", "nightmarket", "accessory"}
            or not puuid
        ):
            await interaction.response.defer()
            await error(interaction, "shop-account-selection-invalid")
            return
        await self.shop_mode(interaction, f"{mode},{puuid}")


class NightMarketCog(commands.Cog):
    """Display discounted Night Market offers for the selected Riot account."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the shared shop, account, and emoji services."""
        self.bot = bot

    @app_commands.command(
        name=app_commands.locale_str("nightmarket", key="command-nightmarket-name"),
        description=app_commands.locale_str(
            "Show your Night Market if there is one.",
            key="command-nightmarket-description",
        ),
    )
    async def nightmarket(self, interaction: discord.Interaction) -> None:
        """Fetch and render Night Market offers or report that none are active."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            data = await self.bot.shop.storefront(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(
            account.username,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        if not data.night_market:
            await interaction.followup.send(
                embed=embed(translated(interaction, "shop-night-market-none"))
            )
            return
        vp = await self.bot.emoji_service.currency("vp") or "VP"
        cards = offer_cards(
            self.bot.translator.text(
                interaction.locale,
                "shop-night-market-header",
                username=username,
                timestamp=timestamp(data.night_market_expires or data.expires),
            ),
            data.night_market,
            vp,
            link_item_image=False,
            unknown_skin_name=self.bot.translator.text(
                interaction.locale, "common-unknown"
            ),
            emoji_service=self.bot.emoji_service,
            header_colour=0xEAEEB2,
            locale=interaction.locale,
        )
        controls = view()
        add_skin_selector(
            controls,
            interaction.user.id,
            data.night_market,
            data.night_market_expires or data.expires,
            self.bot.emoji_service,
            self.bot.translator,
            interaction.locale,
        )
        await add_account_selector(
            controls,
            interaction.user.id,
            "nightmarket",
            account.puuid,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        await interaction.followup.send(
            embeds=cards, view=controls if controls.children else None
        )


class BalanceCog(commands.Cog):
    """Display the selected account's three VALORANT wallet balances."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the shared shop and user-preference services."""
        self.bot = bot

    @app_commands.command(
        name=app_commands.locale_str("balance", key="command-balance-name"),
        description=app_commands.locale_str(
            "Show your VALORANT Points, Radianite, and Kingdom Credits",
            key="command-balance-description",
        ),
    )
    async def balance(self, interaction: discord.Interaction) -> None:
        """Fetch and display VP, Radianite, and Kingdom Credit balances."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            wallet = await self.bot.shop.wallet(account)
        except (AuthenticationRequired, ShopUnavailable) as exc:
            await error(interaction, exc)
            return
        user = await get_user(interaction.user.id)
        hide_ign = bool(user and user.hide_ign)
        username = _account_display_name(
            account.username,
            hide_ign=hide_ign,
            translator=self.bot.translator,
            locale=interaction.locale,
        )
        card = embed(
            translated(interaction, "balance-summary"),
            title=username,
        )
        for name, key, value in (
            (
                translated(interaction, "balance-vp"),
                "vp",
                wallet["vp"],
            ),
            (
                translated(interaction, "balance-rp"),
                "rp",
                wallet["rp"],
            ),
            (
                translated(interaction, "balance-kc"),
                "kc",
                wallet["kc"],
            ),
        ):
            card.add_field(
                name=name,
                value=f"{await self.bot.emoji_service.currency(key) or key.upper()} **{value:,}**",
                inline=True,
            )
        await interaction.followup.send(embed=card)


async def setup(bot: BotFraggBot) -> None:
    """Register the shop, Night Market, and wallet-balance cogs."""
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(NightMarketCog(bot))
    await bot.add_cog(BalanceCog(bot))
