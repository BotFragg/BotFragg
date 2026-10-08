"""Behavior and regression checks for components."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from src.views import OwnedActionButton, OwnedSelect
from src.views.components import ACTION_RE, SELECT_RE
from tests.helpers import _localized_interaction


@pytest.mark.parametrize("kind", ["button", "select"])
@pytest.mark.parametrize("caller", [101, 202])
async def test_reconstructed_components_preserve_owner_and_reject_other_users(
    kind, caller
):
    interaction = _localized_interaction(
        user=SimpleNamespace(id=caller),
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    handler = AsyncMock()
    interaction.client.component_handlers = {"action": handler}
    if kind == "button":
        original = OwnedActionButton("action", 101, "payload", label="Do it")
        match = ACTION_RE.fullmatch(original.item.custom_id)
    else:
        original = OwnedSelect(
            "action",
            101,
            "payload",
            options=[discord.SelectOption(label="Choice", value="chosen")],
        )
        match = SELECT_RE.fullmatch(original.item.custom_id)
    assert match is not None
    restored = await type(original).from_custom_id(interaction, original.item, match)
    assert (restored.action, restored.owner_id, restored.payload) == (
        "action",
        101,
        "payload",
    )
    if kind == "select":
        restored.item._values = ["chosen"]

    # discord.py checks authorization before dispatching a dynamic item's callback.
    allowed = await restored.interaction_check(interaction)
    if allowed:
        await restored.callback(interaction)

    assert allowed is (caller == 101)
    if caller == 101:
        interaction.response.send_message.assert_not_awaited()
        handler.assert_awaited_once_with(
            interaction, "payload" if kind == "button" else "payload|chosen"
        )
    else:
        handler.assert_not_awaited()
        sent = interaction.response.send_message.call_args.kwargs
        assert sent["ephemeral"] is True
        assert sent["embed"].description == interaction.client.translator.text(
            interaction.locale, f"component-{kind}-other-owner"
        )


def test_dynamic_component_ids_fit_discord_limit() -> None:
    """Verify that dynamic component IDs fit Discord limit."""
    owner_id = 12345678901234567890
    assert (
        len(
            OwnedSelect(
                "alert_create",
                owner_id,
                "12345678-1234-1234-1234-123456789012",
                empty_option_label="Unavailable",
            ).item.custom_id
        )
        <= 100
    )
    assert (
        len(
            OwnedSelect(
                "shop_variant",
                owner_id,
                "4000000000|12345678-1234-1234-1234-123456789012",
                empty_option_label="Unavailable",
            ).item.custom_id
        )
        <= 100
    )


def test_alert_removal_control_fits_a_persistent_dm() -> None:
    """Verify that alert removal control fits a persistent DM."""
    button = OwnedActionButton("remove_alert", 123456789012345678, "12345678")
    assert len(button.item.custom_id) <= 100
