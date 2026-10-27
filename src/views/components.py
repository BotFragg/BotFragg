"""Persistent interactive controls scoped to the Discord user who created them."""

from __future__ import annotations

import re
from typing import Any

import discord

from ..monitoring import transaction
from .ui import unexpected_error

ACTION_RE = re.compile(
    r"botfragg:(?P<action>[a-z_]+):(?P<owner>\d+):(?P<payload>[^:]*)"
)
SELECT_RE = re.compile(
    r"botfragg_select:(?P<action>[a-z_]+):(?P<owner>\d+):(?P<payload>[^:]*)"
)


async def _reject_other_owner(
    interaction: discord.Interaction[Any], owner_id: int, key: str
) -> bool:
    """Allow the recorded owner and refuse the control to everybody else."""
    if interaction.user.id == owner_id:
        return True
    await interaction.response.send_message(
        embed=_error_embed(interaction.client.translator.text(interaction.locale, key)),
        ephemeral=True,
    )
    return False


async def _dispatch(
    interaction: discord.Interaction[Any], action: str, payload: str, key: str
) -> None:
    """Run the handler registered for an owned control inside a trace."""
    handler = getattr(interaction.client, "component_handlers", {}).get(action)
    if handler is None:
        await interaction.response.send_message(
            embed=_error_embed(
                interaction.client.translator.text(interaction.locale, key)
            ),
            ephemeral=True,
        )
        return
    try:
        with transaction(f"discord.component.{action}", "discord.component"):
            await handler(interaction, payload)
    except Exception as exc:
        await unexpected_error(interaction, exc)


class OwnedActionButton(discord.ui.DynamicItem[discord.ui.Button], template=ACTION_RE):
    """Create a persistent button whose action can only be used by its owner."""

    def __init__(
        self,
        action: str,
        owner_id: int,
        payload: str = "",
        *,
        label: str | None = None,
        emoji: str | None = None,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        disabled: bool = False,
    ) -> None:
        """Build a stable custom ID containing the action, owner, and payload."""
        self.action = action
        self.owner_id = owner_id
        self.payload = payload
        super().__init__(
            discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style,
                disabled=disabled,
                custom_id=f"botfragg:{action}:{owner_id}:{payload}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Any],
        item: discord.ui.Item[Any],
        match: re.Match[str],
    ) -> OwnedActionButton:
        """Reconstruct a persistent button from its custom ID and visible style."""
        assert isinstance(item, discord.ui.Button)
        instance = cls(
            match["action"],
            int(match["owner"]),
            match["payload"],
            label=item.label,
            emoji=str(item.emoji) if item.emoji else None,
            style=item.style,
            disabled=item.disabled,
        )
        return instance

    async def interaction_check(self, interaction: discord.Interaction[Any]) -> bool:
        """Reject interactions from users other than the button's recorded owner."""
        return await _reject_other_owner(
            interaction, self.owner_id, "component-button-other-owner"
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Dispatch the button action to its registered handler inside a trace."""
        await _dispatch(
            interaction, self.action, self.payload, "component-button-unavailable"
        )


class OwnedSelect(discord.ui.DynamicItem[discord.ui.Select], template=SELECT_RE):
    """Create a persistent select menu whose action is restricted to its owner."""

    def __init__(
        self,
        action: str,
        owner_id: int,
        payload: str = "",
        *,
        placeholder: str | None = None,
        options: list[discord.SelectOption] | None = None,
        empty_option_label: str | None = None,
    ) -> None:
        """Build a stable custom ID and a translated placeholder when options are empty."""
        self.action = action
        self.owner_id = owner_id
        self.payload = payload
        select_options = options or []
        if not select_options:
            if not empty_option_label:
                raise ValueError(
                    "empty_option_label is required when options are empty"
                )
            select_options = [
                discord.SelectOption(label=empty_option_label, value="unavailable")
            ]
        super().__init__(
            discord.ui.Select(
                custom_id=f"botfragg_select:{action}:{owner_id}:{payload}",
                placeholder=placeholder,
                options=select_options,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Any],
        item: discord.ui.Item[Any],
        match: re.Match[str],
    ) -> OwnedSelect:
        """Reconstruct a persistent select menu from its ID and current options."""
        assert isinstance(item, discord.ui.Select)
        return cls(
            match["action"],
            int(match["owner"]),
            match["payload"],
            placeholder=item.placeholder,
            options=item.options,
            empty_option_label=interaction.client.translator.text(
                interaction.locale, "common-unavailable"
            ),
        )

    async def interaction_check(self, interaction: discord.Interaction[Any]) -> bool:
        """Reject interactions from users other than the menu's recorded owner."""
        return await _reject_other_owner(
            interaction, self.owner_id, "component-select-other-owner"
        )

    async def callback(self, interaction: discord.Interaction[Any]) -> None:
        """Dispatch the selected value with the menu payload to its registered handler."""
        selected = self.item.values[0] if self.item.values else ""
        await _dispatch(
            interaction,
            self.action,
            f"{self.payload}|{selected}",
            "component-select-unavailable",
        )


def _error_embed(message: str) -> discord.Embed:
    """Build a compact red embed for an invalid or unavailable component action."""
    return discord.Embed(description=message, colour=0xED4245)
