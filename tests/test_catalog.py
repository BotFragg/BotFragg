"""Behavior checks for catalog."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services import catalog as catalog_module
from src.services.catalog import CatalogService, localized_text
from src.services.gameplay import GameplayService
from src.services.http import HTTPFailure


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
                    "skins": [],
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

    assert await service.accessory(item_type, "spray-id") is None
    assert await service.accessory(item_type, "spray-id") is None
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
