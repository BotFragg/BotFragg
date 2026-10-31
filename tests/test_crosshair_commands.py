"""Behaviour checks for the /crosshair view command and its selector."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import discord
import pytest

from src.cogs.valorant import crosshair as crosshair_cog
from src.cogs.valorant.crosshair import (
    CrosshairCog,
    CrosshairView,
    RefreshButton,
    ShareConfirmView,
)
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
        self.original: dict[str, object] | None = None
        self.sent: dict[str, object] | None = None

    async def send_message(self, **kwargs: object) -> None:
        """Record a direct message response."""
        self.sent = kwargs

    async def defer(self, *, thinking: bool = False, ephemeral: bool = False) -> None:
        """Record how the interaction was deferred."""
        self.deferred = (thinking, ephemeral)

    @staticmethod
    def is_done() -> bool:
        """Report that the interaction already responded."""
        return True

    async def edit_message(self, **kwargs: object) -> None:
        """Record the edited message payload."""
        self.edited = kwargs

    async def edit_original_response(self, **kwargs: object) -> None:
        """Record the edited original message payload."""
        self.original = kwargs


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


async def test_refresh_refetches_and_keeps_the_selected_profile(monkeypatch):
    """The refresh control must bypass the cache and redraw the same message."""
    current = account()
    monkeypatch.setattr(
        crosshair_cog, "account_for_user", AsyncMock(return_value=current)
    )
    bot, service = build_bot()
    service.profiles = AsyncMock(
        return_value=[
            CrosshairProfile(index=0, name="one", code=CODE, current=False),
            CrosshairProfile(index=1, name="two", code=CODE, current=True),
        ]
    )
    response = Response()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=response,
        followup=Followup(),
        locale=TEST_LOCALE,
        edit_original_response=response.edit_original_response,
    )
    view = CrosshairView(
        CrosshairCog(bot), interaction, current, profiles(), profiles()[0]
    )
    button = next(item for item in view.children if isinstance(item, RefreshButton))

    await button.callback(interaction)

    assert service.profiles.await_args.kwargs == {"refresh": True}
    assert response.deferred == (False, False)
    assert response.original["embed"].title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-title", name="one"
    )
    assert response.original["attachments"][0].filename == "crosshair.png"
    refreshed = response.original["view"]
    assert isinstance(refreshed, CrosshairView)
    assert refreshed.children[0].options[0].default is True


@pytest.mark.parametrize(
    ("lookup", "key"),
    [
        (None, "error-not-registered"),
        (AuthenticationRequired("expired"), "error-riot-login-expired"),
        (CrosshairUnavailable("unavailable"), "crosshair-unavailable"),
    ],
)
async def test_refresh_reports_lookup_and_fetch_failures(monkeypatch, lookup, key):
    """A relinked account or a failed refetch must keep the old message intact."""
    current = None if lookup is None else account()
    monkeypatch.setattr(
        crosshair_cog, "account_for_user", AsyncMock(return_value=current)
    )
    bot, service = build_bot()
    if isinstance(lookup, Exception):
        service.profiles = AsyncMock(side_effect=lookup)
    response = Response()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1),
        response=response,
        followup=followup,
        locale=TEST_LOCALE,
    )
    view = CrosshairView(
        CrosshairCog(bot), interaction, account(), profiles(), profiles()[1]
    )
    button = next(item for item in view.children if isinstance(item, RefreshButton))

    await button.callback(interaction)

    assert response.original is None
    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, key
    )


async def test_refresh_rejects_a_foreign_user():
    """Another user must not refetch or redraw the owner's message."""
    cog = make_cog()
    view = CrosshairView(cog, guild_interaction(), account(), profiles(), profiles()[1])
    button = next(item for item in view.children if isinstance(item, RefreshButton))
    followup = Followup()

    await button.callback(guild_interaction(user_id=2, followup=followup))

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-command-failed"
    )
    assert cog.bot.crosshair.profiles.await_count == 0


class Channel(discord.abc.Messageable):
    """Capture public sends and return configurable permissions."""

    def __init__(self, *, allowed: bool = True) -> None:
        """Start with no sent messages and the requested permission state."""
        self.allowed = allowed
        self.send = AsyncMock()

    async def _get_channel(self):
        """Return this object so the abstract Messageable contract is satisfied."""
        return self

    def permissions_for(self, _member: object) -> SimpleNamespace:
        """Return the three permissions the share flow needs."""
        return SimpleNamespace(
            send_messages=self.allowed,
            embed_links=self.allowed,
            attach_files=self.allowed,
        )


def guild_interaction(
    *,
    channel: Channel | None = None,
    response: Response | None = None,
    followup: Followup | None = None,
    user_id: int = 1,
    locale: discord.Locale = TEST_LOCALE,
) -> SimpleNamespace:
    """Build a guild interaction with the fields the share flow uses."""
    return _localized_interaction(
        user=SimpleNamespace(id=user_id, display_name="Example"),
        response=response or Response(),
        followup=followup or Followup(),
        guild=SimpleNamespace(me=SimpleNamespace(id=1)),
        channel=channel or Channel(),
        locale=locale,
    )


def make_cog() -> CrosshairCog:
    """Build a crosshair cog with the fake rendering service."""
    bot, _service = build_bot()
    return CrosshairCog(bot)


def test_share_button_appears_only_in_a_guild():
    """The public share control must not exist in DMs."""
    cog = make_cog()
    guild_view = CrosshairView(
        cog, guild_interaction(), account(), profiles(), profiles()[1]
    )
    dm_view = CrosshairView(
        cog,
        _localized_interaction(user=SimpleNamespace(id=1)),
        account(),
        profiles(),
        profiles()[1],
    )

    assert [
        item.label
        for item in guild_view.children
        if isinstance(item, discord.ui.Button)
    ] == ["Share", "Refresh"]
    assert [
        item.label for item in dm_view.children if isinstance(item, discord.ui.Button)
    ] == ["Refresh"]


async def test_share_button_shows_the_card_that_will_be_posted():
    """The preview must show the same profile, code, image, and footer."""
    cog = make_cog()
    response = Response()
    interaction = guild_interaction(response=response)
    view = CrosshairView(cog, interaction, account(), profiles(), profiles()[1])
    button = next(item for item in view.children if isinstance(item, discord.ui.Button))

    await button.callback(interaction)

    assert response.sent is not None
    assert response.sent["ephemeral"] is True
    assert response.sent["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-preview-description"
    )
    card = response.sent["embed"]
    assert card.title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-title", name="two"
    )
    assert CODE in card.description
    assert card.footer.text == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-public-footer", user="Example"
    )
    assert response.sent["file"].filename == "crosshair.png"
    assert isinstance(response.sent["view"], ShareConfirmView)


async def test_share_post_sends_the_public_card_and_starts_cooldown(monkeypatch):
    """Posting must send one public message and block immediate repeats."""
    clock = [1000.0]
    monkeypatch.setattr(crosshair_cog, "monotonic", lambda: clock[0])
    cog = make_cog()
    channel = Channel()
    preview_response = Response()
    interaction = guild_interaction(channel=channel, response=preview_response)
    view = CrosshairView(cog, interaction, account(), profiles(), profiles()[1])
    await view.share_preview(interaction)
    confirm = preview_response.sent["view"]

    post_response = Response()
    post_interaction = guild_interaction(channel=channel, response=post_response)
    await confirm.post.callback(post_interaction)

    assert channel.send.await_count == 1
    sent = channel.send.await_args.kwargs
    assert sent["file"].filename == "crosshair.png"
    assert sent["embed"].footer.text == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-public-footer", user="Example"
    )
    assert sent["allowed_mentions"].everyone is False
    assert post_response.edited["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-success"
    )
    assert post_response.edited["view"] is None

    second_followup = Followup()
    second_interaction = guild_interaction(
        channel=channel, response=Response(), followup=second_followup
    )
    await confirm.post.callback(second_interaction)

    assert channel.send.await_count == 1
    assert second_followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-cooldown", seconds=30
    )


async def test_share_reserves_the_cooldown_before_posting(monkeypatch):
    """A second click must be blocked while the first post is still in flight."""
    clock = [1000.0]
    monkeypatch.setattr(crosshair_cog, "monotonic", lambda: clock[0])
    cog = make_cog()
    channel = Channel()
    observed: list[int] = []

    async def send(**_kwargs: object) -> None:
        """Record the cooldown visible from inside the public send."""
        observed.append(cog.share_cooldown_remaining(1))

    channel.send.side_effect = send
    interaction = guild_interaction(channel=channel)
    confirm = ShareConfirmView(cog, profiles()[1], interaction)

    await confirm.post.callback(interaction)

    assert observed == [30]


async def test_share_failure_releases_the_cooldown(monkeypatch):
    """A failed post must not cost the user the next attempt."""
    clock = [1000.0]
    monkeypatch.setattr(crosshair_cog, "monotonic", lambda: clock[0])
    cog = make_cog()
    channel = Channel()
    channel.send.side_effect = aiohttp.ClientError("Synthetic outage")
    confirm = ShareConfirmView(cog, profiles()[1], guild_interaction(channel=channel))
    followup = Followup()

    await confirm.post.callback(guild_interaction(channel=channel, followup=followup))

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-failed"
    )
    assert cog.share_cooldown_remaining(1) == 0


async def test_share_reports_a_missing_channel_permission():
    """A channel that cannot accept image embeds must be rejected early."""
    cog = make_cog()
    followup = Followup()
    interaction = guild_interaction(channel=Channel(allowed=False), followup=followup)
    view = CrosshairView(cog, interaction, account(), profiles(), profiles()[1])

    await view.share_preview(interaction)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-no-permission"
    )


async def test_share_rejects_a_direct_message():
    """There is no public channel to share into from a DM."""
    cog = make_cog()
    followup = Followup()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=1, display_name="Example"),
        response=Response(),
        followup=followup,
    )
    view = CrosshairView(cog, interaction, account(), profiles(), profiles()[1])

    await view.share_preview(interaction)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-guild-only"
    )


async def test_share_cancel_dismisses_the_preview():
    """Cancelling must remove the preview without posting."""
    cog = make_cog()
    response = Response()
    interaction = guild_interaction(response=response)
    confirm = ShareConfirmView(cog, profiles()[1], interaction)

    await confirm.cancel.callback(interaction)

    assert response.edited["content"] == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-share-cancelled"
    )
    assert response.edited["view"] is None


async def test_public_share_card_is_english_in_a_foreign_locale():
    """Public cards must stay readable when the sharer uses another language."""
    cog = make_cog()
    response = Response()
    interaction = guild_interaction(response=response, locale=discord.Locale.german)
    view = CrosshairView(cog, interaction, account(), profiles(), profiles()[1])

    await view.share_preview(interaction)

    card = response.sent["embed"]
    assert card.title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-title", name="two"
    )
    assert card.footer.text == TEST_TRANSLATOR.text(
        TEST_LOCALE, "crosshair-public-footer", user="Example"
    )
    assert response.sent["content"] == TEST_TRANSLATOR.text(
        discord.Locale.german, "crosshair-share-preview-description"
    )
    confirm = response.sent["view"]
    assert confirm.post.label == TEST_TRANSLATOR.text(
        discord.Locale.german, "crosshair-share-post"
    )
