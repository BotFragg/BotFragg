"""Behaviour checks for the /crosshair view command and its selector."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.cogs.valorant import crosshair as crosshair_cog
from src.cogs.valorant.crosshair import CrosshairCog, CrosshairView
from src.services.auth import AuthenticationRequired
from src.services.crosshair import CrosshairProfile, CrosshairUnavailable
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)

CODE = "0;P;c;1;h;0;0b;0;1b;0"
PNG = b"\x89PNG\r\n\x1a\nsynthetic"


def profiles() -> list[CrosshairProfile]:
    """Build one non-current and one current profile."""
    return [
        CrosshairProfile(index=0, name="one", code=CODE, current=False),
        CrosshairProfile(index=1, name="two", code=CODE, current=True),
    ]


def account() -> SimpleNamespace:
    """Build the account used by the command and selector."""
    return SimpleNamespace(
        puuid="synthetic",
        user_id=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class Response:
    """Record deferrals and component edits."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.deferred: tuple[bool, bool] | None = None
        self.edited: dict[str, object] | None = None

    async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
        """Record how the interaction was deferred."""
        self.deferred = (thinking, ephemeral)

    @staticmethod
    def is_done() -> bool:
        """Report that the interaction already responded."""
        return True

    async def edit_message(self, **kwargs: object) -> None:
        """Record the edited message payload."""
        self.edited = kwargs


class Followup:
    """Record follow-up messages."""

    def __init__(self) -> None:
        """Start with no recorded messages."""
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record one sent message."""
        self.sent.append(kwargs)


def build_bot(service_profiles: list[CrosshairProfile] | None = None):
    """Build a localized bot with a fake crosshair service."""
    service = SimpleNamespace(
        profiles=AsyncMock(return_value=service_profiles or profiles()),
        render_png=lambda _profile: PNG,
    )
    return _localized_bot(crosshair=service), service


async def test_view_shows_the_current_profile_code_and_selector(monkeypatch):
    """The default response must show the current profile, code, and image."""
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=account())
    )
    bot, _service = build_bot()
    response = Response()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=response,
        followup=followup,
        locale=TEST_LOCALE,
    )

    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)

    assert response.deferred == (True, True)
    assert len(followup.sent) == 1
    sent = followup.sent[0]
    assert sent["ephemeral"] is True
    assert sent["embed"].title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-title", name="two"
    )
    assert CODE in sent["embed"].description
    assert sent["file"].filename == "crosshair.png"
    select = sent["view"].children[0]
    assert [option.value for option in select.options] == ["0", "1"]
    assert [option.default for option in select.options] == [False, True]


async def test_selecting_a_profile_edits_the_message(monkeypatch):
    """Selecting another profile must re-render without refetching from Riot."""
    current = account()
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=current)
    )
    monkeypatch.setattr(
        crosshair_cog, "account_for_user", AsyncMock(return_value=current)
    )
    bot, service = build_bot()
    response = Response()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=response,
        followup=followup,
        locale=TEST_LOCALE,
    )
    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)
    select = followup.sent[0]["view"].children[0]
    select._values = ["0"]

    edit_response = Response()
    select_interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=edit_response,
        followup=Followup(),
        locale=TEST_LOCALE,
    )
    await select.callback(select_interaction)

    assert edit_response.edited is not None
    assert edit_response.edited["embed"].title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-title", name="one"
    )
    assert service.profiles.await_count == 1


async def test_selector_rejects_a_foreign_user(monkeypatch):
    """A component click from another user must not render the owner's code."""
    current = account()
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=current)
    )
    monkeypatch.setattr(
        crosshair_cog, "account_for_user", AsyncMock(return_value=current)
    )
    bot, _service = build_bot()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup,
        locale=TEST_LOCALE,
    )
    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)
    select = followup.sent[0]["view"].children[0]
    select._values = ["0"]

    other_followup = Followup()
    select_interaction = _localized_interaction(
        user=SimpleNamespace(id=2),
        response=Response(),
        followup=other_followup,
        locale=TEST_LOCALE,
    )
    await select.callback(select_interaction)

    assert other_followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-command-failed"
    )


async def test_selector_rejects_a_relinked_account(monkeypatch):
    """A stale puuid must not render settings after deletion or relinking."""
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=account())
    )
    monkeypatch.setattr(crosshair_cog, "account_for_user", AsyncMock(return_value=None))
    bot, _service = build_bot()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup,
        locale=TEST_LOCALE,
    )
    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)
    select = followup.sent[0]["view"].children[0]
    select._values = ["0"]

    edit_response = Response()
    select_interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=edit_response,
        followup=Followup(),
        locale=TEST_LOCALE,
    )
    await select.callback(select_interaction)

    assert edit_response.edited is None


async def test_view_reports_not_registered(monkeypatch):
    """An unlinked caller must get the existing not-registered error."""
    monkeypatch.setattr(crosshair_cog, "selected_account", AsyncMock(return_value=None))
    bot, _service = build_bot()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup,
        locale=TEST_LOCALE,
    )

    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-not-registered"
    )


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (AuthenticationRequired("expired"), "error-riot-login-expired"),
        (CrosshairUnavailable("unavailable"), "crosshair-unavailable"),
    ],
)
async def test_view_maps_service_errors(monkeypatch, error, key):
    """Authentication and decode failures must use the right private message."""
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=account())
    )
    bot, service = build_bot()
    service.profiles = AsyncMock(side_effect=error)
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup,
        locale=TEST_LOCALE,
    )

    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, key
    )


async def test_view_reports_a_render_failure(monkeypatch):
    """A profile that cannot be drawn must not produce a broken message."""
    monkeypatch.setattr(
        crosshair_cog, "selected_account", AsyncMock(return_value=account())
    )
    bot, service = build_bot()
    service.render_png = lambda _profile: (_ for _ in ()).throw(ValueError("bad"))
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup,
        locale=TEST_LOCALE,
    )

    await CrosshairCog.crosshair_view.callback(CrosshairCog(bot), interaction)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-unavailable"
    )


def test_view_keeps_the_current_profile_when_profiles_exceed_the_menu_limit():
    """The current profile must stay selectable when the menu is capped."""
    profiles_list = [
        CrosshairProfile(index=index, name=f"p{index}", code=CODE, current=index == 30)
        for index in range(40)
    ]
    interaction = _localized_interaction(user=SimpleNamespace(id=1))
    view = CrosshairView(
        CrosshairCog(_localized_bot()),
        interaction,
        account(),
        profiles_list,
        profiles_list[30],
    )

    assert len(view.children[0].options) == 25
    assert view.children[0].options[0].value == "30"
