"""Behavior and regression checks for catalog."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from datetime import UTC, datetime
from datetime import time as utc_time
from pathlib import Path
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from src.cogs.tasks import TasksCog
from src.services import catalog as catalog_module
from src.services.catalog import (
    CATALOG_FORMAT_VERSION,
    Bundle,
    CatalogService,
    Skin,
    localized_text,
)
from src.services.gameplay import GameplayService
from src.services.http import HTTPFailure


@pytest.fixture
def changing_catalog(tmp_path):
    state = SimpleNamespace(version="v1", calls=0, missing=False)

    async def request(_method, url):
        if url.endswith("/version"):
            data = {"version": state.version}
        elif "/weapons?" in url:
            data = [{"skins": [{"uuid": "skin"}]}]
        elif "/bundles?" in url:
            data = [{"uuid": "bundle"}]
        else:
            state.calls += 1
            if state.missing and "/sprays/" in url:
                return NS(status=404, data={})
            item = {"uuid": "item", "displayName": state.version}
            data = item
            if "/buddies?" in url:
                data = [item]
                if state.version == "v2":
                    data.append({"uuid": "new-item", "displayName": state.version})
        return NS(status=200, data={"data": data})

    service = CatalogService(NS(request=request))
    service.path = tmp_path / "skins.json"
    return service, state


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("failure", ["transport", "status", "malformed"])
async def test_failed_mission_metadata_refresh_has_shared_cooldown(
    monkeypatch, cached, failure
):
    now = [2000.0]
    monkeypatch.setattr(catalog_module.time, "monotonic", lambda: now[0])
    recovered = False

    async def request(*args, **kwargs):
        await asyncio.sleep(0)
        if recovered:
            return NS(status=200, data={"data": [{"uuid": "fresh", "title": "Fresh"}]})
        if failure == "transport":
            raise HTTPFailure("Synthetic metadata outage")
        return NS(status=503 if failure == "status" else 200, data={"data": None})

    http = NS(request=AsyncMock(side_effect=request))
    service = CatalogService(http)
    previous = {"old": {"title": "Cached"}} if cached else {}
    service._mission_definitions = previous
    if cached:
        service._mission_metadata_loaded_at = 0.0
    results = await asyncio.gather(*(service.mission_metadata() for _ in range(10)))
    assert all(result is previous for result in results)
    assert http.request.await_count == 1
    recovered = True
    now[0] += 29
    assert await service.mission_metadata() is previous
    assert http.request.await_count == 1
    now[0] += 1
    result = await service.mission_metadata()
    assert result["fresh"]["title"] == "Fresh"
    assert http.request.await_count == 2
    now[0] += catalog_module.MISSION_METADATA_TTL - 1
    assert await service.mission_metadata() is result
    assert http.request.await_count == 2


@pytest.mark.parametrize("buddy", [False, True])
@pytest.mark.parametrize("missing", [False, True])
async def test_catalog_version_change_refreshes_accessory_metadata(
    changing_catalog, buddy, missing
):
    service, state = changing_catalog
    item_type = (
        catalog_module.BUDDY_ITEM_TYPE_ID
        if buddy
        else "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
    )
    await service.refresh()
    state.missing = missing
    identifier = "new-item" if buddy and missing else "item"
    original = await service.accessory(item_type, identifier)
    assert (original is None) == missing
    state.version = "v2"
    state.missing = False
    await service.refresh(check_version=True)
    result = await service.accessory(item_type, identifier)
    assert result is not None and result.name == "v2"
    assert state.calls == 2


@pytest.mark.parametrize("failed", [False, True])
async def test_same_version_or_failed_refresh_preserves_accessory_cache(
    changing_catalog, monkeypatch, failed
):
    service, state = changing_catalog
    await service.refresh()
    item_type = "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
    spray = await service.accessory(item_type, "item")
    buddy = await service.accessory(catalog_module.BUDDY_ITEM_TYPE_ID, "item")
    if failed:
        state.version = "v2"
        monkeypatch.setattr(service, "_save", Mock(side_effect=OSError("write failed")))
        with pytest.raises(OSError):
            await service.refresh(check_version=True)
    else:
        await service.refresh(check_version=True)
        await service.refresh()
    assert await service.accessory(item_type, "item") is spray
    assert await service.accessory(catalog_module.BUDDY_ITEM_TYPE_ID, "item") is buddy
    assert state.calls == 2 and service.version == "v1"


async def test_cancelled_failed_catalog_save_rolls_back_and_retries(
    changing_catalog, monkeypatch
):
    service, state = changing_catalog
    await service.refresh()
    original = service._serialize()
    spray = await service.accessory("d5f120f8-ff8c-4aac-92ea-f2b5acbe9475", "item")
    buddy = await service.accessory(catalog_module.BUDDY_ITEM_TYPE_ID, "item")
    generation = service._accessory_generation
    state.version = "v2"
    started, release = asyncio.Event(), asyncio.Event()
    save = service._save

    async def failed_worker(_function, *_args):
        started.set()
        await release.wait()
        raise OSError("synthetic write failure")

    monkeypatch.setattr(catalog_module.asyncio, "to_thread", failed_worker)
    refresh = asyncio.create_task(service.refresh(check_version=True))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        refresh.cancel()
        await asyncio.sleep(0)
        refresh.cancel()
        await asyncio.sleep(0)
        assert not refresh.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(refresh, timeout=2)

    assert service._serialize() == original
    assert service.path.read_text(encoding="utf-8") == original
    assert service._accessory_generation == generation
    assert (
        await service.accessory("d5f120f8-ff8c-4aac-92ea-f2b5acbe9475", "item") is spray
    )
    assert await service.accessory(catalog_module.BUDDY_ITEM_TYPE_ID, "item") is buddy

    writer = AsyncMock(side_effect=lambda function, *args: function(*args))
    monkeypatch.setattr(catalog_module.asyncio, "to_thread", writer)
    await service.refresh(check_version=True)
    writer.assert_awaited_once()
    assert writer.call_args.args[0] == save
    assert json.loads(service.path.read_text(encoding="utf-8"))["version"] == "v2"
    assert service.version == "v2"
    assert service._accessory_generation == generation + 1
    assert service._accessories == {} and service._buddy_catalog is None


@pytest.mark.parametrize("buddy", [False, True])
@pytest.mark.parametrize("missing", [False, True])
async def test_inflight_accessory_request_cannot_restore_old_cache(
    changing_catalog, buddy, missing
):
    service, state = changing_catalog
    await service.refresh()
    state.missing = missing
    started, release = asyncio.Event(), asyncio.Event()
    original_request = service.http.request

    async def delayed_request(method, url):
        response = await original_request(method, url)
        if "/buddies?" in url or "/sprays/" in url:
            started.set()
            await release.wait()
        return response

    service.http.request = delayed_request
    item_type = (
        catalog_module.BUDDY_ITEM_TYPE_ID
        if buddy
        else "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
    )
    identifier = "new-item" if buddy and missing else "item"
    lookup = asyncio.create_task(service.accessory(item_type, identifier))
    try:
        await asyncio.wait_for(started.wait(), 1)
        state.version, state.missing = "v2", False
        await service.refresh(check_version=True)
    finally:
        release.set()
        await asyncio.wait_for(lookup, 1)
    result = await service.accessory(item_type, identifier)
    assert result is not None and result.name == "v2"
    assert state.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"data": None},
        {"data": ["malformed"]},
        {"data": {}},
        {"data": {"manifestId": []}},
        {"data": {"version": 1}},
    ],
)
async def test_catalog_version_failure_is_recoverable(payload):
    catalog = CatalogService(
        NS(request=AsyncMock(return_value=NS(status=200, data=payload)))
    )
    with pytest.raises(HTTPFailure):
        await catalog.refresh()


@pytest.mark.asyncio
async def test_malformed_weapon_rows_do_not_kill_catalog_loop():
    async def request(method, url, **kwargs):
        if url.endswith("/version"):
            return NS(status=200, data={"data": {"manifestId": "synthetic"}})
        if "/weapons?" in url:
            return NS(status=200, data={"data": [None]})
        return NS(status=200, data={"data": [{"uuid": "bundle"}]})

    catalog = CatalogService(NS(request=request))
    bot = NS(
        config=NS(
            user_agent_interval_minutes=15,
            game_version_interval_minutes=15,
            alert_time_utc=utc_time(0, 0),
            log_flush_interval_seconds=10,
        ),
        wait_until_ready=AsyncMock(),
        catalog=catalog,
        shop=NS(prune_expired=lambda: None),
    )
    cog = TasksCog(bot)
    loop = cog.catalog_refresh
    task = loop.start()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=0.15)
    except HTTPFailure, TimeoutError:
        pass
    finally:
        loop.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not loop.failed()


@pytest.mark.parametrize(
    "kind, rows",
    [
        ("weapons", [None]),
        ("weapons", [{"skins": {}}]),
        ("weapons", [{"skins": [None]}]),
        ("weapons", [{"skins": [{"uuid": []}]}]),
        ("weapons", [{"skins": [{}]}]),
        ("weapons", [{"skins": [{"uuid": "skin", "levels": {}}]}]),
        ("weapons", [{"skins": [{"uuid": "skin", "levels": [None]}]}]),
        ("weapons", [{"skins": [{"uuid": "skin", "chromas": {}}]}]),
        ("weapons", [{"skins": [{"uuid": "skin", "chromas": [None]}]}]),
        (
            "weapons",
            [{"skins": [{"uuid": "skin", "chromas": [{"streamedVideo": []}]}]}],
        ),
        ("bundles", [None]),
        ("bundles", [{"uuid": {}}]),
        ("bundles", [{"uuid": "bundle", "displayIcon": []}]),
    ],
)
async def test_upstream_catalog_failure_preserves_cache_and_retries(
    tmp_path, kind, rows
):
    valid = {
        "weapons": [{"skins": [{"uuid": "skin", "levels": [{"uuid": "offer"}]}]}],
        "bundles": [{"uuid": "bundle"}],
    }
    broken = True

    async def request(method, url, **kwargs):
        if url.endswith("/version"):
            return NS(status=200, data={"data": {"manifestId": "new"}})
        endpoint = "weapons" if "/weapons?" in url else "bundles"
        return NS(
            status=200,
            data={"data": rows if broken and endpoint == kind else valid[endpoint]},
        )

    catalog = CatalogService(NS(request=request))
    catalog.path = tmp_path / "skins.json"
    catalog.skins = {"old": Skin("old", "old-offer", "Old", None, None)}
    catalog.bundles = {"old": Bundle("old", "Old", None, None, None)}
    catalog.version = "old"
    catalog._cache_format = CATALOG_FORMAT_VERSION
    catalog._reindex()
    snapshot = catalog._serialize()
    catalog.path.write_text(snapshot, encoding="utf-8")
    with pytest.raises(HTTPFailure):
        await catalog.refresh(check_version=True)
    assert catalog.get_skin("old-offer").name == "Old"
    assert catalog.get_bundle("old").name == "Old"
    assert catalog.version == "old"
    assert catalog.path.read_text(encoding="utf-8") == snapshot
    broken = False
    await catalog.refresh(check_version=True)
    assert catalog.get_skin("offer").uuid == "skin"
    assert catalog.get_bundle("bundle") is not None
    assert catalog.version == "new"


async def test_bad_buddy_level_container_is_retryable():
    catalog = CatalogService(
        NS(
            request=AsyncMock(
                return_value=NS(
                    status=200, data={"data": [{"uuid": "buddy", "levels": 5}]}
                )
            )
        )
    )
    with pytest.raises(HTTPFailure):
        await catalog._buddy_accessory("buddy")
    assert catalog._buddy_catalog is None
    catalog.http.request.return_value.data = {
        "data": [
            {
                "uuid": "buddy",
                "displayName": {"en-US": "Buddy", "fr-FR": "Copain"},
                "levels": [
                    {"uuid": "level", "displayIcon": "https://example.com/buddy.png"}
                ],
            }
        ]
    }
    item = await catalog.accessory("dd3bf334-87f3-40bd-b043-682a57a8dc3a", "level")
    assert item.name_for(discord.Locale.french) == "Copain"
    assert item.icon == "https://example.com/buddy.png"
    assert catalog.http.request.await_count == 2


@pytest.mark.parametrize(
    "rows",
    [
        [None],
        [{"uuid": []}],
        [{"uuid": "buddy", "displayIcon": []}],
        [{"uuid": "buddy", "levels": [None]}],
        [{"uuid": "buddy", "levels": [{"uuid": "level", "displayIcon": []}]}],
    ],
)
async def test_malformed_buddy_rows_never_publish_partial_cache(rows):
    catalog = CatalogService(
        NS(
            request=AsyncMock(
                return_value=NS(status=200, data={"data": [{"uuid": "valid"}, *rows]})
            )
        )
    )
    with pytest.raises(HTTPFailure):
        await catalog._buddy_accessory("valid")
    assert catalog._buddy_catalog is None


@pytest.mark.parametrize("levels", [None, []])
async def test_buddy_optional_levels_remain_supported(levels):
    catalog = CatalogService(
        NS(
            request=AsyncMock(
                return_value=NS(
                    status=200,
                    data={
                        "data": [
                            {"uuid": "buddy", "displayName": "Buddy", "levels": levels}
                        ]
                    },
                )
            )
        )
    )
    assert (await catalog._buddy_accessory("buddy")).name == "Buddy"


@pytest.mark.parametrize(
    "item_type, field",
    [
        ("d5f120f8-ff8c-4aac-92ea-f2b5acbe9475", "fullTransparentIcon"),
        ("3f296c07-64c3-494c-923b-fe692a4fa1bd", "largeArt"),
        ("3f296c07-64c3-494c-923b-fe692a4fa1bd", "wideArt"),
        ("d5f120f8-ff8c-4aac-92ea-f2b5acbe9475", "displayIcon"),
        ("03a572de-4234-31ed-d344-ababa488f981", "displayIcon"),
    ],
)
async def test_accessory_media_is_validated_before_caching(item_type, field):
    request = AsyncMock(
        return_value=NS(
            status=200,
            data={"data": {"displayName": "Synthetic", field: ["malformed"]}},
        )
    )
    catalog = CatalogService(NS(request=request))
    with pytest.raises(HTTPFailure):
        await catalog.accessory(item_type, "synthetic")
    assert catalog._accessories == {}
    request.return_value.data = {
        "data": {"displayName": "Recovered", field: "https://example.com/recovered.png"}
    }
    recovered = await catalog.accessory(item_type, "synthetic")
    assert recovered.icon == "https://example.com/recovered.png"
    assert await catalog.accessory(item_type, "synthetic") is recovered
    assert request.await_count == 2


@pytest.mark.parametrize(
    "item_type, field",
    [
        ("d5f120f8-ff8c-4aac-92ea-f2b5acbe9475", "fullTransparentIcon"),
        ("3f296c07-64c3-494c-923b-fe692a4fa1bd", "largeArt"),
        ("03a572de-4234-31ed-d344-ababa488f981", "displayIcon"),
    ],
)
@pytest.mark.parametrize("icon", [None, "https://example.com/valid.png"])
async def test_valid_accessory_media_remains_cached(item_type, field, icon):
    request = AsyncMock(
        return_value=NS(
            status=200, data={"data": {"displayName": "Valid", field: icon}}
        )
    )
    catalog = CatalogService(NS(request=request))
    item = await catalog.accessory(item_type, "synthetic")
    assert item.icon == icon
    assert await catalog.accessory(item_type, "synthetic") is item
    assert request.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "snapshot",
    [
        [],
        {},
        {"skins": True},
        {"skins": [None]},
        {"skins": [{"uuid": "skin", "offer_uuid": "offer", "levels": [None]}]},
        {"skins": [{"uuid": "skin", "offer_uuid": "offer"}], "bundles": [None]},
        {"format_version": []},
    ],
)
async def test_structurally_invalid_catalog_recovers(tmp_path, snapshot):
    service = CatalogService(NS())
    service.path = tmp_path / "skins.json"
    service.path.write_text(json.dumps(snapshot), encoding="utf-8")
    service.refresh = AsyncMock()
    await service.load()
    service.refresh.assert_awaited_once()


async def test_invalid_catalog_and_failed_refresh_preserve_previous_indexes(tmp_path):
    service = CatalogService(NS(request=AsyncMock(side_effect=HTTPFailure("offline"))))
    service.path = tmp_path / "skins.json"
    service.skins = {"old": Skin("old", "offer", "Old", None, None)}
    service.bundles = {"old": Bundle("old", "Old", None, None, None)}
    service.version = "old"
    service._cache_format = CATALOG_FORMAT_VERSION
    service._reindex()
    service.path.write_text(
        json.dumps(
            {"skins": [{"uuid": "new", "offer_uuid": "new"}], "bundles": [None]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(HTTPFailure):
        await service.load()
    assert service.get_skin("offer").name == "Old"
    assert service.get_skin("new") is None
    assert service.get_bundle("old").name == "Old"
    assert service.version == "old" and service._cache_format == CATALOG_FORMAT_VERSION


async def test_gameplay_missions_join_contract_progress_with_catalog_metadata() -> None:
    """Verify mission metadata is localized while joining live progress."""
    urls: list[str] = []

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {"Authorization": "test"}

    class HTTP:
        """Stub the shared Riot client so request handling and shutdown can be observed."""

        async def request(self, _method, url, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            urls.append(url)
            if "/contracts/v1/contracts/" in url:
                assert kwargs["headers"] == {"Authorization": "test"}
                return SimpleNamespace(
                    status=200,
                    data={
                        "Missions": [
                            {
                                "ID": "weekly-mission",
                                "Objectives": {"headshots": 15},
                                "Complete": False,
                                "ExpirationTime": "2026-09-28T00:00:00Z",
                            }
                        ]
                    },
                )
            if "/v1/missions?" in url:
                assert url.endswith("?language=all")
                return SimpleNamespace(
                    status=200,
                    data={
                        "data": [
                            {
                                "uuid": "weekly-mission",
                                "title": {
                                    "en-US": "Kill players with headshots",
                                    "fr-FR": "Éliminez des joueurs par tirs à la tête",
                                },
                                "type": "EAresMissionType::Weekly",
                                "xpGrant": 20000,
                                "progressToComplete": 100,
                                "objectives": [
                                    {"objectiveUuid": "headshots", "value": 100}
                                ],
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected request: {url}")

    http = HTTP()
    service = GameplayService(http, Auth(), CatalogService(http))

    missions = await service.missions(
        SimpleNamespace(puuid="player", region="na"), locale="fr"
    )

    assert len(missions) == 1
    assert missions[0]["type"] == "Weekly Missions"
    assert missions[0]["title"] == "Éliminez des joueurs par tirs à la tête"
    assert missions[0]["xp"] == 20000
    assert missions[0]["tasks"] == [{"progress": 15, "target": 100}]
    assert missions[0]["expires"] == datetime(2026, 9, 28, tzinfo=UTC)
    assert sum("/contracts/v1/contracts/" in url for url in urls) == 1
    assert sum("/v1/missions?" in url for url in urls) == 1
    assert len(urls) == 2


async def test_catalog_load_reads_file_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that catalog load reads file off event loop."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"
        path.write_text(
            json.dumps(
                {
                    "format_version": catalog_module.CATALOG_FORMAT_VERSION,
                    "version": "test",
                    "skins": [{"uuid": "skin", "offer_uuid": "offer"}],
                    "bundles": [{"uuid": "bundle"}],
                }
            ),
            encoding="utf-8",
        )
        service = CatalogService(SimpleNamespace())
        service.path = path
        caller_thread = threading.get_ident()
        read_threads: list[int] = []
        original_read_text = Path.read_text

        def track_read(self, *args, **kwargs):
            """Record the worker thread used to read the catalog snapshot."""
            read_threads.append(threading.get_ident())
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", track_read)
        await service.load()

        assert read_threads and read_threads[0] != caller_thread


async def test_catalog_snapshot_round_trips_skin_chromas() -> None:
    """Verify localized catalog names and skin chromas survive cache round trips."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"
        urls: list[str] = []

        class CatalogHTTP:
            """Provide deterministic multilingual catalog responses."""

            async def request(self, _method: str, url: str):
                """Return the requested catalog fixture."""
                urls.append(url)
                if url.endswith("/version"):
                    return SimpleNamespace(
                        status=200, data={"data": {"manifestId": "manifest"}}
                    )
                if "/bundles?" in url:
                    return SimpleNamespace(
                        status=200,
                        data={
                            "data": [
                                {
                                    "uuid": "bundle",
                                    "displayName": {
                                        "en-US": "Test Bundle",
                                        "fr-FR": "Pack de test",
                                    },
                                    "displayNameSubText": {
                                        "en-US": "Limited Edition",
                                        "fr-FR": "Édition limitée",
                                    },
                                    "extraDescription": {
                                        "en-US": "A test bundle",
                                        "fr-FR": "Un pack de test",
                                    },
                                    "displayIcon": "https://example.com/bundle.png",
                                    "assetPath": "ShooterGame/Content/Bundles/Test",
                                }
                            ]
                        },
                    )
                return SimpleNamespace(
                    status=200,
                    data={
                        "data": [
                            {
                                "skins": [
                                    {
                                        "uuid": "skin",
                                        "displayName": {
                                            "en-US": "Test Skin",
                                            "fr-FR": "Peau de test",
                                        },
                                        "assetPath": "ShooterGame/Content/Weapons/Skin",
                                        "levels": [
                                            {
                                                "uuid": "level",
                                                "displayName": {
                                                    "en-US": "Test Skin Level 2",
                                                    "fr-FR": "Peau de test niveau 2",
                                                },
                                                "streamedVideo": "https://example.com/level.mp4",
                                            }
                                        ],
                                        "chromas": [
                                            {
                                                "uuid": "chroma",
                                                "displayName": {
                                                    "en-US": "Test Skin Green",
                                                    "fr-FR": "Peau de test verte",
                                                },
                                                "streamedVideo": "https://example.com/chroma.mp4",
                                            }
                                        ],
                                    }
                                ]
                            }
                        ]
                    },
                )

        service = CatalogService(CatalogHTTP())
        service.path = path
        await service.refresh()

        loaded = CatalogService(SimpleNamespace())
        loaded.path = path
        await loaded.load()

        assert any(url.endswith("/weapons?language=all") for url in urls)
        assert any(url.endswith("/bundles?language=all") for url in urls)
        skin = loaded.get_skin("skin")
        assert skin is not None
        assert skin.name == "Test Skin"
        assert skin.name_for("fr") == "Peau de test"
        assert skin.name_for("cs") == "Test Skin"
        assert localized_text(skin.levels[0]["displayName"], "fr") == (
            "Peau de test niveau 2"
        )
        assert localized_text(skin.chromas[0]["displayName"], "fr") == (
            "Peau de test verte"
        )
        assert loaded.search_skins("Peau de test", locale="fr")[0] == skin
        assert loaded.search_skins("Test Skin", locale="fr")[0] == skin
        assert skin.chromas == [
            {
                "uuid": "chroma",
                "displayName": {
                    "en-US": "Test Skin Green",
                    "fr-FR": "Peau de test verte",
                },
                "streamedVideo": "https://example.com/chroma.mp4",
            }
        ]
        assert skin.levels[0]["streamedVideo"] == "https://example.com/level.mp4"
        bundle = loaded.get_bundle("bundle")
        assert bundle is not None
        assert bundle.name_for("fr") == "Pack de test"
        assert bundle.subtitle_for("fr") == "Édition limitée"
        assert bundle.description_for("fr") == "Un pack de test"


async def test_catalog_load_refreshes_legacy_snapshot_with_same_manifest() -> None:
    """Verify a legacy snapshot refreshes even when Riot's manifest matches."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"
        path.write_text(
            json.dumps(
                {
                    "version": "manifest",
                    "skins": [
                        {
                            "uuid": "skin",
                            "offer_uuid": "offer",
                            "name": "Skin",
                            "levels": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        calls: list[str] = []

        class CatalogHTTP:
            """Provide manifest and upgraded catalog responses for the test."""

            async def request(self, _method: str, url: str):
                """Record requests and return the configured catalog response."""
                calls.append(url)
                if url.endswith("/version"):
                    return SimpleNamespace(
                        status=200, data={"data": {"manifestId": "manifest"}}
                    )
                if "/bundles?" in url:
                    return SimpleNamespace(
                        status=200,
                        data={"data": [{"uuid": "bundle", "displayName": "Bundle"}]},
                    )
                return SimpleNamespace(
                    status=200,
                    data={
                        "data": [
                            {
                                "skins": [
                                    {
                                        "uuid": "skin",
                                        "displayName": "Skin",
                                        "levels": [{"uuid": "offer"}],
                                        "chromas": [{"uuid": "chroma"}],
                                    }
                                ]
                            }
                        ]
                    },
                )

        http = CatalogHTTP()
        service = CatalogService(http)
        service.path = path
        await service.load()

        assert any("/weapons?" in url for url in calls)
        assert service._cache_format == catalog_module.CATALOG_FORMAT_VERSION
        assert service.get_skin("skin").chromas == [{"uuid": "chroma"}]


async def test_failed_catalog_upgrade_keeps_legacy_data_and_retries() -> None:
    """Verify failed bundle refreshes preserve the old catalog and remain retryable."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"
        path.write_text(
            json.dumps(
                {
                    "format_version": catalog_module.CATALOG_FORMAT_VERSION,
                    "version": "old-manifest",
                    "skins": [
                        {
                            "uuid": "old-skin",
                            "offer_uuid": "old-offer",
                            "name": "Old skin",
                        }
                    ],
                    "bundles": [
                        {
                            "uuid": "old-bundle",
                            "name": "Old bundle",
                            "asset_path": "old/path",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        class CatalogHTTP:
            """Return catalog failures while tracking upgrade attempts."""

            weapons_calls = 0
            bundle_calls = 0

            async def request(self, _method: str, url: str):
                """Return valid weapons and an empty bundle catalog."""
                if url.endswith("/version"):
                    return SimpleNamespace(
                        status=200, data={"data": {"manifestId": "new-manifest"}}
                    )
                if "/weapons?" in url:
                    self.weapons_calls += 1
                    return SimpleNamespace(
                        status=200,
                        data={"data": [{"skins": [{"uuid": "new-skin"}]}]},
                    )
                self.bundle_calls += 1
                return SimpleNamespace(status=200, data={"data": []})

        http = CatalogHTTP()
        service = CatalogService(http)
        service.path = path

        await service.load()
        with pytest.raises(HTTPFailure, match="empty bundles catalog"):
            await service.refresh(check_version=True)
        assert service.get_skin("old-skin").name == "Old skin"
        assert service.get_bundle("old-bundle").name == "Old bundle"

        with pytest.raises(HTTPFailure, match="empty bundles catalog"):
            await service.refresh(check_version=True)
        assert http.weapons_calls == 2
        assert http.bundle_calls == 2
        assert service.get_skin("old-skin").name == "Old skin"
        assert service.get_bundle("old-bundle").name == "Old bundle"


def test_catalog_data_file_uses_the_working_directory() -> None:
    """Verify that catalog data file uses the working directory."""
    assert CatalogService(SimpleNamespace()).path == Path.cwd() / "data" / "skins.json"


async def test_concurrent_accessory_lookups_share_one_request() -> None:
    """Verify that concurrent accessory lookups share one request."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    request_urls: list[str] = []

    class HTTP:
        """Stub the shared Riot client so request handling and shutdown can be observed."""

        async def request(self, _method: str, url: str):
            """Record request arguments and return the configured HTTP response."""
            nonlocal calls
            calls += 1
            request_urls.append(url)
            started.set()
            await release.wait()
            return SimpleNamespace(
                status=200,
                data={
                    "data": [
                        {
                            "uuid": "buddy-base",
                            "displayName": {
                                "en-US": "Buddy",
                                "fr-FR": "Porte-bonheur",
                            },
                            "levels": [
                                {
                                    "uuid": "buddy-id",
                                    "displayIcon": "https://example.com/buddy.png",
                                }
                            ],
                        }
                    ]
                },
            )

    service = CatalogService(HTTP())
    item_type = "dd3bf334-87f3-40bd-b043-682a57a8dc3a"
    first = asyncio.create_task(service.accessory(item_type, "buddy-id"))
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(service.accessory(item_type, "buddy-id"))
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.wait_for(asyncio.gather(first, second), timeout=1)

    assert calls == 1
    assert results[0] is not None and results[0].name == "Buddy"
    assert results[0].name_for("fr") == "Porte-bonheur"
    assert request_urls == ["https://valorant-api.com/v1/buddies?language=all"]
    assert results[0] == results[1]


async def test_accessory_lookup_retries_after_a_transient_response() -> None:
    """Verify that temporary accessory API failures are not cached as missing items."""

    class HTTP:
        """Return a temporary failure followed by a valid accessory response."""

        calls = 0

        async def request(self, _method: str, _url: str):
            """Return the next configured accessory response."""
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(status=503, data={})
            if self.calls == 2:
                return SimpleNamespace(status=200, data={"data": []})
            return SimpleNamespace(
                status=200,
                data={"data": {"displayName": "Spray", "displayIcon": None}},
            )

    http = HTTP()
    service = CatalogService(http)
    item_type = "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"

    with pytest.raises(HTTPFailure):
        await service.accessory(item_type, "spray-id")
    with pytest.raises(HTTPFailure):
        await service.accessory(item_type, "spray-id")
    item = await service.accessory(item_type, "spray-id")

    assert item is not None and item.name == "Spray"
    assert http.calls == 3


async def test_missing_accessory_404_is_negative_cached() -> None:
    """Verify confirmed missing catalog items do not trigger repeated HTTP requests."""

    class HTTP:
        """Count missing-item requests for the cache assertion."""

        calls = 0

        async def request(self, _method: str, _url: str):
            """Return a confirmed not-found response."""
            self.calls += 1
            return SimpleNamespace(status=404, data={"status": 404})

    http = HTTP()
    service = CatalogService(http)
    item_type = "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"

    assert await service.accessory(item_type, "missing-spray") is None
    assert await service.accessory(item_type, "missing-spray") is None
    assert http.calls == 1


async def test_catalog_refresh_writes_a_stable_snapshot_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that catalog refresh writes a stable snapshot off event loop."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"

        class CatalogHTTP:
            """Provide fake version, weapons, and bundle catalog responses."""

            async def request(self, _method, url):
                """Return the matching version or catalog fixture."""
                if url.endswith("/version"):
                    return SimpleNamespace(status=200, data={"data": {"version": "v1"}})
                if "/bundles?" in url:
                    return SimpleNamespace(
                        status=200,
                        data={"data": [{"uuid": "bundle", "displayName": "Bundle"}]},
                    )
                return SimpleNamespace(
                    status=200,
                    data={
                        "data": [
                            {
                                "skins": [
                                    {
                                        "uuid": "skin",
                                        "displayName": "Skin",
                                        "levels": [{"uuid": "offer"}],
                                    }
                                ]
                            }
                        ]
                    },
                )

        service = CatalogService(CatalogHTTP())
        service.path = path
        caller_thread = threading.get_ident()
        write_threads: list[int] = []
        worker_started = asyncio.Event()
        release_worker = asyncio.Event()
        original_to_thread = asyncio.to_thread
        original_write_text = Path.write_text

        def track_write(self, *args, **kwargs):
            """Record the worker thread used to write the catalog snapshot."""
            write_threads.append(threading.get_ident())
            return original_write_text(self, *args, **kwargs)

        async def delayed_to_thread(function, *args, **kwargs):
            """Wait for the test gate before invoking the worker-thread operation."""
            worker_started.set()
            await release_worker.wait()
            return await original_to_thread(function, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", track_write)
        monkeypatch.setattr(catalog_module.asyncio, "to_thread", delayed_to_thread)
        refresh = asyncio.create_task(service.refresh())
        try:
            await asyncio.wait_for(worker_started.wait(), timeout=1)
            service.skins["skin"].price = 1775
        finally:
            release_worker.set()
            await asyncio.wait_for(refresh, timeout=2)

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert write_threads and write_threads[0] != caller_thread
        assert saved["skins"][0]["price"] is None
        assert service.skins["skin"].price == 1775


async def test_catalog_refresh_waits_for_file_worker_after_repeated_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that catalog refresh waits for file worker after repeated cancellation."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"

        class VersionHTTP:
            """Provide a stable game version to the catalog refresh test."""

            async def request(self, _method, _url):
                """Return the configured version response."""
                return SimpleNamespace(status=200, data={"data": {"version": "v1"}})

        service = CatalogService(VersionHTTP())
        service.path = path

        async def fetch_weapons(_kind):
            """Return the minimum metadata needed by catalog refresh."""
            if _kind == "bundles":
                return [{"uuid": "bundle", "displayName": "Bundle"}]
            return [{"skins": [{"uuid": "skin", "displayName": "Skin"}]}]

        service._fetch_data = fetch_weapons
        service._accessories[("sprays", "old")] = None
        service._buddy_catalog = {}
        worker_started = asyncio.Event()
        release_worker = asyncio.Event()
        original_to_thread = asyncio.to_thread

        async def delayed_to_thread(function, *args, **kwargs):
            """Hold the file worker until cancellation behavior has been observed."""
            worker_started.set()
            await release_worker.wait()
            return await original_to_thread(function, *args, **kwargs)

        monkeypatch.setattr(catalog_module.asyncio, "to_thread", delayed_to_thread)
        refresh = asyncio.create_task(service.refresh())
        await asyncio.wait_for(worker_started.wait(), timeout=1)
        refresh.cancel()
        await asyncio.sleep(0)
        refresh.cancel()
        await asyncio.sleep(0)
        assert not refresh.done()
        release_worker.set()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(refresh, timeout=2)

        assert path.exists()
        assert service._accessories == {} and service._buddy_catalog is None
