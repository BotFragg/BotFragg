"""Tests for alert-page ordering, wrapping, and concurrent deletion."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import discord
import pytest

from src.cogs.valorant.alerts import AlertsCog
from src.localization import BotFraggTranslator
from src.models import Account, Alert, User
from src.services.catalog import Skin
from src.views.components import ACTION_RE
from tests.helpers import TEST_LOCALE, TEST_TRANSLATOR, _localized_interaction


@pytest.mark.usefixtures("database")
async def test_alert_manager_preserves_order_and_page_wrapping() -> None:
    """Verify that alert manager preserves order and page wrapping."""
    user = await User.create(id=123)
    account = await Account.create(puuid="alerts", user=user, username="One#NA")
    skin_uuids = [UUID(int=index) for index in range(1, 6)]
    skins = {
        str(skin_uuid): Skin(
            str(skin_uuid), str(skin_uuid), f"Skin {index}", None, None
        )
        for index, skin_uuid in enumerate(skin_uuids, start=1)
    }
    for skin_uuid in skin_uuids:
        await Alert.create(account=account, skin_uuid=skin_uuid)

    bot = SimpleNamespace(
        config=SimpleNamespace(alerts_per_page=2),
        catalog=SimpleNamespace(get_skin=skins.get),
        translator=BotFraggTranslator(),
        emoji_service=SimpleNamespace(
            skin_name=lambda name, _tier_uuid: name,
            skin_emoji=lambda _tier_uuid: "",
        ),
        register_component=lambda *_args: None,
    )
    cog = AlertsCog(bot)

    page, controls = await cog.manager_view(user.id, 1, discord.Locale.american_english)
    assert page.description == "**3.** **Skin 3**\n**4.** **Skin 4**"
    assert controls is not None
    assert [
        button.payload for button in controls.children if button.action == "alert_page"
    ] == [
        "prev,3",
        "next,4",
    ]

    wrapped_back, _ = await cog.manager_view(
        user.id, -1, discord.Locale.american_english
    )
    wrapped_forward, _ = await cog.manager_view(
        user.id, 3, discord.Locale.american_english
    )
    assert wrapped_back.description == "**5.** **Skin 5**"
    assert wrapped_forward.description == "**1.** **Skin 1**\n**2.** **Skin 2**"

    bot.config.alerts_per_page = 5
    single_page, single_controls = await cog.manager_view(
        user.id, 0, discord.Locale.american_english
    )
    assert single_page.description == "\n".join(
        f"**{index}.** **Skin {index}**" for index in range(1, 6)
    )
    assert single_controls is not None
    assert len(single_controls.children) == 5

    empty_user = await User.create(id=456)
    empty_page, empty_controls = await cog.manager_view(
        empty_user.id, 0, discord.Locale.american_english
    )
    assert empty_page.description == "You have no active alerts."
    assert empty_controls is None


async def test_alert_manager_handles_deletion_between_count_and_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that alert manager handles deletion between count and fetch."""

    class Query:
        """Capture query filters and pagination bounds, including rows removed between count and fetch."""

        def __init__(self) -> None:
            """Seed a stale count before the page fetch returns no remaining rows."""
            self.counts = iter((1, 0))

        def order_by(self, *_args: object) -> Query:
            """Record the requested ordering and return this query stub."""
            return self

        async def count(self) -> int:
            """Return the number of rows represented by this query stub."""
            return next(self.counts)

        def offset(self, _offset: int) -> Query:
            """Set the query offset and return this query stub."""
            return self

        def limit(self, _limit: int) -> Query:
            """Set the query limit and return this query stub."""
            return self

        def __await__(self):
            """Make the query stub awaitable and yield its configured rows."""

            async def fetch() -> list[object]:
                """Return the configured result from the fake query or HTTP client."""
                return []

            return fetch().__await__()

    monkeypatch.setattr(Alert, "filter", lambda **_filters: Query())
    bot = SimpleNamespace(
        config=SimpleNamespace(alerts_per_page=10),
        catalog=SimpleNamespace(get_skin=lambda _uuid: None),
        translator=BotFraggTranslator(),
        register_component=lambda *_args: None,
    )

    card, controls = await AlertsCog(bot).manager_view(
        123, 0, discord.Locale.american_english
    )

    assert card.description == "You have no active alerts."
    assert controls is None


@pytest.mark.usefixtures("database")
async def test_alert_page_anchor_does_not_skip_after_an_earlier_alert_is_removed():
    """An alert removed from an earlier page must not shift the next page."""
    user = await User.create(id=321)
    account = await Account.create(puuid="anchors", user=user, username="One#NA")
    alerts = [
        await Alert.create(account=account, skin_uuid=UUID(int=index))
        for index in range(1, 22)
    ]
    skins = {
        str(alert.skin_uuid): Skin(
            str(alert.skin_uuid), "offer", f"Skin {number}", None, None
        )
        for number, alert in enumerate(alerts, start=1)
    }
    bot = SimpleNamespace(
        config=SimpleNamespace(alerts_per_page=10),
        catalog=SimpleNamespace(get_skin=skins.get),
        translator=BotFraggTranslator(),
        emoji_service=SimpleNamespace(
            skin_name=lambda name, _tier_uuid: name,
            skin_emoji=lambda _tier_uuid: "",
        ),
        register_component=lambda *_args: None,
    )
    cog = AlertsCog(bot)

    _, controls = await cog.manager_view(user.id, 0, discord.Locale.american_english)
    next_payload = next(
        button.payload
        for button in controls.children
        if button.action == "alert_page" and button.payload.startswith("next,")
    )
    await alerts[0].delete()

    card, _ = await cog.manager_view(
        user.id,
        0,
        discord.Locale.american_english,
        anchor_id=int(next_payload.partition(",")[2]),
        forward=True,
    )

    assert "**10.** **Skin 11**" in card.description
    assert "**11.** **Skin 12**" in card.description
    assert "**1.** **Skin 2**" not in card.description


async def _alert_cog_with_alerts(count: int) -> tuple[AlertsCog, User, list[Alert]]:
    """Create alerts 1..count with one catalog skin each and return the cog."""
    user = await User.create(id=654)
    account = await Account.create(puuid="paging", user=user, username="One#NA")
    alerts = [
        await Alert.create(account=account, skin_uuid=UUID(int=index))
        for index in range(1, count + 1)
    ]
    skins = {
        str(alert.skin_uuid): Skin(
            str(alert.skin_uuid), "offer", f"Skin {number}", None, None
        )
        for number, alert in enumerate(alerts, start=1)
    }
    bot = SimpleNamespace(
        config=SimpleNamespace(alerts_per_page=10),
        catalog=SimpleNamespace(get_skin=skins.get),
        translator=BotFraggTranslator(),
        emoji_service=SimpleNamespace(
            skin_name=lambda name, _tier_uuid: name,
            skin_emoji=lambda _tier_uuid: "",
        ),
        register_component=lambda *_args: None,
    )
    return AlertsCog(bot), user, alerts


@pytest.mark.usefixtures("database")
async def test_alert_page_handler_pages_by_anchor_and_accepts_legacy_payloads():
    """The button handler must page by alert ID and still accept old page indexes."""
    cog, user, _ = await _alert_cog_with_alerts(21)
    edit = AsyncMock()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=user.id),
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=edit,
    )

    await cog.alert_page(interaction, "next,10")
    rendered = edit.await_args.kwargs["embed"].description
    assert "**11.** **Skin 11**" in rendered
    assert "**20.** **Skin 20**" in rendered

    await cog.alert_page(interaction, "2")
    assert "**21.** **Skin 21**" in edit.await_args.kwargs["embed"].description

    await cog.alert_page(interaction, "bogus")
    assert interaction.followup.send.await_args.kwargs[
        "embed"
    ].description == TEST_TRANSLATOR.text(TEST_LOCALE, "alert-page-invalid")


@pytest.mark.usefixtures("database")
async def test_alert_remove_refresh_keeps_the_anchored_window():
    """Removing an alert must re-render the same window, not a shifted page."""
    cog, user, alerts = await _alert_cog_with_alerts(25)
    await alerts[0].delete()
    _, controls = await cog.manager_view(
        user.id, 0, discord.Locale.american_english, anchor_id=10, forward=True
    )
    remove = next(
        button
        for button in controls.children
        if button.action == "remove_alert" and button.payload.startswith("15,anchor_")
    )
    edit = AsyncMock()
    interaction = _localized_interaction(
        user=SimpleNamespace(id=user.id),
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=edit,
    )

    await cog.remove_alert(interaction, remove.payload)

    rendered = edit.await_args.kwargs["embed"].description
    assert "**10.** **Skin 11**" in rendered
    assert "**11.** **Skin 12**" in rendered
    assert "Skin 15" not in rendered


@pytest.mark.usefixtures("database")
async def test_manager_buttons_are_dispatchable_custom_ids():
    """Every persistent button must match the full custom-ID pattern Discord uses."""
    cog, user, _ = await _alert_cog_with_alerts(21)

    _, controls = await cog.manager_view(user.id, 0, discord.Locale.american_english)

    assert controls is not None
    for button in controls.children:
        assert ACTION_RE.fullmatch(button.item.custom_id) is not None, (
            f"Discord would not dispatch {button.item.custom_id}"
        )
