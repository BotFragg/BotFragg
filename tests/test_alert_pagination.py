"""Tests for alert-page ordering, wrapping, and concurrent deletion."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from src.cogs.valorant.alerts import AlertsCog
from src.models import Account, Alert, User


@pytest.mark.usefixtures("database")
async def test_alert_manager_preserves_order_and_page_wrapping() -> None:
    """Verify that alert manager preserves order and page wrapping."""
    user = await User.create(id=123)
    account = await Account.create(puuid="alerts", user=user, username="One#NA")
    skin_uuids = [UUID(int=index) for index in range(1, 6)]
    skins = {
        str(skin_uuid): SimpleNamespace(name=f"Skin {index}", icon=None)
        for index, skin_uuid in enumerate(skin_uuids, start=1)
    }
    for skin_uuid in skin_uuids:
        await Alert.create(account=account, skin_uuid=skin_uuid)

    bot = SimpleNamespace(
        config=SimpleNamespace(alerts_per_page=2),
        catalog=SimpleNamespace(get_skin=skins.get),
        register_component=lambda *_args: None,
    )
    cog = AlertsCog(bot)

    page, controls = await cog.manager_view(user.id, 1)
    assert page.description == "**3.** **Skin 3**\n**4.** **Skin 4**"
    assert controls is not None
    assert [
        button.payload for button in controls.children if button.action == "alert_page"
    ] == [
        "0",
        "2",
    ]

    wrapped_back, _ = await cog.manager_view(user.id, -1)
    wrapped_forward, _ = await cog.manager_view(user.id, 3)
    assert wrapped_back.description == "**5.** **Skin 5**"
    assert wrapped_forward.description == "**1.** **Skin 1**\n**2.** **Skin 2**"

    bot.config.alerts_per_page = 5
    single_page, single_controls = await cog.manager_view(user.id, 0)
    assert single_page.description == "\n".join(
        f"**{index}.** **Skin {index}**" for index in range(1, 6)
    )
    assert single_controls is not None
    assert len(single_controls.children) == 5

    empty_user = await User.create(id=456)
    empty_page, empty_controls = await cog.manager_view(empty_user.id, 0)
    assert empty_page.description == "You don't have any alerts."
    assert empty_controls is None


@pytest.mark.asyncio
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
        register_component=lambda *_args: None,
    )

    card, controls = await AlertsCog(bot).manager_view(123, 0)

    assert card.description == "You don't have any alerts."
    assert controls is None
