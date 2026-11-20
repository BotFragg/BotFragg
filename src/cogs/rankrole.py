"""Member self-service rank roles driven by a staff-configured panel."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..database import TRANSIENT_DATABASE_ERRORS
from ..models import RankRole, RankRolePanel
from ..services.accounts import selected_account
from ..services.auth import AuthenticationRequired
from ..services.http import DISCORD_HTTP_ERRORS, HTTPFailure
from ..services.profile import ProfileUnavailable
from ..views import PublicActionButton
from ..views.ui import embed, error, translated

log = logging.getLogger(__name__)

TIER_ROLES: tuple[tuple[str, str], ...] = (
    ("iron", "rankrole-tier-iron"),
    ("bronze", "rankrole-tier-bronze"),
    ("silver", "rankrole-tier-silver"),
    ("gold", "rankrole-tier-gold"),
    ("platinum", "rankrole-tier-platinum"),
    ("diamond", "rankrole-tier-diamond"),
    ("ascendant", "rankrole-tier-ascendant"),
    ("immortal", "rankrole-tier-immortal"),
    ("radiant", "rankrole-tier-radiant"),
)
TIER_GROUPS = tuple(group for group, _ in TIER_ROLES)
# Competitive tier ids per group; 0-2 and unknown values mean unranked.
TIER_RANGES: tuple[tuple[int, int, str], ...] = (
    (3, 5, "iron"),
    (6, 8, "bronze"),
    (9, 11, "silver"),
    (12, 14, "gold"),
    (15, 17, "platinum"),
    (18, 20, "diamond"),
    (21, 23, "ascendant"),
    (24, 26, "immortal"),
    (27, 27, "radiant"),
)
DEBOUNCE_SECONDS = 5.0
DASHBOARD_TIMEOUT = 300
SYNC_REASON = "Rank role sync"
# The first tier of each group carries the art the emoji service already ships.
TIER_EMOJI_TIERS: dict[str, int] = {
    "iron": 3,
    "bronze": 6,
    "silver": 9,
    "gold": 12,
    "platinum": 15,
    "diamond": 18,
    "ascendant": 21,
    "immortal": 24,
    "radiant": 27,
}


def tier_group(tier: int) -> str | None:
    """Map a competitive tier id to its rank group, or None when unranked."""
    for low, high, group in TIER_RANGES:
        if low <= tier <= high:
            return group
    return None


def _tier_key(group: str) -> str:
    """Return the locale key naming one rank group."""
    for name, key in TIER_ROLES:
        if name == group:
            return key
    return "rankrole-unset"


def _select_emoji(emoji: str) -> discord.PartialEmoji | None:
    """Convert a cached rank emoji into a select option emoji when present."""
    return discord.PartialEmoji.from_str(emoji) if emoji else None


def plan_changes(
    held: set[int], by_role: dict[int, str], target: int | None
) -> tuple[list[int], bool]:
    """Return the mapped roles to strip and whether the target must be added.

    Roles the bot does not map are never touched, and a member who already holds
    exactly the target role produces no Discord writes at all.
    """
    stale = sorted(
        role_id for role_id in held if role_id in by_role and role_id != target
    )
    return stale, target is not None and target not in held


def _one_item(item: discord.ui.Item[Any]) -> discord.ui.View:
    """Wrap a single component in a disposable view for an ephemeral step."""
    built = discord.ui.View(timeout=DASHBOARD_TIMEOUT)
    built.add_item(item)
    return built


async def _notice(
    interaction: discord.Interaction, key: str, **arguments: object
) -> None:
    """Reply with a plain localized line instead of an embed."""
    await interaction.followup.send(
        content=translated(interaction, key, **arguments), ephemeral=True
    )


async def _retry_write(
    operation: Callable[[], Awaitable[object]], failure: str
) -> bool:
    """Run one database write twice, reporting whether it eventually landed."""
    for attempt in range(2):
        try:
            await operation()
        except TRANSIENT_DATABASE_ERRORS:
            if attempt == 1:
                log.exception("%s", failure)
                return False
        else:
            return True
    return False


class RankRoleCog(commands.Cog):
    """Configure the rank role panel and serve its member controls."""

    rankrole_group = app_commands.Group(
        name=app_commands.locale_str("rankrole", key="command-rankrole-name"),
        description=app_commands.locale_str(
            "Let members claim the role for their rank",
            key="command-rankrole-description",
        ),
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the member-facing panel actions."""
        self.bot = bot
        self._recent: dict[int, float] = {}
        bot.register_component("rankrole_add", self.add_role)
        bot.register_component("rankrole_remove", self.remove_role)

    @rankrole_group.command(
        name=app_commands.locale_str("config", key="command-rankrole-config-name"),
        description=app_commands.locale_str(
            "Choose the panel channel and rank role mappings",
            key="command-rankrole-config-description",
        ),
    )
    async def config(self, interaction: discord.Interaction) -> None:
        """Open the staff dashboard for the panel and its mappings."""
        guild = interaction.guild
        if guild is None:
            await error(interaction, "error-guild-only")
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        await interaction.edit_original_response(
            embed=await self._dashboard_embed(interaction, guild),
            view=self._dashboard_view(interaction, guild),
        )

    async def _dashboard_embed(
        self, interaction: discord.Interaction, guild: discord.Guild
    ) -> discord.Embed:
        """Render the panel state, every mapping, and the gaps left to fill."""
        panel = await RankRolePanel.get_or_none(guild_id=guild.id)
        rows = await RankRole.filter(guild_id=guild.id)
        mapped = {row.tier_group: row.role_id for row in rows}
        channel = (
            f"<#{panel.channel_id}>"
            if panel is not None and panel.channel_id is not None
            else translated(interaction, "rankrole-unset")
        )
        if panel is not None and panel.message_id is not None:
            link = (
                f"https://discord.com/channels/{guild.id}/"
                f"{panel.channel_id}/{panel.message_id}"
            )
            posted = f"[{translated(interaction, 'rankrole-posted')}]({link})"
        else:
            posted = translated(interaction, "rankrole-not-posted")
        card = embed(
            translated(interaction, "rankrole-dashboard-purpose"),
            title=translated(interaction, "rankrole-title"),
        )
        card.add_field(
            name=translated(interaction, "rankrole-dashboard-panel-field"),
            value=f"{channel}\n{posted}",
            inline=True,
        )
        card.add_field(
            name=translated(interaction, "rankrole-dashboard-coverage-field"),
            value=translated(
                interaction,
                "rankrole-dashboard-coverage",
                mapped=len(mapped),
                total=len(TIER_GROUPS),
            ),
            inline=True,
        )
        ranks = []
        for group, key in TIER_ROLES:
            role_id = mapped.get(group)
            if role_id is None:
                continue
            emoji = self.bot.emoji_service.rank_emoji(TIER_EMOJI_TIERS[group])
            label = self.bot.translator.text(interaction.locale, key)
            ranks.append(f"{emoji} {label} → <@&{role_id}>".strip())
        card.add_field(
            name=translated(interaction, "rankrole-dashboard-mapped-field"),
            value="\n".join(ranks)
            if ranks
            else translated(interaction, "rankrole-dashboard-empty-mapped"),
            inline=False,
        )
        missing = [
            self.bot.translator.text(interaction.locale, key)
            for group, key in TIER_ROLES
            if group not in mapped
        ]
        card.add_field(
            name=translated(interaction, "rankrole-dashboard-unmapped-field"),
            value=" · ".join(missing)
            if missing
            else translated(interaction, "rankrole-dashboard-empty-unmapped"),
            inline=False,
        )
        card.set_footer(text=translated(interaction, "rankrole-dashboard-footer"))
        return card

    def _dashboard_view(
        self, interaction: discord.Interaction, guild: discord.Guild
    ) -> discord.ui.View:
        """Build the ephemeral dashboard controls for one staff session."""
        view = discord.ui.View(timeout=DASHBOARD_TIMEOUT)
        view.add_item(_ChannelPicker(self, interaction, guild))
        view.add_item(_MappingButton(self, interaction, guild))
        view.add_item(_ResetButton(self, interaction, guild))
        view.add_item(_PublishButton(self, interaction, guild))
        return view

    async def refresh_dashboard(
        self, interaction: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Redraw the staff dashboard after a change."""
        await interaction.edit_original_response(
            embed=await self._dashboard_embed(interaction, guild),
            view=self._dashboard_view(interaction, guild),
        )

    async def _safe_dashboard(
        self, interaction: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Redraw the dashboard on a failure path without raising again."""
        try:
            await self.refresh_dashboard(interaction, guild)
        except (*DISCORD_HTTP_ERRORS, *TRANSIENT_DATABASE_ERRORS):
            log.warning("Could not redraw the rank role dashboard")

    async def apply_mapping(
        self, guild: discord.Guild, group: str, role: discord.Role
    ) -> str | None:
        """Store one tier mapping, returning a locale key when it is refused."""
        if role.is_default() or role.managed:
            return "rankrole-role-invalid"
        if role >= guild.me.top_role:
            return "rankrole-hierarchy"
        await RankRole.update_or_create(
            guild_id=guild.id, tier_group=group, defaults={"role_id": role.id}
        )
        return None

    @staticmethod
    async def _panel_channel(
        guild: discord.Guild, channel_id: int
    ) -> discord.TextChannel | None:
        """Resolve the configured channel, returning None only when it is gone.

        Transient failures are left to propagate so callers never mistake a
        network error for a deleted channel.
        """
        resolved: discord.abc.GuildChannel | discord.Thread | None = guild.get_channel(
            channel_id
        )
        if resolved is None:
            try:
                resolved = await guild.fetch_channel(channel_id)
            except discord.NotFound:
                return None
        return resolved if isinstance(resolved, discord.TextChannel) else None

    async def retire_panel(
        self, interaction: discord.Interaction, guild: discord.Guild
    ) -> bool:
        """Delete the posted panel, or disable it when deletion is refused."""
        panel = await RankRolePanel.get_or_none(guild_id=guild.id)
        if panel is None or panel.channel_id is None or panel.message_id is None:
            return True
        try:
            channel = await self._panel_channel(guild, panel.channel_id)
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not resolve the rank role panel channel")
            return False
        if channel is None:
            await RankRolePanel.filter(guild_id=guild.id).update(message_id=None)
            return True
        try:
            message = await channel.fetch_message(panel.message_id)
        except discord.NotFound:
            message = None
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not read the rank role panel before retiring it")
            return False
        if message is not None:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except DISCORD_HTTP_ERRORS:
                try:
                    await message.edit(
                        content=translated(interaction, "rankrole-panel-retired"),
                        embed=None,
                        view=None,
                    )
                except DISCORD_HTTP_ERRORS:
                    log.warning("Could not retire the rank role panel message")
                    return False
        await RankRolePanel.filter(guild_id=guild.id).update(message_id=None)
        return True

    async def reset_all(
        self, dashboard: discord.Interaction, guild: discord.Guild, scope: str
    ) -> str | None:
        """Clear the panel, every mapping, or one tier, updating the panel safely.

        The live panel is always updated before stored data is discarded for
        good, so a refused edit leaves the database exactly as it was.
        """
        if scope == "panel":
            if not await self.retire_panel(dashboard, guild):
                await self._safe_dashboard(dashboard, guild)
                return "rankrole-panel-blocked"
            if not await _retry_write(
                lambda: RankRolePanel.filter(guild_id=guild.id).delete(),
                "Could not delete the rank role panel row after a reset",
            ):
                await self._safe_dashboard(dashboard, guild)
                return "error-command-failed"
        elif scope in TIER_GROUPS:
            removed = await RankRole.filter(guild_id=guild.id, tier_group=scope).first()
            await RankRole.filter(guild_id=guild.id, tier_group=scope).delete()
            try:
                if await RankRole.exists(guild_id=guild.id):
                    problem = await self.refresh_panel(dashboard)
                elif await self.retire_panel(dashboard, guild):
                    problem = None
                else:
                    problem = "rankrole-panel-blocked"
            except (*DISCORD_HTTP_ERRORS, *TRANSIENT_DATABASE_ERRORS):
                log.warning("Could not update the rank role panel after a reset")
                problem = "rankrole-panel-blocked"
            if problem is not None:
                if removed is not None and not await _retry_write(
                    lambda: RankRole.create(
                        guild_id=removed.guild_id,
                        tier_group=removed.tier_group,
                        role_id=removed.role_id,
                    ),
                    "Could not restore a rank role mapping after a reset",
                ):
                    # The tier is gone for good, so say so instead of
                    # blaming the panel.
                    problem = "rankrole-mapping-lost"
                await self._safe_dashboard(dashboard, guild)
                return problem
        else:
            if not await self.retire_panel(dashboard, guild):
                await self._safe_dashboard(dashboard, guild)
                return "rankrole-panel-blocked"
            if not await _retry_write(
                lambda: RankRole.filter(guild_id=guild.id).delete(),
                "Could not delete rank role mappings after a reset",
            ):
                await self._safe_dashboard(dashboard, guild)
                return "error-command-failed"
        await self._safe_dashboard(dashboard, guild)
        return None

    async def publish_panel(self, interaction: discord.Interaction) -> str | None:
        """Post or update the member panel, returning a locale key when blocked."""
        guild = interaction.guild
        if guild is None:
            return "error-guild-only"
        panel = await RankRolePanel.get_or_none(guild_id=guild.id)
        if panel is None or panel.channel_id is None:
            return "rankrole-needs-channel"
        rows = await RankRole.filter(guild_id=guild.id)
        if not rows:
            return "rankrole-needs-mapping"
        try:
            channel = await self._panel_channel(guild, panel.channel_id)
        except DISCORD_HTTP_ERRORS:
            return "rankrole-panel-blocked"
        if channel is None:
            return "rankrole-needs-channel"
        card, view = self._panel_parts(
            interaction, {r.tier_group: r.role_id for r in rows}
        )
        message: discord.Message | None = None
        if panel.message_id is not None:
            try:
                message = await channel.fetch_message(panel.message_id)
            except discord.NotFound:
                # The stored panel is gone; repost instead of leaving a dead link.
                message = None
            except DISCORD_HTTP_ERRORS:
                # A permission or transient failure is not proof the panel is
                # gone, so never post a second one over it.
                return "rankrole-panel-blocked"
        try:
            if message is None:
                message = await channel.send(embed=card, view=view)
                if not await self._record_panel(panel, message):
                    # Without a stored id the next publish would post a second
                    # panel, so withdraw the one just sent.
                    try:
                        await message.delete()
                    except DISCORD_HTTP_ERRORS:
                        log.warning("Could not withdraw an unrecorded panel message")
                        return "rankrole-panel-untracked"
                    return "rankrole-panel-blocked"
            else:
                await message.edit(embed=card, view=view)
        except DISCORD_HTTP_ERRORS:
            return "rankrole-panel-blocked"
        return None

    @staticmethod
    async def _record_panel(panel: RankRolePanel, message: discord.Message) -> bool:
        """Store the posted panel id, retrying once before giving up."""
        panel.message_id = message.id
        return await _retry_write(
            lambda: panel.save(update_fields=["message_id", "updated_at"]),
            "Could not record the new rank role panel",
        )

    def _panel_parts(
        self, interaction: discord.Interaction, mapped: dict[str, int]
    ) -> tuple[discord.Embed, discord.ui.View]:
        """Build the panel: every mapped rank, the role it awards, and how it works."""
        title = translated(interaction, "rankrole-panel-title")
        card = embed(
            translated(interaction, "rankrole-panel-description"),
            title=title.strip(),
        )
        ranks = []
        for group, key in TIER_ROLES:
            role_id = mapped.get(group)
            if role_id is None:
                continue
            mark = self.bot.emoji_service.rank_emoji(TIER_EMOJI_TIERS[group])
            label = self.bot.translator.text(interaction.locale, key)
            ranks.append(f"{mark} {label} → <@&{role_id}>".strip())
        card.add_field(
            name=translated(interaction, "rankrole-panel-roles-field"),
            value="\n".join(ranks),
            inline=False,
        )
        card.add_field(
            name=translated(interaction, "rankrole-panel-how-field"),
            value="\n".join(
                translated(interaction, key)
                for key in (
                    "rankrole-panel-how-add",
                    "rankrole-panel-how-swap",
                    "rankrole-panel-how-remove",
                )
            ),
            inline=False,
        )
        card.set_footer(
            text=translated(
                interaction,
                "rankrole-panel-coverage",
                mapped=len(mapped),
                total=len(TIER_GROUPS),
            )
        )
        controls = discord.ui.View(timeout=None)
        controls.add_item(
            PublicActionButton(
                "rankrole_add",
                label=translated(interaction, "rankrole-panel-add"),
                style=discord.ButtonStyle.primary,
            )
        )
        controls.add_item(
            PublicActionButton(
                "rankrole_remove",
                label=translated(interaction, "rankrole-panel-remove"),
            )
        )
        return card, controls

    async def refresh_panel(self, interaction: discord.Interaction) -> str | None:
        """Update an already posted panel in place, never creating one.

        Returns a locale key describing why the update could not happen, so a
        deleted panel is reported as stale rather than as a permission problem.
        """
        guild = interaction.guild
        if guild is None:
            return None
        try:
            panel = await RankRolePanel.get_or_none(guild_id=guild.id)
            if panel is None or panel.channel_id is None or panel.message_id is None:
                return None
            rows = await RankRole.filter(guild_id=guild.id)
        except TRANSIENT_DATABASE_ERRORS:
            log.warning("Could not read rank role settings to refresh the panel")
            return "rankrole-panel-blocked"
        if not rows:
            return None
        try:
            channel = await self._panel_channel(guild, panel.channel_id)
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not resolve the rank role panel channel")
            return "rankrole-panel-blocked"
        if channel is None:
            return "rankrole-needs-channel"
        try:
            message = await channel.fetch_message(panel.message_id)
        except discord.NotFound:
            return "rankrole-panel-stale"
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not read the rank role panel to refresh it")
            return "rankrole-panel-blocked"
        card, view = self._panel_parts(
            interaction, {row.tier_group: row.role_id for row in rows}
        )
        try:
            await message.edit(embed=card, view=view)
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not refresh the rank role panel message")
            return "rankrole-panel-blocked"
        return None

    def _throttled(self, user_id: int) -> bool:
        """Return True when the member acted within the debounce window."""
        now = time.monotonic()
        if len(self._recent) > 1024:
            self._recent = {
                key: seen
                for key, seen in self._recent.items()
                if now - seen < DEBOUNCE_SECONDS
            }
        last = self._recent.get(user_id)
        if last is not None and now - last < DEBOUNCE_SECONDS:
            return True
        self._recent[user_id] = now
        return False

    async def _mapped_roles(
        self, guild: discord.Guild
    ) -> tuple[dict[str, int], dict[int, str]]:
        """Return tier to role ids and its reverse for one guild."""
        rows = await RankRole.filter(guild_id=guild.id)
        by_tier = {row.tier_group: row.role_id for row in rows}
        by_role = {row.role_id: row.tier_group for row in rows}
        return by_tier, by_role

    async def _sync_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        target: str | None,
    ) -> str:
        """Move one member to the target tier role, returning a locale key."""
        if not guild.me.guild_permissions.manage_roles:
            return "rankrole-no-manage-roles"
        by_tier, by_role = await self._mapped_roles(guild)
        if not by_tier:
            return "rankrole-not-configured"
        wanted: discord.Role | None = None
        if target is not None:
            role_id = by_tier.get(target)
            if role_id is None:
                return "rankrole-tier-unmapped"
            wanted = guild.get_role(role_id)
            if wanted is None:
                return "rankrole-tier-unmapped"
            if wanted >= guild.me.top_role:
                return "rankrole-hierarchy"
        held = {role.id for role in member.roles}
        stale_ids, needs_add = plan_changes(
            held, by_role, wanted.id if wanted is not None else None
        )
        if not stale_ids and not needs_add:
            return "rankrole-already" if wanted is not None else "rankrole-removed"
        # One edit keeps the member's other roles intact and never leaves them
        # without a rank role if the add would have failed after the remove.
        final = [
            role
            for role in member.roles
            if role.id not in stale_ids and not role.is_default()
        ]
        if needs_add and wanted is not None:
            final.append(wanted)
        try:
            await member.edit(roles=final, reason=SYNC_REASON)
        except discord.Forbidden:
            return "rankrole-no-manage-roles"
        except DISCORD_HTTP_ERRORS:
            return "rankrole-sync-failed"
        return "rankrole-updated" if wanted is not None else "rankrole-removed"

    async def add_role(self, interaction: discord.Interaction, payload: str) -> None:
        """Give the member the role for their current rank."""
        if self._throttled(interaction.user.id):
            await _notice(interaction, "rankrole-cooldown")
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await _notice(interaction, "error-guild-only")
            return
        if not await RankRole.exists(guild_id=guild.id):
            await _notice(interaction, "rankrole-not-configured")
            return
        account = await selected_account(interaction.user.id)
        if account is None:
            await _notice(interaction, "rankrole-needs-account")
            return
        try:
            profile = await self.bot.profiles.profile(account)
        except AuthenticationRequired:
            await _notice(interaction, "error-riot-login-expired")
            return
        except ProfileUnavailable, HTTPFailure:
            await _notice(interaction, "error-riot-services-unavailable")
            return
        group = tier_group(profile.tier)
        member = interaction.user
        if not isinstance(member, discord.Member):
            await _notice(interaction, "error-guild-only")
            return
        key = await self._sync_member(guild, member, group)
        if group is None and key == "rankrole-removed":
            key = "rankrole-unranked"
        name = (
            self.bot.translator.text(interaction.locale, _tier_key(group))
            if group is not None
            else ""
        )
        await _notice(interaction, key, tier=name)

    async def remove_role(self, interaction: discord.Interaction, payload: str) -> None:
        """Strip every mapped rank role from the member."""
        if self._throttled(interaction.user.id):
            await _notice(interaction, "rankrole-cooldown")
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await _notice(interaction, "error-guild-only")
            return
        key = await self._sync_member(guild, member, None)
        await _notice(interaction, key)


class _ChannelPicker(discord.ui.ChannelSelect):
    """Choose and store the channel that hosts the member panel."""

    def __init__(
        self,
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        guild: discord.Guild,
    ) -> None:
        """Label the picker and remember the dashboard it belongs to."""
        super().__init__(
            placeholder=cog.bot.translator.text(
                dashboard.locale, "rankrole-channel-placeholder"
            ),
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Store the chosen channel, retiring the old panel first."""
        await interaction.response.defer()
        channel_id = int(self.values[0].id)
        existing = await RankRolePanel.get_or_none(guild_id=self.guild.id)
        if (
            existing is not None
            and existing.channel_id != channel_id
            and not await self.cog.retire_panel(self.dashboard, self.guild)
        ):
            await error(interaction, "rankrole-panel-blocked")
            return
        if not await _retry_write(
            lambda: RankRolePanel.update_or_create(
                guild_id=self.guild.id, defaults={"channel_id": channel_id}
            ),
            "Could not store the rank role panel channel",
        ):
            await error(interaction, "error-command-failed")
            return
        await self.cog._safe_dashboard(self.dashboard, self.guild)


class _MappingButton(discord.ui.Button[discord.ui.View]):
    """Start the two-step tier then role mapping flow."""

    def __init__(
        self, cog: RankRoleCog, dashboard: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Label the button and remember the dashboard it belongs to."""
        super().__init__(row=1)
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild
        self.label = cog.bot.translator.text(
            dashboard.locale, "rankrole-button-mapping"
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Offer a rank picker and a role picker in one step."""
        await interaction.response.defer()
        rows = await RankRole.filter(guild_id=self.guild.id)
        mapped = {row.tier_group: row.role_id for row in rows}
        await interaction.followup.send(
            content=translated(interaction, "rankrole-mapping-prompt"),
            view=_MappingView(self.cog, self.dashboard, self.guild, mapped),
            ephemeral=True,
        )


class _MappingView(discord.ui.View):
    """Pick a rank and its role together, then save both in one step."""

    def __init__(
        self,
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        guild: discord.Guild,
        mapped: dict[str, int],
    ) -> None:
        """Build the rank picker, the role picker, and the save controls."""
        super().__init__(timeout=DASHBOARD_TIMEOUT)
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild
        self.group: str | None = None
        self.role: discord.Role | None = None
        self.rank_select = _RankSelect(cog, dashboard, guild, self, mapped)
        self.role_select = _RoleSelect(cog, dashboard, self)
        self.save_button = _SaveButton(cog, dashboard, self)
        self.add_item(self.rank_select)
        self.add_item(self.role_select)
        self.add_item(self.save_button)


class _RankSelect(discord.ui.Select[discord.ui.View]):
    """Choose the rank whose role is being configured."""

    def __init__(
        self,
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        guild: discord.Guild,
        owner: _MappingView,
        mapped: dict[str, int],
    ) -> None:
        """Build one option per rank, noting the role it currently awards."""
        super().__init__(row=0)
        self.owner = owner
        self.placeholder = cog.bot.translator.text(
            dashboard.locale, "rankrole-pick-rank"
        )
        self.options = [
            discord.SelectOption(
                label=cog.bot.translator.text(dashboard.locale, key),
                value=group,
                description=self._current(cog, dashboard, guild, mapped, group),
                emoji=_select_emoji(
                    cog.bot.emoji_service.rank_emoji(TIER_EMOJI_TIERS[group])
                ),
            )
            for group, key in TIER_ROLES
        ]

    @staticmethod
    def _current(
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        guild: discord.Guild,
        mapped: dict[str, int],
        group: str,
    ) -> str:
        """Describe the role a rank currently awards, for the option subtitle."""
        role_id = mapped.get(group)
        role = guild.get_role(role_id) if role_id is not None else None
        if role is None:
            return cog.bot.translator.text(dashboard.locale, "rankrole-choice-unmapped")
        return cog.bot.translator.text(
            dashboard.locale, "rankrole-choice-current", role=role.name
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Record the chosen rank without redrawing the step."""
        await interaction.response.defer()
        self.owner.group = self.values[0]


class _RoleSelect(discord.ui.RoleSelect):
    """Choose the role that will be awarded for the chosen rank."""

    def __init__(
        self,
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        owner: _MappingView,
    ) -> None:
        """Label the picker and remember the step it belongs to."""
        super().__init__(min_values=1, max_values=1, row=1)
        self.owner = owner
        self.placeholder = cog.bot.translator.text(
            dashboard.locale, "rankrole-pick-role"
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Record the chosen role without redrawing the step."""
        await interaction.response.defer()
        role = self.values[0]
        if not isinstance(role, discord.Role):
            await error(interaction, "rankrole-role-invalid")
            return
        self.owner.role = role


class _SaveButton(discord.ui.Button[discord.ui.View]):
    """Store the chosen rank and role pair."""

    def __init__(
        self,
        cog: RankRoleCog,
        dashboard: discord.Interaction,
        owner: _MappingView,
    ) -> None:
        """Label the button and let the step validate the pair on save."""
        super().__init__(row=2, style=discord.ButtonStyle.success)
        self.cog = cog
        self.dashboard = dashboard
        self.owner = owner
        self.label = cog.bot.translator.text(dashboard.locale, "rankrole-save")

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Save the mapping, then refresh the panel and the dashboard."""
        await interaction.response.defer()
        if self.owner.group is None or self.owner.role is None:
            await error(interaction, "rankrole-pick-both")
            return
        try:
            problem = await self.cog.apply_mapping(
                self.owner.guild, self.owner.group, self.owner.role
            )
        except TRANSIENT_DATABASE_ERRORS:
            log.warning("Could not store a rank role mapping")
            await error(interaction, "rankrole-panel-blocked")
            return
        if problem is not None:
            await error(interaction, problem)
            return
        await interaction.edit_original_response(
            content=translated(
                interaction,
                "rankrole-mapping-saved",
                role=self.owner.role.mention,
            ),
            embeds=[],
            view=None,
        )
        problem = await self.cog.refresh_panel(self.dashboard)
        if problem is not None:
            await interaction.followup.send(
                content=translated(interaction, problem),
                ephemeral=True,
            )
        await self.cog._safe_dashboard(self.dashboard, self.owner.guild)


class _ResetButton(discord.ui.Button[discord.ui.View]):
    """Open the reset scope picker."""

    def __init__(
        self, cog: RankRoleCog, dashboard: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Label the button and remember the dashboard it belongs to."""
        super().__init__(row=1, style=discord.ButtonStyle.danger)
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild
        self.label = cog.bot.translator.text(dashboard.locale, "rankrole-button-reset")

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Offer the reset scopes."""
        await interaction.response.defer()
        await interaction.followup.send(
            content=translated(interaction, "rankrole-pick-reset"),
            view=_one_item(_ResetPicker(self.cog, self.dashboard, self.guild)),
            ephemeral=True,
        )


class _ResetPicker(discord.ui.Select[discord.ui.View]):
    """Pick which stored rank role data to clear."""

    def __init__(
        self, cog: RankRoleCog, dashboard: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Build the panel, all-mappings, and per-tier reset options."""
        super().__init__()
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild
        self.placeholder = cog.bot.translator.text(
            dashboard.locale, "rankrole-pick-reset"
        )
        options = [
            discord.SelectOption(
                label=cog.bot.translator.text(dashboard.locale, "rankrole-reset-panel"),
                value="panel",
            ),
            discord.SelectOption(
                label=cog.bot.translator.text(dashboard.locale, "rankrole-reset-all"),
                value="all",
            ),
        ]
        options.extend(
            discord.SelectOption(
                label=cog.bot.translator.text(dashboard.locale, key), value=group
            )
            for group, key in TIER_ROLES
        )
        self.options = options

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Apply the chosen reset scope, then confirm what actually happened."""
        await interaction.response.defer()
        problem = await self.cog.reset_all(self.dashboard, self.guild, self.values[0])
        await interaction.edit_original_response(
            content=translated(
                interaction, problem if problem is not None else "rankrole-reset-done"
            ),
            embeds=[],
            view=None,
        )


class _PublishButton(discord.ui.Button[discord.ui.View]):
    """Post or update the member-facing panel."""

    def __init__(
        self, cog: RankRoleCog, dashboard: discord.Interaction, guild: discord.Guild
    ) -> None:
        """Label the button and remember the dashboard it belongs to."""
        super().__init__(row=1, style=discord.ButtonStyle.success)
        self.cog = cog
        self.dashboard = dashboard
        self.guild = guild
        self.label = cog.bot.translator.text(
            dashboard.locale, "rankrole-button-publish"
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Publish the panel and redraw the dashboard."""
        await interaction.response.defer()
        problem = await self.cog.publish_panel(self.dashboard)
        if problem is not None:
            await _notice(interaction, problem)
            return
        await _notice(interaction, "rankrole-published")
        await self.cog._safe_dashboard(self.dashboard, self.guild)


async def setup(bot: BotFraggBot) -> None:
    """Register the rank role command and its member controls."""
    await bot.add_cog(RankRoleCog(bot))
