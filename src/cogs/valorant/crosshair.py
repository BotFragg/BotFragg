"""Commands for viewing and sharing the caller's VALORANT crosshairs."""

from __future__ import annotations

import asyncio
import io
import math
from collections.abc import Sequence
from time import monotonic

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...models import Account
from ...services.accounts import account_for_user, selected_account
from ...services.auth import AuthenticationRequired
from ...services.crosshair import CrosshairProfile, CrosshairUnavailable
from ...services.http import DISCORD_HTTP_ERRORS, HTTPFailure
from ...views.ui import DARK, embed, error, translated

MAX_OPTIONS = 25
VIEW_TIMEOUT = 900
SHARE_COOLDOWN_SECONDS = 30
SHARE_CONFIRM_TIMEOUT = 120


def _share_target(
    interaction: discord.Interaction,
) -> tuple[discord.abc.Messageable | None, str | None]:
    """Return a channel that accepts a public card, or the matching error key."""
    guild = getattr(interaction, "guild", None)
    channel = getattr(interaction, "channel", None)
    if (
        guild is None
        or guild.me is None
        or not isinstance(channel, discord.abc.Messageable)
    ):
        return None, "crosshair-share-guild-only"
    permissions_for = getattr(channel, "permissions_for", None)
    permissions = permissions_for(guild.me) if permissions_for else None
    if permissions is None or not (
        permissions.send_messages
        and permissions.embed_links
        and permissions.attach_files
    ):
        return None, "crosshair-share-no-permission"
    return channel, None


class CrosshairView(discord.ui.View):
    """Owner-scoped profile selector for one crosshair message."""

    def __init__(
        self,
        cog: CrosshairCog,
        interaction: discord.Interaction,
        account: Account,
        profiles: Sequence[CrosshairProfile],
        selected: CrosshairProfile,
    ) -> None:
        """Build the selector from the caller's profiles."""
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.owner_id = interaction.user.id
        self.account = account
        self.profiles = list(profiles)
        self.selected = selected
        options = []
        for profile in self._visible(profiles):
            options.append(
                discord.SelectOption(
                    label=profile.name[:100],
                    value=str(profile.index),
                    description=(
                        translated(interaction, "crosshair-current-profile")
                        if profile.current
                        else None
                    ),
                    default=profile.index == selected.index,
                )
            )
        self.add_item(CrosshairSelect(interaction, options))
        if getattr(interaction, "guild", None) is not None:
            self.add_item(ShareButton(interaction))
        self.add_item(RefreshButton(interaction))

    @staticmethod
    def _visible(profiles: Sequence[CrosshairProfile]) -> list[CrosshairProfile]:
        """Keep the current profile first and cap the menu at Discord's limit."""
        if len(profiles) <= MAX_OPTIONS:
            return list(profiles)
        current = next(
            (profile for profile in profiles if profile.current), profiles[0]
        )
        rest = [profile for profile in profiles if profile is not current]
        return [current, *rest[: MAX_OPTIONS - 1]]

    async def _owned_account(self, interaction: discord.Interaction) -> Account | None:
        """Recheck that the caller still owns this account, or report an error."""
        if interaction.user.id != self.owner_id:
            await error(interaction, "error-command-failed")
            return None
        current = await account_for_user(interaction.user.id, self.account.puuid)
        if current is None or current.created_at != self.account.created_at:
            await error(interaction, "error-not-registered")
            return None
        return current

    async def profile_selected(
        self, interaction: discord.Interaction, index: int
    ) -> None:
        """Recheck ownership and edit the message with the chosen profile."""
        current = await self._owned_account(interaction)
        if current is None:
            return
        profile = next(
            (profile for profile in self.profiles if profile.index == index),
            None,
        )
        if profile is None:
            await error(interaction, "crosshair-unavailable")
            return
        try:
            card, file, controls = await self.cog.build_card(
                interaction, current, self.profiles, profile
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        await interaction.response.edit_message(
            embed=card, attachments=[file], view=controls
        )

    async def refresh_profiles(self, interaction: discord.Interaction) -> None:
        """Refetch the profiles from Riot, update the cache, and redraw the message."""
        current = await self._owned_account(interaction)
        if current is None:
            return
        await interaction.response.defer()
        try:
            profiles = await self.cog.bot.crosshair.profiles(current, refresh=True)
        except AuthenticationRequired as exc:
            await error(interaction, exc)
            return
        except CrosshairUnavailable, HTTPFailure:
            await error(interaction, "crosshair-unavailable")
            return
        selected = next(
            (profile for profile in profiles if profile.index == self.selected.index),
            next((profile for profile in profiles if profile.current), profiles[0]),
        )
        try:
            card, file, controls = await self.cog.build_card(
                interaction, current, profiles, selected
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        await interaction.edit_original_response(
            embed=card, attachments=[file], view=controls
        )

    async def share_preview(self, interaction: discord.Interaction) -> None:
        """Show a private preview of the public share card."""
        if interaction.user.id != self.owner_id:
            await error(interaction, "error-command-failed")
            return
        _channel, failure = _share_target(interaction)
        if failure:
            await error(interaction, failure)
            return
        try:
            card, png = await self.cog.render_card(
                interaction, self.selected, locale="en-US"
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        card.set_footer(text=self.cog.share_footer(interaction))
        file = discord.File(io.BytesIO(png), filename="crosshair.png")
        confirm = ShareConfirmView(self.cog, self.selected, interaction)
        await interaction.response.send_message(
            content=translated(interaction, "crosshair-share-preview-description"),
            embed=card,
            file=file,
            view=confirm,
            ephemeral=True,
        )


class ShareButton(discord.ui.Button[CrosshairView]):
    """Open the private preview for a public crosshair share."""

    def __init__(self, interaction: discord.Interaction) -> None:
        """Label the button in the interaction's locale."""
        super().__init__(
            label=translated(interaction, "crosshair-share-button"),
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the share preview for the selected profile."""
        view = self.view
        if isinstance(view, CrosshairView):
            await view.share_preview(interaction)


class RefreshButton(discord.ui.Button[CrosshairView]):
    """Refetch the caller's profiles and redraw the message."""

    def __init__(self, interaction: discord.Interaction) -> None:
        """Label the button in the interaction's locale."""
        super().__init__(
            label=translated(interaction, "crosshair-refresh-button"),
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Refresh the owner's cached profiles from Riot."""
        view = self.view
        if isinstance(view, CrosshairView):
            await view.refresh_profiles(interaction)


class ShareConfirmView(discord.ui.View):
    """Confirm and post a public crosshair card."""

    def __init__(
        self,
        cog: CrosshairCog,
        profile: CrosshairProfile,
        interaction: discord.Interaction,
    ) -> None:
        """Bind the profile to share and localize the two buttons."""
        super().__init__(timeout=SHARE_CONFIRM_TIMEOUT)
        self.cog = cog
        self.profile = profile
        self.owner_id = interaction.user.id
        self.post.label = translated(interaction, "crosshair-share-post")
        self.cancel.label = translated(interaction, "crosshair-share-cancel")

    @discord.ui.button(label="Post", style=discord.ButtonStyle.success)
    async def post(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """Post the previewed crosshair to the current channel."""
        if interaction.user.id != self.owner_id:
            await error(interaction, "error-command-failed")
            return
        remaining = self.cog.share_cooldown_remaining(interaction.user.id)
        if remaining:
            await error(interaction, "crosshair-share-cooldown", seconds=remaining)
            return
        channel, failure = _share_target(interaction)
        if failure or channel is None:
            await error(interaction, failure or "crosshair-share-guild-only")
            return
        # Reserve before the first await so a double-click cannot post twice.
        self.cog.mark_shared(interaction.user.id)
        try:
            card, png = await self.cog.render_card(
                interaction, self.profile, locale="en-US"
            )
        except CrosshairUnavailable:
            self.cog.clear_shared(interaction.user.id)
            await error(interaction, "crosshair-unavailable")
            return
        card.set_footer(text=self.cog.share_footer(interaction))
        file = discord.File(io.BytesIO(png), filename="crosshair.png")
        try:
            await channel.send(
                embed=card,
                file=file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except DISCORD_HTTP_ERRORS:
            self.cog.clear_shared(interaction.user.id)
            await error(interaction, "crosshair-share-failed")
            return
        await interaction.response.edit_message(
            content=translated(interaction, "crosshair-share-success"),
            embed=None,
            attachments=[],
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """Dismiss the preview without posting anything."""
        if interaction.user.id != self.owner_id:
            await error(interaction, "error-command-failed")
            return
        await interaction.response.edit_message(
            content=translated(interaction, "crosshair-share-cancelled"),
            embed=None,
            attachments=[],
            view=None,
        )


class CrosshairSelect(discord.ui.Select):
    """Select one crosshair profile from the owner's saved profiles."""

    def __init__(
        self, interaction: discord.Interaction, options: list[discord.SelectOption]
    ) -> None:
        """Build the selector with the interaction's localized placeholder."""
        super().__init__(
            placeholder=translated(interaction, "crosshair-select-placeholder"),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Forward the selection to the owning view."""
        view = self.view
        if isinstance(view, CrosshairView):
            await view.profile_selected(interaction, int(self.values[0]))


class CrosshairCog(commands.Cog):
    """View and export the caller's VALORANT crosshair profiles."""

    crosshair_group = app_commands.Group(
        name=app_commands.locale_str("crosshair", key="command-crosshair-name"),
        description=app_commands.locale_str(
            "View and copy your in-game crosshairs",
            key="command-crosshair-description",
        ),
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot's crosshair service and start the share cooldown map."""
        self.bot = bot
        self._share_times: dict[int, float] = {}

    @crosshair_group.command(
        name=app_commands.locale_str("view", key="command-crosshair-view-name"),
        description=app_commands.locale_str(
            "Show your crosshair profile, export code, and preview",
            key="command-crosshair-view-description",
        ),
    )
    async def crosshair_view(self, interaction: discord.Interaction) -> None:
        """Show the caller's current crosshair, its code, and a profile menu."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        try:
            profiles = await self.bot.crosshair.profiles(account)
        except AuthenticationRequired as exc:
            await error(interaction, exc)
            return
        except CrosshairUnavailable, HTTPFailure:
            await error(interaction, "crosshair-unavailable")
            return
        current = next(
            (profile for profile in profiles if profile.current), profiles[0]
        )
        try:
            card, file, controls = await self.build_card(
                interaction, account, profiles, current
            )
        except CrosshairUnavailable:
            await error(interaction, "crosshair-unavailable")
            return
        await interaction.followup.send(
            embed=card, file=file, view=controls, ephemeral=True
        )

    async def build_card(
        self,
        interaction: discord.Interaction,
        account: Account,
        profiles: Sequence[CrosshairProfile],
        profile: CrosshairProfile,
    ) -> tuple[discord.Embed, discord.File, CrosshairView]:
        """Render one profile into an embed, attachment, and selector view."""
        card, png = await self.render_card(interaction, profile)
        if len(profiles) > MAX_OPTIONS:
            card.set_footer(
                text=translated(
                    interaction,
                    "crosshair-more-profiles",
                    count=len(profiles) - MAX_OPTIONS,
                )
            )
        file = discord.File(io.BytesIO(png), filename="crosshair.png")
        controls = CrosshairView(self, interaction, account, list(profiles), profile)
        return card, file, controls

    async def render_card(
        self,
        interaction: discord.Interaction,
        profile: CrosshairProfile,
        *,
        locale: discord.Locale | str | None = None,
    ) -> tuple[discord.Embed, bytes]:
        """Render one profile into an embed and PNG bytes."""
        language = locale or interaction.locale
        try:
            png = await asyncio.to_thread(self.bot.crosshair.render_png, profile)
        except ValueError:
            raise CrosshairUnavailable("The crosshair could not be rendered") from None
        card = embed(
            self.bot.translator.text(
                language, "crosshair-code-block", code=profile.code
            ),
            title=self.bot.translator.text(
                language,
                "crosshair-title",
                name=discord.utils.escape_markdown(profile.name),
            ),
            colour=DARK,
        )
        card.set_image(url="attachment://crosshair.png")
        return card, png

    def share_footer(self, interaction: discord.Interaction) -> str:
        """Return the English footer used on every public share card."""
        return self.bot.translator.text(
            "en-US",
            "crosshair-public-footer",
            user=discord.utils.escape_markdown(interaction.user.display_name),
        )

    def share_cooldown_remaining(self, user_id: int) -> int:
        """Return the seconds left before this user may share again."""
        last = self._share_times.get(user_id)
        if last is None:
            return 0
        return max(0, math.ceil(SHARE_COOLDOWN_SECONDS - (monotonic() - last)))

    def mark_shared(self, user_id: int) -> None:
        """Reserve a user's share slot and bound the tracking map."""
        self._share_times[user_id] = monotonic()
        if len(self._share_times) > 1000:
            cutoff = monotonic() - SHARE_COOLDOWN_SECONDS
            for key, value in list(self._share_times.items()):
                if value < cutoff:
                    del self._share_times[key]

    def clear_shared(self, user_id: int) -> None:
        """Release a reserved share slot after a failed post."""
        self._share_times.pop(user_id, None)


async def setup(bot: BotFraggBot) -> None:
    """Register the crosshair command group."""
    await bot.add_cog(CrosshairCog(bot))
