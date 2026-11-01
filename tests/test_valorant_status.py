"""Behaviour checks for Riot's public VALORANT status feed."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import discord
import pytest

from src.services import valorant_status as status_module
from src.services.http import HTTPFailure, HTTPResult
from src.services.valorant_status import StatusService, StatusUnavailable


def feed(*, maintenances: object = None, incidents: object = None) -> dict:
    """Build one region status payload with the given entries."""
    return {
        "id": "EU",
        "name": "Europe",
        "locales": ["en_US", "de_DE"],
        "maintenances": [] if maintenances is None else maintenances,
        "incidents": [] if incidents is None else incidents,
    }


def entry(**overrides: object) -> dict:
    """Build one maintenance or incident entry."""
    values: dict[str, object] = {
        "titles": [
            {"locale": "en_US", "content": "Game Server Unavailable"},
            {"locale": "de_DE", "content": "Spielserver nicht verfügbar"},
        ],
        "updates": [
            {
                "created_at": "2026-03-02T08:20:51Z",
                "publish": True,
                "translations": [
                    {"locale": "en_US", "content": "Dubai is unavailable."},
                    {"locale": "de_DE", "content": "Dubai ist nicht verfügbar."},
                ],
            }
        ],
        "created_at": "2026-03-02T08:20:51Z",
        "updated_at": "2026-05-28T19:37:49Z",
        "platforms": ["windows", "ps5"],
        "incident_severity": "info",
    }
    values.update(overrides)
    return values


def service(payload: object) -> tuple[StatusService, AsyncMock]:
    """Build a status service whose HTTP client returns one payload."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(200, payload))
    return StatusService(http), http


async def test_empty_feed_reports_no_entries():
    """A feed without incidents or maintenance must stay usable."""
    instance, _http = service(feed())

    data = await instance.status("eu")

    assert data.region == "eu"
    assert data.entries == ()


async def test_incident_is_parsed_and_localized():
    """The feed text must follow the caller's locale with an English fallback."""
    instance, _http = service(feed(incidents=[entry()]))

    data = await instance.status("eu", discord.Locale.german)

    assert len(data.entries) == 1
    incident = data.entries[0]
    assert incident.kind == "incident"
    assert incident.title == "Spielserver nicht verfügbar"
    assert incident.body == "Dubai ist nicht verfügbar."
    assert incident.updated == datetime(2026, 5, 28, 19, 37, 49, tzinfo=UTC)
    assert incident.platforms == ("windows", "ps5")


@pytest.mark.parametrize(
    ("content", "title", "body"),
    [
        ("Dubai is unavailable.", "Dubai is unavailable.", None),
        (
            "Server maintenance in progress.\nExpected back at 18:00 UTC.",
            "Server maintenance in progress.",
            "Expected back at 18:00 UTC.",
        ),
        (
            "\nServer maintenance in progress.\nBack soon.",
            "Server maintenance in progress.",
            "Back soon.",
        ),
    ],
    ids=["single-line", "multi-line", "leading-newline"],
)
async def test_a_body_without_a_title_becomes_the_title(content, title, body):
    """The first body line becomes the title without repeating that line."""
    updates = [
        {
            "created_at": "2026-03-02T08:20:51Z",
            "publish": True,
            "translations": [{"locale": "en_US", "content": content}],
        }
    ]
    instance, _http = service(feed(incidents=[entry(titles=[], updates=updates)]))

    data = await instance.status("eu")

    assert data.entries[0].title == title
    assert data.entries[0].body == body


async def test_an_entry_without_updates_renders_its_title():
    """A missing update must not hide the entry."""
    instance, _http = service(feed(maintenances=[entry(updates=[])]))

    data = await instance.status("eu")

    assert data.entries[0].title == "Game Server Unavailable"
    assert data.entries[0].body is None


async def test_unknown_locale_falls_back_to_english():
    """A locale Riot does not translate must fall back to English."""
    instance, _http = service(feed(incidents=[entry()]))

    data = await instance.status("eu", discord.Locale.japanese)

    assert data.entries[0].title == "Game Server Unavailable"
    assert data.entries[0].body == "Dubai is unavailable."


async def test_newest_published_update_wins():
    """Drafts and older updates must not replace the latest published text."""
    updates = [
        {
            "created_at": "2026-03-01T00:00:00Z",
            "publish": True,
            "translations": [{"locale": "en_US", "content": "Old text"}],
        },
        {
            "created_at": "2026-03-05T00:00:00Z",
            "publish": False,
            "translations": [{"locale": "en_US", "content": "Draft text"}],
        },
        {
            "created_at": "2026-03-03T00:00:00Z",
            "publish": True,
            "translations": [{"locale": "en_US", "content": "New text"}],
        },
    ]
    instance, _http = service(feed(incidents=[entry(updates=updates)]))

    data = await instance.status("eu")

    assert data.entries[0].body == "New text"


async def test_archived_entries_are_skipped():
    """Archived incidents are history, not current status."""
    archived = entry(archive_at="2026-06-01T00:00:00Z")
    instance, _http = service(feed(incidents=[archived]))

    data = await instance.status("eu")

    assert data.entries == ()


async def test_entries_are_sorted_newest_first():
    """The most recently updated entry must be rendered first."""
    older = entry(updated_at="2026-01-01T00:00:00Z")
    newer = entry(updated_at="2026-06-01T00:00:00Z")
    instance, _http = service(feed(incidents=[older], maintenances=[newer]))

    data = await instance.status("eu")

    assert [item.kind for item in data.entries] == ["maintenance", "incident"]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"maintenances": "bad"},
        {"incidents": {"id": 1}},
    ],
)
async def test_malformed_payloads_raise(payload):
    """A payload with an unexpected shape must not look empty."""
    instance, _http = service(payload)

    with pytest.raises(StatusUnavailable):
        await instance.status("eu")


async def test_unusable_entries_are_skipped():
    """If one entry is malformed, the rest of the region still renders."""
    instance, _http = service(
        feed(incidents=["not an entry", {"titles": [], "updates": []}, entry()])
    )

    data = await instance.status("eu")

    assert len(data.entries) == 1


@pytest.mark.parametrize("status", [429, 500])
async def test_non_200_responses_raise(status):
    """Riot failures must map to one service error."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=HTTPResult(status, {}))
    instance = StatusService(http)

    with pytest.raises(StatusUnavailable):
        await instance.status("eu")


async def test_transport_failure_raises():
    """A transport failure is reported as unavailable, not propagated raw."""
    http = AsyncMock()
    http.request = AsyncMock(side_effect=HTTPFailure("down"))
    instance = StatusService(http)

    with pytest.raises(StatusUnavailable):
        await instance.status("eu")


async def test_concurrent_lookups_share_one_request():
    """Two simultaneous lookups for one region must fetch only once."""
    http = AsyncMock()
    calls = 0

    async def request(*_args: object, **_kwargs: object) -> HTTPResult:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return HTTPResult(200, feed())

    http.request = request
    instance = StatusService(http)

    first, second = await asyncio.gather(instance.status("eu"), instance.status("eu"))

    assert calls == 1
    assert first.entries == second.entries


async def test_cache_reuses_the_payload_for_the_ttl(monkeypatch):
    """Repeated lookups inside the window must not refetch."""
    clock = [1000.0]
    monkeypatch.setattr(status_module.time, "monotonic", lambda: clock[0])
    instance, http = service(feed())
    http.request = AsyncMock(
        side_effect=[HTTPResult(200, feed()), HTTPResult(200, feed())]
    )

    await instance.status("eu")
    await instance.status("eu")
    assert http.request.await_count == 1

    clock[0] += 61
    await instance.status("eu")
    assert http.request.await_count == 2


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        (None, "na"),
        ("EU", "eu"),
        ("latam", "latam"),
        ("br", "br"),
        ("sea", "na"),
    ],
)
def test_region_for_maps_to_supported_files(region, expected):
    """Unknown game regions must fall back to the default status file."""
    assert StatusService.region_for(region) == expected
