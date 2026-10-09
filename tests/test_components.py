"""Behavior and regression checks for components."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import discord
import pytest
from tortoise.exceptions import DBConnectionError

from src.cogs.valorant.login import LoginModal
from src.views import OwnedActionButton, OwnedSelect
from src.views.components import ACTION_RE, SELECT_RE
from src.views.ui import unexpected_error
from tests.helpers import _localized_interaction


@pytest.mark.parametrize("kind", ["button", "select", "modal"])
@pytest.mark.parametrize("deferred", [False, True])
async def test_unhandled_interaction_failure_returns_private_localized_error(
    kind, deferred, caplog
):
    interaction = _localized_interaction(
        user=SimpleNamespace(id=101),
        response=SimpleNamespace(
            is_done=Mock(return_value=False),
            send_message=AsyncMock(),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    failure = DBConnectionError("Synthetic private database detail")

    async def defer(**kwargs):
        if kind == "modal" and not deferred:
            raise failure
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=defer)

    async def handler(*args):
        if deferred:
            await interaction.response.defer()
        raise failure

    with caplog.at_level(logging.ERROR):
        if kind == "modal":
            bot = interaction.client
            bot.auth = SimpleNamespace(redeem_callback=AsyncMock(side_effect=failure))
            modal = LoginModal(bot, interaction.locale)
            try:
                await modal._scheduled_task(interaction, [], {})
            finally:
                modal.stop()
        else:
            interaction.client.component_handlers = {"action": handler}
            control = (
                OwnedActionButton("action", 101, label="Do it")
                if kind == "button"
                else OwnedSelect("action", 101, empty_option_label="Choice")
            )
            await control.callback(interaction)

    send = interaction.followup.send if deferred else interaction.response.send_message
    other = interaction.response.send_message if deferred else interaction.followup.send
    send.assert_awaited_once()
    other.assert_not_awaited()
    sent = send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert sent["embed"].description == interaction.client.translator.text(
        interaction.locale, "error-command-failed"
    )
    assert "Synthetic private database detail" not in sent["embed"].description
    assert any(
        record.exc_info and record.exc_info[1] is failure for record in caplog.records
    )


@pytest.mark.parametrize("kind", ["button", "select", "modal"])
async def test_interaction_cancellation_propagates_without_error_response(kind):
    interaction = _localized_interaction(
        user=SimpleNamespace(id=101),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    handler = AsyncMock(side_effect=asyncio.CancelledError)
    if kind == "modal":
        interaction.client.auth = SimpleNamespace(redeem_callback=handler)
        modal = LoginModal(interaction.client, interaction.locale)
        try:
            with pytest.raises(asyncio.CancelledError):
                await modal._scheduled_task(interaction, [], {})
        finally:
            modal.stop()
    else:
        interaction.client.component_handlers = {"action": handler}
        control = (
            OwnedActionButton("action", 101, label="Do it")
            if kind == "button"
            else OwnedSelect("action", 101, empty_option_label="Choice")
        )
        with pytest.raises(asyncio.CancelledError):
            await control.callback(interaction)
    handler.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize(
    "delivery_failure",
    [
        discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Blocked"),
        aiohttp.ServerDisconnectedError(),
        OSError("Synthetic disconnected transport"),
    ],
)
async def test_error_response_delivery_failure_preserves_original_exception(
    deferred, delivery_failure, caplog
):
    interaction = _localized_interaction(
        response=SimpleNamespace(
            is_done=Mock(return_value=deferred),
            send_message=AsyncMock(side_effect=delivery_failure),
        ),
        followup=SimpleNamespace(send=AsyncMock(side_effect=delivery_failure)),
    )
    original = DBConnectionError("Synthetic database outage")
    with caplog.at_level(logging.WARNING):
        try:
            raise original
        except DBConnectionError as exc:
            await unexpected_error(interaction, exc)

    send = interaction.followup.send if deferred else interaction.response.send_message
    send.assert_awaited_once()
    assert any(
        record.exc_info and record.exc_info[1] is original for record in caplog.records
    )
    assert "Could not deliver interaction error response" in caplog.text


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
