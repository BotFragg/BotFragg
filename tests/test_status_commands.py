"""Behaviour checks for the /status command and its rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.cogs.valorant import status as status_cog
from src.cogs.valorant.status import MAX_ENTRIES, StatusCog, _entry_field
from src.services.valorant_status import (
    RegionStatus,
    StatusEntry,
    StatusUnavailable,
)
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)


class Response:
    """Record the deferral of the interaction response."""

    def __init__(self) -> None:
        """Start with no recorded deferral."""
        self.deferred: bool | None = None

    async def defer(self, *, thinking: bool = False) -> None:
        """Record whether the command deferred with a thinking state."""
        self.deferred = thinking

    @staticmethod
    def is_done() -> bool:
        """Report that the interaction already responded."""
        return True


class Followup:
    """Record follow-up messages."""

    def __init__(self) -> None:
        """Start with no recorded messages."""
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record one sent message."""
        self.sent.append(kwargs)


def interaction(
    *, response: Response | None = None, followup: Followup | None = None
) -> SimpleNamespace:
    """Build a fake interaction for the status command."""
    return _localized_interaction(
        user=SimpleNamespace(id=1),
        response=response or Response(),
        followup=followup or Followup(),
        locale=TEST_LOCALE,
    )


def build_bot(data: RegionStatus | Exception):
    """Build a localized bot with a fake status service."""
    status = (
        AsyncMock(side_effect=data)
        if isinstance(data, Exception)
        else AsyncMock(return_value=data)
    )
    service = SimpleNamespace(status=status)
    return _localized_bot(valorant_status=service), service


def entry(kind: str = "incident", title: str = "Game Server Unavailable"):
    """Build one status entry."""
    return StatusEntry(
        kind=kind,
        title=title,
        body="Dubai is unavailable.",
        updated=datetime(2026, 5, 28, 19, 37, 49, tzinfo=UTC),
        platforms=("windows", "ps5"),
    )


def account(region: str | None = "eu") -> SimpleNamespace:
    """Build the selected account used to pick a default region."""
    return SimpleNamespace(region=region)


async def test_status_uses_the_account_region_by_default(monkeypatch):
    """An explicit region is optional: the linked account picks the default."""
    monkeypatch.setattr(
        status_cog, "selected_account", AsyncMock(return_value=account("eu"))
    )
    bot, service = build_bot(RegionStatus(region="eu", entries=()))
    response = Response()
    followup = Followup()

    await StatusCog.status.callback(
        StatusCog(bot), interaction(response=response, followup=followup)
    )

    assert response.deferred is True
    assert service.status.await_args.args[0] == "eu"
    assert followup.sent[0]["embed"].title == TEST_TRANSLATOR.text(
        TEST_LOCALE, "status-title", region="EU"
    )


async def test_status_prefers_an_explicit_region(monkeypatch):
    """A supplied region must win over the account's region."""
    lookup = AsyncMock(return_value=account("eu"))
    monkeypatch.setattr(status_cog, "selected_account", lookup)
    bot, service = build_bot(RegionStatus(region="br", entries=()))

    await StatusCog.status.callback(StatusCog(bot), interaction(), region="br")

    assert service.status.await_args.args[0] == "br"
    lookup.assert_not_awaited()


async def test_status_without_an_account_uses_no_region(monkeypatch):
    """An unlinked caller must still get the default region."""
    monkeypatch.setattr(status_cog, "selected_account", AsyncMock(return_value=None))
    bot, service = build_bot(RegionStatus(region="na", entries=()))

    await StatusCog.status.callback(StatusCog(bot), interaction())

    assert service.status.await_args.args[0] is None


async def test_status_reports_no_active_entries(monkeypatch):
    """An empty region must render the all-clear message."""
    monkeypatch.setattr(status_cog, "selected_account", AsyncMock(return_value=None))
    bot, _service = build_bot(RegionStatus(region="na", entries=()))
    followup = Followup()

    await StatusCog.status.callback(StatusCog(bot), interaction(followup=followup))

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "status-all-clear"
    )


async def test_status_caps_the_number_of_entries(monkeypatch):
    """The embed must stay inside Discord's field limit and say what it hid."""
    monkeypatch.setattr(status_cog, "selected_account", AsyncMock(return_value=None))
    entries = tuple(entry() for _ in range(MAX_ENTRIES + 2))
    bot, _service = build_bot(RegionStatus(region="eu", entries=entries))
    followup = Followup()

    await StatusCog.status.callback(StatusCog(bot), interaction(followup=followup))

    card = followup.sent[0]["embed"]
    assert len(card.fields) == MAX_ENTRIES
    assert card.description == TEST_TRANSLATOR.text(TEST_LOCALE, "status-more", count=2)


async def test_status_reports_an_unavailable_feed(monkeypatch):
    """A failed fetch must use the existing Riot-unavailable message."""
    monkeypatch.setattr(status_cog, "selected_account", AsyncMock(return_value=None))
    bot, _service = build_bot(StatusUnavailable("down"))
    followup = Followup()

    await StatusCog.status.callback(StatusCog(bot), interaction(followup=followup))

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-riot-services-unavailable"
    )


def test_entry_field_formats_icon_body_and_platforms():
    """One feed entry must render its kind icon, update time, and platforms."""
    name, value = _entry_field(entry(kind="maintenance"))

    assert name.startswith("🛠")
    assert "Dubai is unavailable." in value
    assert "<t:" in value
    assert "Windows" in value and "PlayStation 5" in value
