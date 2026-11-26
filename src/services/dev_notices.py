"""Persisted dev maintenance state and announcement delivery helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from tortoise.exceptions import IntegrityError

from ..models import DevAnnouncement, DevAnnouncementRead, DevMaintenance
from ..views import OwnedActionButton
from ..views.ui import view
from .analytics import personal_data_write

if TYPE_CHECKING:
    from ..bot import BotFraggBot

log = logging.getLogger(__name__)

READ_ACTION = "dev_announce_read"
READ_CUSTOM_ID_PREFIX = f"botfragg:{READ_ACTION}:"


def _read_action(interaction: discord.Interaction[Any]) -> bool:
    """Return whether an interaction came from the Mark read button."""
    data = getattr(interaction, "data", None)
    custom_id = data.get("custom_id") if isinstance(data, dict) else None
    return isinstance(custom_id, str) and custom_id.startswith(READ_CUSTOM_ID_PREFIX)


class DevNotices:
    """Cache dev notices and gate or deliver them around interactions."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the owning bot and start with maintenance disabled."""
        self.bot = bot
        self._maintenance = False
        self._maintenance_reason: str | None = None
        self._latest_announcement: DevAnnouncement | None = None

    async def load(self) -> None:
        """Load persisted state, failing open when it cannot be read."""
        try:
            row = await DevMaintenance.get_or_none(id=1)
            latest = await DevAnnouncement.all().order_by("-created_at", "-id").first()
        except Exception:
            log.exception("Could not load the dev notice state")
            self._maintenance = False
            self._maintenance_reason = None
            self._latest_announcement = None
            return
        self._maintenance = bool(row.enabled) if row else False
        self._maintenance_reason = row.reason if row else None
        self._latest_announcement = latest

    async def set_maintenance(
        self, *, enabled: bool, reason: str | None, updated_by: int
    ) -> None:
        """Persist maintenance mode, clearing the reason when it is disabled."""
        stored_reason = reason if enabled else None
        await DevMaintenance.update_or_create(
            id=1,
            defaults={
                "enabled": enabled,
                "reason": stored_reason,
                "updated_by": updated_by,
            },
        )
        self._maintenance = enabled
        self._maintenance_reason = stored_reason

    async def publish(self, message: str, *, created_by: int) -> DevAnnouncement:
        """Persist an announcement and make it the newest one."""
        announcement = await DevAnnouncement.create(
            message=message, created_by=created_by
        )
        self._latest_announcement = announcement
        return announcement

    async def pending_announcement(self, user_id: int) -> DevAnnouncement | None:
        """Return the newest announcement unless this user has already read it."""
        try:
            announcement = self._latest_announcement
            if announcement is None:
                return None
            if await DevAnnouncementRead.exists(
                user_id=user_id, announcement_id=announcement.id
            ):
                return None
            return announcement
        except Exception:
            log.exception("Could not read the pending dev announcement")
            return None

    async def mark_read(self, user_id: int, announcement_id: int) -> None:
        """Record that a user read an announcement, ignoring repeated marks."""
        async with personal_data_write(user_id) as allowed:
            if not allowed:
                return
            try:
                await DevAnnouncementRead.get_or_create(
                    user_id=user_id, announcement_id=announcement_id
                )
            except IntegrityError:
                # A concurrent click may insert the unique row before this commits.
                if not await DevAnnouncementRead.exists(
                    user_id=user_id, announcement_id=announcement_id
                ):
                    raise

    def maintenance_embed(self, locale: discord.Locale | str | None) -> discord.Embed:
        """Build the private embed shown while maintenance blocks an interaction."""
        text = self.bot.translator.text
        card = discord.Embed(
            title=text(locale, "dev-maintenance-title"),
            description=text(locale, "dev-maintenance-description"),
            colour=0xFAA61A,
        )
        if self._maintenance_reason:
            card.add_field(
                name=text(locale, "dev-maintenance-reason"),
                value=self._maintenance_reason,
                inline=False,
            )
        return card

    async def allow(self, interaction: discord.Interaction[Any]) -> bool:
        """Allow an interaction unless maintenance blocks it, failing open."""
        try:
            if interaction.type is discord.InteractionType.autocomplete:
                return True
            if not self._maintenance:
                return True
            if await self.bot.is_owner(interaction.user):
                return True
            if _read_action(interaction):
                return True
            await interaction.response.send_message(
                embed=self.maintenance_embed(interaction.locale), ephemeral=True
            )
            return False
        except Exception:
            log.exception("Could not enforce the dev maintenance gate")
            return True

    async def deliver(self, interaction: discord.Interaction[Any]) -> None:
        """Send the newest unread announcement privately, swallowing errors."""
        try:
            if interaction.type is discord.InteractionType.autocomplete:
                return
            if _read_action(interaction):
                return
            if self._maintenance and not await self.bot.is_owner(interaction.user):
                return
            announcement = await self.pending_announcement(interaction.user.id)
            if announcement is None:
                return
            locale = interaction.locale
            card = discord.Embed(
                title=self.bot.translator.text(locale, "dev-announcement-title"),
                description=announcement.message,
                colour=0x5865F2,
            )
            button = OwnedActionButton(
                READ_ACTION,
                interaction.user.id,
                str(announcement.id),
                label=self.bot.translator.text(locale, "dev-announcement-read-button"),
            )
            controls = view(button)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=card, view=controls, ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=card, view=controls, ephemeral=True
                )
        except Exception:
            log.exception("Could not deliver the dev announcement")
