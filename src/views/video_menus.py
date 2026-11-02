"""Shared two-step skin-video menus used by the shop and loadout commands."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import discord

from ..localization import BotFraggTranslator
from .components import OwnedSelect, select_custom_id, selected_values
from .ui import skin_video, skin_video_options, translated, view


@dataclass(frozen=True, slots=True)
class VideoMenu:
    """Identify one command's video-menu actions and message keys."""

    action: str
    variant_action: str
    invalid_menu_key: str
    invalid_video_key: str
    missing_skin_key: str
    empty_key: str


SHOP_VIDEO_MENU = VideoMenu(
    action="shop_skin",
    variant_action="shop_variant",
    invalid_menu_key="shop-skin-selection-invalid",
    invalid_video_key="shop-video-selection-invalid",
    missing_skin_key="shop-skin-unavailable",
    empty_key="skin-no-variants",
)
LOADOUT_VIDEO_MENU = VideoMenu(
    action="loadout_video",
    variant_action="loadout_variant",
    invalid_menu_key="loadout-video-selection-invalid",
    invalid_video_key="loadout-video-selection-invalid",
    missing_skin_key="skin-video-unavailable",
    empty_key="skin-no-variants",
)


async def open_video_menu(
    interaction: discord.Interaction,
    payload: str,
    menu: VideoMenu,
    catalog: Any,
    emoji_service: Any,
    translator: BotFraggTranslator,
) -> None:
    """Open a private level/chroma video menu for one selected skin."""
    expiry, separator, skin_uuid = payload.rpartition("|")
    try:
        expires = int(expiry)
    except ValueError:
        expires = 0
    menu_id = select_custom_id(menu.action, interaction.user.id, expiry)
    if (
        not separator
        or expires <= time.time()
        or not skin_uuid
        or skin_uuid not in selected_values(interaction, menu_id)
    ):
        await interaction.response.send_message(
            translated(interaction, menu.invalid_menu_key), ephemeral=True
        )
        return
    skin = catalog.get_skin(skin_uuid)
    if skin is None:
        await interaction.response.send_message(
            translated(interaction, menu.missing_skin_key), ephemeral=True
        )
        return
    options = skin_video_options(skin, translator, interaction.locale)
    if not options:
        await interaction.response.send_message(
            translated(interaction, menu.empty_key), ephemeral=True
        )
        return
    controls = view(
        OwnedSelect(
            menu.variant_action,
            interaction.user.id,
            f"{expiry}|{skin.uuid}",
            placeholder=translated(interaction, "skin-variant-select-placeholder"),
            options=options,
            empty_option_label=translated(interaction, "common-unavailable"),
        )
    )
    skin_name = emoji_service.skin_name(
        skin.name_for(interaction.locale)
        or translator.text(interaction.locale, "common-unknown"),
        skin.tier_uuid,
    )
    await interaction.response.send_message(
        translated(interaction, "skin-variant-prompt", skin=skin_name),
        view=controls,
        ephemeral=True,
    )


async def send_video(
    interaction: discord.Interaction,
    payload: str,
    menu: VideoMenu,
    catalog: Any,
    emoji_service: Any,
    translator: BotFraggTranslator,
) -> None:
    """Privately return the selected level or chroma inspect video."""
    skin_context, separator, variant_uuid = payload.rpartition("|")
    expiry, skin_separator, skin_uuid = skin_context.partition("|")
    try:
        expires = int(expiry)
    except ValueError:
        expires = 0
    menu_id = select_custom_id(
        menu.variant_action, interaction.user.id, f"{expiry}|{skin_uuid}"
    )
    if (
        not separator
        or not skin_separator
        or expires <= time.time()
        or not skin_uuid
        or not variant_uuid
        or variant_uuid not in selected_values(interaction, menu_id)
    ):
        await interaction.response.send_message(
            translated(interaction, menu.invalid_video_key), ephemeral=True
        )
        return
    skin = catalog.get_skin(skin_uuid)
    selected = (
        skin_video(skin, variant_uuid, translator, interaction.locale)
        if skin is not None
        else None
    )
    if selected is None:
        await interaction.response.send_message(
            translated(interaction, "skin-video-unavailable"), ephemeral=True
        )
        return
    display_name, video = selected
    linked_name = emoji_service.skin_name(display_name, skin.tier_uuid)
    await interaction.response.send_message(f"[{linked_name}]({video})", ephemeral=True)
