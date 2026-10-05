"""Commands for creating, viewing, removing, and testing skin alerts."""

from __future__ import annotations

from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import (
    create_alert,
    first_alert,
    list_alerts_page,
    remove_alert,
    selected_account,
)
from ...services.auth import AuthenticationRequired
from ...services.catalog import Skin
from ...services.http import HTTPFailure
from ...services.shop import ShopUnavailable
from ...views import OwnedActionButton, timestamp
from ._ui import embed, error, translated, view


class AlertsCog(commands.Cog):
    """Manage owner-scoped alert records and their persistent Discord controls."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register persistent alert-management actions."""
        self.bot = bot
        bot.register_component("remove_alert", self.remove_alert)
        bot.register_component("alert_page", self.alert_page)

    async def skin_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Return catalog skin matches suitable for Discord's autocomplete limit."""
        return [
            app_commands.Choice(
                name=(
                    skin.name_for(interaction.locale)
                    or self.bot.translator.text(interaction.locale, "common-unknown")
                )[:100],
                value=skin.uuid,
            )
            for skin in self.bot.catalog.search_skins(
                current or "a", locale=interaction.locale
            )
        ][:25]

    @app_commands.command(
        name=app_commands.locale_str("alert", key="command-alert-name"),
        description=app_commands.locale_str(
            "Add a skin alert delivered by DM", key="command-alert-description"
        ),
    )
    @app_commands.rename(
        skin=app_commands.locale_str("skin", key="option-alert-skin-name")
    )
    @app_commands.describe(
        skin=app_commands.locale_str(
            "Skin to receive an alert for",
            key="option-alert-skin-description",
        )
    )
    @app_commands.autocomplete(skin=skin_autocomplete)
    async def alert(self, interaction: discord.Interaction, skin: str) -> None:
        """Create a skin alert for the caller's active account and show a remove control."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        item = self.bot.catalog.get_skin(skin)
        if not item:
            matches = self.bot.catalog.search_skins(
                skin, locale=interaction.locale, limit=1
            )
            item = matches[0] if matches else None
        if not item:
            await error(interaction, "alert-skin-not-found")
            return
        skin_uuid = UUID(item.uuid)
        alert, created = await create_alert(interaction.user.id, account, skin_uuid)
        if not created:
            await error(
                interaction,
                "alert-already-exists",
                skin=self._skin_display_name(item, interaction.locale),
            )
            return
        card = self._created_embed(item, interaction.locale)
        controls = view(
            OwnedActionButton(
                "remove_alert",
                interaction.user.id,
                str(alert.id),
                label=translated(interaction, "alerts-remove-button"),
                style=discord.ButtonStyle.danger,
            )
        )
        await interaction.followup.send(embed=card, view=controls)

    @app_commands.command(
        name=app_commands.locale_str("alerts", key="command-alerts-name"),
        description=app_commands.locale_str(
            "Manage your active DM alerts", key="command-alerts-description"
        ),
    )
    async def alerts(self, interaction: discord.Interaction) -> None:
        """Show the caller's paginated alerts and owner-bound management controls."""
        await interaction.response.defer(thinking=True)
        if not await selected_account(interaction.user.id):
            await error(interaction, "error-not-registered")
            return
        card, controls = await self.manager_view(
            interaction.user.id, 0, interaction.locale
        )
        kwargs: dict[str, object] = {"embed": card}
        if controls is not None:
            kwargs["view"] = controls
        await interaction.followup.send(**kwargs)

    def _created_embed(self, skin: Skin, locale: discord.Locale) -> discord.Embed:
        """Build the confirmation card for a newly created skin alert."""
        card = embed(
            self.bot.translator.text(
                locale, "alert-created", skin=self._skin_display_name(skin, locale)
            )
        )
        if skin.icon:
            card.url = skin.icon
            card.set_thumbnail(url=skin.icon)
        return card

    def _skin_display_name(self, skin: Skin | None, locale: discord.Locale) -> str:
        """Return a skin name prefixed with its tier emoji, if one exists."""
        if skin is None:
            return self.bot.translator.text(locale, "alert-unknown-skin")
        return self.bot.emoji_service.skin_name(
            skin.name_for(locale)
            or self.bot.translator.text(locale, "alert-unknown-skin"),
            skin.tier_uuid,
        )

    def _skin_emoji(self, skin: Skin | None) -> str | None:
        """Return a button emoji for a skin tier when one is available."""
        if skin is None:
            return None
        return self.bot.emoji_service.skin_emoji(skin.tier_uuid) or None

    async def manager_view(
        self, user_id: int, page: int, locale: discord.Locale
    ) -> tuple[discord.Embed, discord.ui.View | None]:
        """Render one alert page with per-alert removal and optional page controls."""
        page_data = await list_alerts_page(
            user_id, page, self.bot.config.alerts_per_page
        )
        if not page_data.total or not page_data.alerts:
            return (
                embed(message=self.bot.translator.text(locale, "alerts-empty")),
                None,
            )
        visible = page_data.alerts
        lines: list[str] = []
        for number, alert in enumerate(
            visible, page_data.page * page_data.page_size + 1
        ):
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            name = self._skin_display_name(skin, locale)
            lines.append(
                self.bot.translator.text(
                    locale, "alerts-list-entry", number=number, name=name
                )
            )
        card = embed(
            "\n".join(lines),
            title=self.bot.translator.text(locale, "alerts-title"),
        )
        if (
            page_data.total == 1
            and (skin := self.bot.catalog.get_skin(str(visible[0].skin_uuid)))
            and skin.icon
        ):
            card.set_thumbnail(url=skin.icon)
        controls = discord.ui.View(timeout=None)
        for alert in visible:
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            skin_name = skin.name_for(locale) if skin else ""
            controls.add_item(
                OwnedActionButton(
                    "remove_alert",
                    user_id,
                    f"{alert.id},{page_data.page}",
                    label=(
                        skin_name
                        or self.bot.translator.text(locale, "alert-unknown-skin")
                    )[:80],
                    emoji=self._skin_emoji(skin),
                    style=discord.ButtonStyle.danger,
                )
            )
        if page_data.pages > 1:
            controls.add_item(
                OwnedActionButton(
                    "alert_page", user_id, str(page_data.page - 1), emoji="◀"
                )
            )
            controls.add_item(
                OwnedActionButton(
                    "alert_page", user_id, str(page_data.page + 1), emoji="▶"
                )
            )
        return card, controls

    async def remove_alert(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Remove the selected owner-scoped alert and refresh or dismiss its controls."""
        await interaction.response.defer()
        raw_id, separator, raw_page = payload.partition(",")
        try:
            alert_id = int(raw_id)
            page = int(raw_page) if separator else None
        except ValueError:
            await error(interaction, "alert-control-invalid")
            return
        alert = await remove_alert(interaction.user.id, alert_id)
        if not alert:
            await error(interaction, "alert-no-longer-exists")
            return
        skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
        if page is not None:
            card, controls = await self.manager_view(
                interaction.user.id, page, interaction.locale
            )
            await interaction.edit_original_response(embed=card, view=controls)
            return
        await interaction.edit_original_response(view=None)
        await interaction.followup.send(
            embed=embed(
                self.bot.translator.text(
                    interaction.locale,
                    "alert-removed",
                    skin=self._skin_display_name(skin, interaction.locale)
                    if skin
                    else self.bot.translator.text(
                        interaction.locale, "alert-that-skin"
                    ),
                ),
            ),
            ephemeral=True,
        )

    async def alert_page(self, interaction: discord.Interaction, payload: str) -> None:
        """Validate a page payload and update the alert-management message."""
        await interaction.response.defer()
        try:
            page = int(payload)
        except ValueError:
            await error(interaction, "alert-page-invalid")
            return
        card, controls = await self.manager_view(
            interaction.user.id, page, interaction.locale
        )
        await interaction.edit_original_response(embed=card, view=controls)

    @app_commands.command(
        name=app_commands.locale_str("testalerts", key="command-testalerts-name"),
        description=app_commands.locale_str(
            "Test whether I can deliver alert DMs",
            key="command-testalerts-description",
        ),
    )
    async def testalerts(self, interaction: discord.Interaction) -> None:
        """Check login and shop availability, then send the caller a test alert DM."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        alert = await first_alert(interaction.user.id)
        if not account or not alert:
            await error(interaction, "test-alerts-needs-active-alert")
            return
        try:
            auth = await self.bot.auth.ensure(account)
        except HTTPFailure:
            await error(
                interaction,
                "error-riot-auth-temporarily-unavailable",
            )
            return
        if not auth.success:
            await error(interaction, "error-riot-login-expired")
            return
        try:
            shop = await self.bot.shop.storefront(alert.account)
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            if not skin:
                await error(interaction, "alert-skin-no-longer-in-catalog")
                return
            card = embed(
                self.bot.translator.text(
                    interaction.locale,
                    "alert-test-message",
                    skin=self._skin_display_name(skin, interaction.locale),
                    username=alert.account.username,
                    timestamp=timestamp(shop.expires),
                ),
            )
            if skin.icon:
                card.set_thumbnail(url=skin.icon)
            await interaction.user.send(
                embed=card,
                view=view(
                    OwnedActionButton(
                        "remove_alert",
                        interaction.user.id,
                        str(alert.id),
                        label=translated(interaction, "alerts-remove-button"),
                        style=discord.ButtonStyle.danger,
                    )
                ),
            )
        except ShopUnavailable:
            await error(
                interaction,
                "error-riot-services-unavailable",
            )
            return
        except AuthenticationRequired:
            await error(interaction, "error-riot-login-expired")
            return
        except discord.HTTPException:
            await error(
                interaction,
                "test-alerts-dm-failed",
            )
            return
        await interaction.followup.send(
            embed=embed(translated(interaction, "test-alerts-sent")),
            ephemeral=True,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the skin-alert commands and their persistent handlers."""
    await bot.add_cog(AlertsCog(bot))
