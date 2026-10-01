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
from ._ui import embed, error, view


class AlertsCog(commands.Cog):
    """Manage owner-scoped alert records and their persistent Discord controls."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register persistent alert-management actions."""
        self.bot = bot
        bot.register_component("remove_alert", self.remove_alert)
        bot.register_component("alert_page", self.alert_page)

    async def skin_autocomplete(
        self, _: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Return catalog skin matches suitable for Discord's autocomplete limit."""
        return [
            app_commands.Choice(name=skin.name[:100], value=skin.uuid)
            for skin in self.bot.catalog.search_skins(current or "a")
        ][:25]

    @app_commands.command(name="alert", description="Add a skin alert delivered by DM")
    @app_commands.autocomplete(skin=skin_autocomplete)
    async def alert(self, interaction: discord.Interaction, skin: str) -> None:
        """Create a skin alert for the caller's active account and show a remove control."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "You're not registered. Try `/login`.")
            return
        item = self.bot.catalog.get_skin(skin)
        if not item:
            matches = self.bot.catalog.search_skins(skin, limit=1)
            item = matches[0] if matches else None
        if not item:
            await error(interaction, "Couldn't find a skin with that name.")
            return
        skin_uuid = UUID(item.uuid)
        alert, created = await create_alert(interaction.user.id, account, skin_uuid)
        if not created:
            await error(
                interaction,
                f"**{self._skin_display_name(item)}** is already in your alert list.",
            )
            return
        card = self._created_embed(item)
        controls = view(
            OwnedActionButton(
                "remove_alert",
                interaction.user.id,
                str(alert.id),
                label="Remove Alert",
                style=discord.ButtonStyle.danger,
            )
        )
        await interaction.followup.send(embed=card, view=controls)

    @app_commands.command(name="alerts", description="Manage your active DM alerts")
    async def alerts(self, interaction: discord.Interaction) -> None:
        """Show the caller's paginated alerts and owner-bound management controls."""
        await interaction.response.defer(thinking=True)
        if not await selected_account(interaction.user.id):
            await error(interaction, "You're not registered. Try `/login`.")
            return
        card, controls = await self.manager_view(interaction.user.id, 0)
        kwargs: dict[str, object] = {"embed": card}
        if controls is not None:
            kwargs["view"] = controls
        await interaction.followup.send(**kwargs)

    def _created_embed(self, skin: Skin) -> discord.Embed:
        """Build the confirmation card for a newly created skin alert."""
        card = embed(
            f"Successfully set an alert for the {self._skin_display_name(skin)}"
        )
        if skin.icon:
            card.url = skin.icon
            card.set_thumbnail(url=skin.icon)
        return card

    def _skin_display_name(self, skin: Skin | None) -> str:
        """Return a skin name prefixed with its tier emoji, if one exists."""
        if skin is None:
            return "Unknown skin"
        return self.bot.emoji_service.skin_name(skin.name, skin.tier_uuid)

    def _skin_emoji(self, skin: Skin | None) -> str | None:
        """Return a button emoji for a skin tier when one is available."""
        if skin is None:
            return None
        return self.bot.emoji_service.skin_emoji(skin.tier_uuid) or None

    async def manager_view(
        self, user_id: int, page: int
    ) -> tuple[discord.Embed, discord.ui.View | None]:
        """Render one alert page with per-alert removal and optional page controls."""
        page_data = await list_alerts_page(
            user_id, page, self.bot.config.alerts_per_page
        )
        if not page_data.total or not page_data.alerts:
            return (
                embed(message="You don't have any alerts."),
                None,
            )
        visible = page_data.alerts
        lines: list[str] = []
        for number, alert in enumerate(
            visible, page_data.page * page_data.page_size + 1
        ):
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            name = self._skin_display_name(skin)
            lines.append(f"**{number}.** **{name}**")
        card = embed("\n".join(lines), title="Your Alerts")
        if (
            page_data.total == 1
            and (skin := self.bot.catalog.get_skin(str(visible[0].skin_uuid)))
            and skin.icon
        ):
            card.set_thumbnail(url=skin.icon)
        controls = discord.ui.View(timeout=None)
        for alert in visible:
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            controls.add_item(
                OwnedActionButton(
                    "remove_alert",
                    user_id,
                    f"{alert.id},{page_data.page}",
                    label=(skin.name if skin else "Unknown skin")[:80],
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
            await error(interaction, "That alert control is invalid.")
            return
        alert = await remove_alert(interaction.user.id, alert_id)
        if not alert:
            await error(interaction, "That alert no longer exists.")
            return
        skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
        if page is not None:
            card, controls = await self.manager_view(interaction.user.id, page)
            await interaction.edit_original_response(embed=card, view=controls)
            return
        await interaction.edit_original_response(view=None)
        await interaction.followup.send(
            embed=embed(
                f"Removed {self._skin_display_name(skin) if skin else 'that skin'} from your alerts",
            ),
            ephemeral=True,
        )

    async def alert_page(self, interaction: discord.Interaction, payload: str) -> None:
        """Validate a page payload and update the alert-management message."""
        await interaction.response.defer()
        try:
            page = int(payload)
        except ValueError:
            await error(interaction, "That alert page is invalid.")
            return
        card, controls = await self.manager_view(interaction.user.id, page)
        await interaction.edit_original_response(embed=card, view=controls)

    @app_commands.command(
        name="testalerts", description="Test whether I can deliver alert DMs"
    )
    async def testalerts(self, interaction: discord.Interaction) -> None:
        """Check login and shop availability, then send the caller a test alert DM."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        alert = await first_alert(interaction.user.id)
        if not account or not alert:
            await error(interaction, "You need an active alert before testing alerts.")
            return
        try:
            auth = await self.bot.auth.ensure(account)
        except HTTPFailure:
            await error(
                interaction,
                "Riot authentication is temporarily unavailable. Try again later.",
            )
            return
        if not auth.success:
            await error(interaction, "Your Riot login has expired. Use `/login` again.")
            return
        try:
            shop = await self.bot.shop.storefront(alert.account)
            skin = self.bot.catalog.get_skin(str(alert.skin_uuid))
            if not skin:
                await error(interaction, "That alert skin is no longer in the catalog.")
                return
            card = embed(
                f"The **{self._skin_display_name(skin)}** is in **{alert.account.username}**'s daily shop.\nIt will be gone {timestamp(shop.expires)}.",
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
                        label="Remove alert",
                        style=discord.ButtonStyle.danger,
                    )
                ),
            )
        except ShopUnavailable:
            await error(
                interaction,
                "Riot services are temporarily unavailable. Try again later.",
            )
            return
        except AuthenticationRequired:
            await error(interaction, "Your Riot login has expired. Use `/login` again.")
            return
        except discord.HTTPException:
            await error(
                interaction,
                "I couldn't send the test alert. Make sure your DMs are enabled.",
            )
            return
        await interaction.followup.send(
            embed=embed("Successfully sent you a test alert."),
            ephemeral=True,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the skin-alert commands and their persistent handlers."""
    await bot.add_cog(AlertsCog(bot))
