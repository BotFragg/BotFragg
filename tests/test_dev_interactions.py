"""Behavior checks for the maintenance gate and notice delivery on controls."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from src.cogs.valorant import crosshair as crosshair_cog
from src.cogs.valorant.crosshair import CrosshairView, ShareConfirmView
from src.cogs.valorant.login import LoginModal
from src.services.crosshair import CrosshairProfile
from src.views.components import OwnedActionButton, OwnedSelect, _dispatch
from src.views.notices import after_interaction
from tests.helpers import TEST_LOCALE, TEST_TRANSLATOR, _localized_bot

CODE = "0;P;c;1;h;0;0b;0;1b;0"
READ_CUSTOM_ID = "botfragg:dev_announce_read:1:7"


def _notices(*, allow: bool = True, delivery_error: Exception | None = None):
    """Build a notice service spy with fixed gate and delivery behavior."""
    return SimpleNamespace(
        allow=AsyncMock(return_value=allow),
        deliver=AsyncMock(side_effect=delivery_error),
    )


def _response(*, done: bool = False) -> SimpleNamespace:
    """Build a recording interaction response."""
    return SimpleNamespace(
        is_done=Mock(return_value=done),
        send_message=AsyncMock(),
        defer=AsyncMock(),
        edit_message=AsyncMock(),
        edit_original_response=AsyncMock(),
    )


def _interaction(
    *,
    notices: SimpleNamespace | None = None,
    user_id: int = 1,
    kind: discord.InteractionType = discord.InteractionType.component,
    data: dict[str, object] | None = None,
    response: SimpleNamespace | None = None,
    guild: object | None = None,
) -> SimpleNamespace:
    """Build a fake interaction whose client carries the notice spies."""
    return SimpleNamespace(
        client=SimpleNamespace(
            translator=TEST_TRANSLATOR, dev_notices=notices or _notices()
        ),
        locale=TEST_LOCALE,
        user=SimpleNamespace(id=user_id, display_name="Example"),
        type=kind,
        data=data or {},
        response=response or _response(),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
        guild=guild,
    )


def _profiles() -> list[CrosshairProfile]:
    """Build one non-current and one current crosshair profile."""
    return [
        CrosshairProfile(index=0, name="one", code=CODE, current=False),
        CrosshairProfile(index=1, name="two", code=CODE, current=True),
    ]


def _account() -> SimpleNamespace:
    """Build the account the crosshair controls operate on."""
    return SimpleNamespace(
        puuid="synthetic",
        user_id=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _cog(**attributes: object) -> SimpleNamespace:
    """Build a fake crosshair cog with the required collaborators."""
    return SimpleNamespace(
        bot=SimpleNamespace(crosshair=SimpleNamespace(profiles=AsyncMock())),
        **attributes,
    )


def _card() -> tuple[discord.Embed, discord.File, None]:
    """Build a rendered crosshair card with its attachment."""
    return (
        discord.Embed(title="card"),
        discord.File(
            io.BytesIO(b"\x89PNG\r\n\x1a\nsynthetic"), filename="crosshair.png"
        ),
        None,
    )


@pytest.mark.parametrize("kind", ["button", "select"])
@pytest.mark.parametrize("data", [{}, {"custom_id": READ_CUSTOM_ID}])
async def test_owned_control_check_consults_allow_before_the_owner_check(
    kind: str, data: dict[str, object]
) -> None:
    """A refused gate must skip the owner check, including for Mark read."""
    notices = _notices(allow=False)
    interaction = _interaction(notices=notices, user_id=2, data=data)
    control: OwnedActionButton | OwnedSelect = (
        OwnedActionButton("action", 1, label="Do it")
        if kind == "button"
        else OwnedSelect("action", 1, empty_option_label="Choice")
    )

    allowed = await control.interaction_check(interaction)

    assert allowed is False
    notices.allow.assert_awaited_once_with(interaction)
    interaction.response.send_message.assert_not_awaited()


async def test_dispatch_delivers_once_after_the_handler() -> None:
    """The announcement must be sent after the component handler finishes."""
    notices = _notices()
    interaction = _interaction(notices=notices)

    async def handler(_interaction: object, _payload: str) -> None:
        assert notices.deliver.await_count == 0

    handler_mock = AsyncMock(side_effect=handler)
    interaction.client.component_handlers = {"action": handler_mock}

    await _dispatch(interaction, "action", "payload", "component-button-unavailable")

    handler_mock.assert_awaited_once_with(interaction, "payload")
    notices.deliver.assert_awaited_once_with(interaction)


async def test_dispatch_still_delivers_after_a_failed_handler() -> None:
    """A failing handler must not suppress the announcement."""
    notices = _notices()
    interaction = _interaction(notices=notices)
    interaction.client.component_handlers = {
        "action": AsyncMock(side_effect=RuntimeError("Synthetic failure"))
    }

    await _dispatch(interaction, "action", "payload", "component-button-unavailable")

    notices.deliver.assert_awaited_once_with(interaction)


@pytest.mark.parametrize("surface", ["view", "share", "modal"])
async def test_views_and_modal_refuse_when_allow_is_false(surface: str) -> None:
    """Every custom interaction surface must honour the maintenance gate."""
    notices = _notices(allow=False)
    interaction = _interaction(notices=notices)
    target: object
    if surface == "view":
        target = CrosshairView(
            _cog(), interaction, _account(), _profiles(), _profiles()[1]
        )
    elif surface == "share":
        target = ShareConfirmView(_cog(), _profiles()[1], interaction)
    else:
        target = LoginModal(_localized_bot(), TEST_LOCALE)

    assert await target.interaction_check(interaction) is False
    notices.allow.assert_awaited_once_with(interaction)


@pytest.mark.parametrize("method", ["profile_selected", "refresh_profiles"])
async def test_control_handlers_deliver_once(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """Selecting or refreshing must deliver one announcement after redrawing."""
    monkeypatch.setattr(
        crosshair_cog, "account_for_user", AsyncMock(return_value=_account())
    )
    notices = _notices()
    interaction = _interaction(notices=notices)
    cog = _cog(build_card=AsyncMock(return_value=_card()))
    cog.bot.crosshair.profiles = AsyncMock(return_value=_profiles())
    view = CrosshairView(cog, interaction, _account(), _profiles(), _profiles()[0])

    if method == "profile_selected":
        await view.profile_selected(interaction, 1)
        interaction.response.edit_message.assert_awaited_once()
    else:
        await view.refresh_profiles(interaction)
        interaction.edit_original_response.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_share_preview_delivers_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening the share preview must deliver one announcement."""
    channel = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(crosshair_cog, "_share_target", lambda _: (channel, None))
    notices = _notices()
    interaction = _interaction(notices=notices)
    cog = _cog(
        render_card=AsyncMock(return_value=(discord.Embed(title="card"), b"png")),
        share_footer=Mock(return_value="footer"),
    )
    view = CrosshairView(cog, interaction, _account(), _profiles(), _profiles()[1])

    await view.share_preview(interaction)

    interaction.response.send_message.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_share_post_delivers_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirming a share must deliver one announcement after posting."""
    channel = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(crosshair_cog, "_share_target", lambda _: (channel, None))
    notices = _notices()
    interaction = _interaction(notices=notices)
    cog = _cog(
        share_cooldown_remaining=Mock(return_value=0),
        mark_shared=Mock(),
        clear_shared=Mock(),
        render_card=AsyncMock(return_value=(discord.Embed(title="card"), b"png")),
        share_footer=Mock(return_value="footer"),
    )
    confirm = ShareConfirmView(cog, _profiles()[1], interaction)

    await confirm.post.callback(interaction)

    channel.send.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_share_cancel_delivers_once() -> None:
    """Cancelling a share must deliver one announcement after dismissing."""
    notices = _notices()
    interaction = _interaction(notices=notices)
    confirm = ShareConfirmView(_cog(), _profiles()[1], interaction)

    await confirm.cancel.callback(interaction)

    interaction.response.edit_message.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_login_submit_delivers_once() -> None:
    """Submitting the login modal must deliver one announcement after replying."""
    notices = _notices()
    interaction = _interaction(notices=notices)
    modal = _login_modal()

    await modal.on_submit(interaction)

    interaction.followup.send.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_after_interaction_accepts_a_keyword_interaction() -> None:
    """The decorator must forward a keyword interaction without an index error."""
    notices = _notices()
    interaction = _interaction(notices=notices)
    seen: list[object] = []

    class View:
        @after_interaction
        async def callback(self, interaction: object, *, note: str = "") -> str:
            seen.append(interaction)
            return note

    result = await View().callback(interaction=interaction, note="done")

    assert result == "done"
    assert seen == [interaction]
    notices.deliver.assert_awaited_once_with(interaction)


async def test_delivery_failure_does_not_change_a_view_callback_result() -> None:
    """A delivery failure must not raise out of or change the control result."""
    notices = _notices(delivery_error=RuntimeError("Synthetic outage"))
    interaction = _interaction(notices=notices)
    confirm = ShareConfirmView(_cog(), _profiles()[1], interaction)

    result = await confirm.cancel.callback(interaction)

    assert result is None
    interaction.response.edit_message.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


async def test_delivery_failure_does_not_change_the_login_result() -> None:
    """A delivery failure must not raise out of the modal submission."""
    notices = _notices(delivery_error=RuntimeError("Synthetic outage"))
    interaction = _interaction(notices=notices)

    await _login_modal().on_submit(interaction)

    interaction.followup.send.assert_awaited_once()
    notices.deliver.assert_awaited_once_with(interaction)


def _login_modal() -> LoginModal:
    """Build a login modal whose auth service accepts the callback."""
    bot = _localized_bot(
        auth=SimpleNamespace(
            redeem_callback=AsyncMock(
                return_value=SimpleNamespace(
                    success=True,
                    account=SimpleNamespace(username="Example"),
                    error_key=None,
                    error_arguments={},
                )
            )
        )
    )
    return LoginModal(bot, TEST_LOCALE)
