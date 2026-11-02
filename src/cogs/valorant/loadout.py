"""Commands for viewing a linked account's equipped VALORANT loadout."""

from __future__ import annotations

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

from ...bot import BotFraggBot
from ...services.accounts import selected_account
from ...services.auth import AuthenticationRequired
from ...services.catalog import (
    BUDDY_ITEM_TYPE_ID,
    PLAYER_CARD_ITEM_TYPE_ID,
    PLAYER_TITLE_ITEM_TYPE_ID,
)
from ...services.profile import ProfileUnavailable
from ...views import OwnedSelect
from ...views.ui import (
    accessory,
    account_viewer,
    embed,
    error,
    skin_video_options,
    translated,
    view,
)
from ...views.video_menus import LOADOUT_VIDEO_MENU, open_video_menu, send_video

VIDEO_MENU_SECONDS = 900
# Groups follow the in-game loadout screen; VALORANT-API supplies the category.
CATEGORY_GROUPS = {
    "Pistols": "loadout-group-sidearms",
    "SMGs": "loadout-group-smgs-shotguns",
    "Shotguns": "loadout-group-smgs-shotguns",
    "Rifles": "loadout-group-rifles",
    "Sniper Rifles": "loadout-group-snipers-heavy",
    "Heavy Weapons": "loadout-group-snipers-heavy",
    "Melee": "loadout-group-melee",
}
GROUP_ORDER = (
    "loadout-group-sidearms",
    "loadout-group-smgs-shotguns",
    "loadout-group-rifles",
    "loadout-group-snipers-heavy",
    "loadout-group-melee",
    "loadout-group-other",
)


class LoadoutCog(commands.Cog):
    """Display the caller's equipped skins, variants, and gun buddies."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind the bot and register the inspect-video selects."""
        self.bot = bot
        bot.register_component(LOADOUT_VIDEO_MENU.action, self.loadout_video)
        bot.register_component(LOADOUT_VIDEO_MENU.variant_action, self.loadout_variant)

    @app_commands.command(
        name=app_commands.locale_str("loadout", key="command-loadout-name"),
        description=app_commands.locale_str(
            "View your equipped VALORANT skins",
            key="command-loadout-description",
        ),
    )
    async def loadout(self, interaction: discord.Interaction) -> None:
        """Show the caller's equipped themed skins."""
        await interaction.response.defer(thinking=True)
        account = await selected_account(interaction.user.id)
        if not account:
            await error(interaction, "error-not-registered")
            return
        viewer = await account_viewer(interaction, account, self.bot.translator)
        if viewer is None:
            return
        account, _, username = viewer
        try:
            data = await self.bot.profiles.profile(account)
        except (AuthenticationRequired, ProfileUnavailable) as exc:
            await error(interaction, exc)
            return
        card_art, title = await asyncio.gather(
            accessory(self.bot.catalog, PLAYER_CARD_ITEM_TYPE_ID, data.card_id),
            accessory(self.bot.catalog, PLAYER_TITLE_ITEM_TYPE_ID, data.title_id),
        )
        buddies = await asyncio.gather(
            *(
                accessory(self.bot.catalog, BUDDY_ITEM_TYPE_ID, gun.charm_id)
                for gun in data.guns
            )
        )
        buddy_names = {
            gun.charm_id: buddy.name_for(interaction.locale)
            for gun, buddy in zip(data.guns, buddies, strict=True)
            if gun.charm_id and buddy is not None
        }
        lines: dict[str, list[str]] = {}
        video_options: list[discord.SelectOption] = []
        offered: set[str] = set()
        for gun in data.guns:
            weapon = self.bot.catalog.get_weapon(gun.weapon_id)
            skin = self.bot.catalog.get_skin(gun.skin_id)
            if (
                weapon is None
                or skin is None
                or not skin.name_for(interaction.locale)
                or gun.skin_id == weapon.default_skin_uuid
            ):
                continue
            group = CATEGORY_GROUPS.get(weapon.category or "", "loadout-group-other")
            emoji = self.bot.emoji_service.skin_emoji(skin.tier_uuid)
            name = skin.name_for(interaction.locale)
            line = f"{emoji} **{name}**".strip()
            if label := skin.chroma_label(gun.chroma_id, interaction.locale):
                line += f" *({label})*"
            if buddy := buddy_names.get(gun.charm_id or ""):
                line += f" · `{buddy}`"
            lines.setdefault(group, []).append(line)
            if (
                skin.uuid not in offered
                and len(video_options) < 25
                and skin_video_options(skin, self.bot.translator, interaction.locale)
            ):
                offered.add(skin.uuid)
                video_options.append(
                    discord.SelectOption(label=name[:100], value=skin.uuid)
                )
        card = embed()
        description = [f"**{username}**"]
        if title is not None and (
            title_text := title.title_text_for(interaction.locale)
        ):
            description.append(f"-# {title_text}")
        if not lines:
            description.extend(("", f"-# {translated(interaction, 'loadout-empty')}"))
        card.description = "\n".join(description)
        for group in GROUP_ORDER:
            if group in lines:
                card.add_field(
                    name=translated(interaction, group),
                    value="\n".join(lines[group]),
                    inline=False,
                )
        if card_art is not None and (card_art.small_icon or card_art.icon):
            card.set_thumbnail(url=card_art.small_icon or card_art.icon)
        controls = None
        if video_options:
            controls = view(
                OwnedSelect(
                    LOADOUT_VIDEO_MENU.action,
                    interaction.user.id,
                    str(int(time.time()) + VIDEO_MENU_SECONDS),
                    placeholder=translated(interaction, "loadout-video-placeholder"),
                    options=video_options,
                    empty_option_label=translated(interaction, "common-unavailable"),
                )
            )
        if controls is None:
            await interaction.followup.send(embed=card)
        else:
            await interaction.followup.send(embed=card, view=controls)

    async def loadout_video(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Open a private level and chroma menu for one equipped skin."""
        await open_video_menu(
            interaction,
            payload,
            LOADOUT_VIDEO_MENU,
            self.bot.catalog,
            self.bot.emoji_service,
            self.bot.translator,
        )

    async def loadout_variant(
        self, interaction: discord.Interaction, payload: str
    ) -> None:
        """Privately return the selected level or chroma inspect video."""
        await send_video(
            interaction,
            payload,
            LOADOUT_VIDEO_MENU,
            self.bot.catalog,
            self.bot.emoji_service,
            self.bot.translator,
        )


async def setup(bot: BotFraggBot) -> None:
    """Register the loadout command."""
    await bot.add_cog(LoadoutCog(bot))
