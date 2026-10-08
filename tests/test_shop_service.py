"""Behavior checks for shop service."""

from __future__ import annotations

import asyncio
import gc
import time
from types import SimpleNamespace

import pytest

from src.services.auth import AuthenticationRequired
from src.services.catalog import Accessory
from src.services.http import HTTPFailure
from src.services.shop import (
    KC_UUID,
    VP_UUID,
    AccessoryOffer,
    ShopData,
    ShopService,
    ShopUnavailable,
)


async def test_cached_shop_requires_active_credentials() -> None:
    """Verify that cached shop requires active credentials."""

    class LoggedOutAuth:
        """Simulate missing credentials to verify cached storefront data is not served after logout."""

        async def auth_headers(self, account):
            """Return the test authorization headers for the fake account."""
            raise AuthenticationRequired("Riot login is required")

    service = ShopService(
        SimpleNamespace(use_shop_cache=True), None, LoggedOutAuth(), None
    )
    service._cache["account"] = ShopData([], [], [], 2_000_000_000, None)

    with pytest.raises(AuthenticationRequired):
        await service.storefront(SimpleNamespace(puuid="account"))


async def test_expired_shop_cache_entry_is_removed_when_refetch_fails() -> None:
    """Verify that expired shop cache entry is removed when refetch fails."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {}

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="expired-shop")
    service._cache[account.puuid] = ShopData([], [], [], int(time.time()) - 1, None)

    async def fail_fetch(_account, _headers):
        """Raise the configured failure on a storefront fetch."""
        raise ShopUnavailable("Riot is unavailable")

    service._fetch_storefront = fail_fetch

    with pytest.raises(ShopUnavailable):
        await service.storefront(account)

    assert account.puuid not in service._cache


async def test_featured_bundle_cache_expiry_does_not_change_daily_expiry() -> None:
    """Verify a bundle expiry refreshes cached data while daily expiry stays intact."""

    class Auth:
        """Provide fake Riot credentials for the storefront request."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return fake authorization headers."""
            return {}

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="early-bundle-expiry")
    now = int(time.time())
    stale = ShopData([], [], [], now + 3600, None, cache_expires=now - 1)
    fresh = ShopData([], [], [], now + 3600, None, cache_expires=now + 600)
    service._cache[account.puuid] = stale
    fetches = 0

    async def fetch(_account, _headers):
        """Replace the stale cache entry with the freshly fetched shop."""
        nonlocal fetches
        fetches += 1
        service._cache[account.puuid] = fresh
        return fresh

    service._fetch_storefront = fetch
    result = await service.storefront(account)

    assert result is fresh
    assert fetches == 1
    assert result.expires == now + 3600
    assert result.cache_expires < result.expires


async def test_shop_service_resolves_accessory_offer_data() -> None:
    """Verify that shop service resolves accessory offer data."""
    item = Accessory("Buddy", "https://example.com/buddy.png", "Limited edition")

    class Catalog:
        """Provide controlled accessory metadata for storefront offer normalization."""

        async def accessory(self, item_type: str, item_id: str) -> Accessory | None:
            """Return the configured catalog accessory fixture."""
            if (item_type, item_id) == ("buddy", "buddy-id"):
                return item
            return None

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, None, Catalog())
    data = ShopData(
        offers=[],
        accessory=[
            {
                "Offer": {
                    "Cost": {KC_UUID: "1500"},
                    "Rewards": [
                        {"ItemTypeID": "buddy", "ItemID": "buddy-id"},
                        {"ItemTypeID": "unknown", "ItemID": "missing"},
                    ],
                }
            }
        ],
        night_market=[],
        expires=4_000_000_000,
        night_market_expires=None,
    )

    assert await service.accessory_offers(data) == [AccessoryOffer(item, 1500)]


async def test_featured_bundles_keep_prices_account_scoped_and_malformed_data_safe() -> (
    None
):
    """Verify bundle data is normalized, isolated by account, and optional-safe."""

    class Auth:
        """Return fake Riot credentials for storefront parsing."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return fake credentials for the storefront request."""
            return {}

    class HTTP:
        """Provide account-specific featured bundle fixtures."""

        async def request(self, _method: str, url: str, **_kwargs):
            """Return account-specific bundles or a malformed optional section."""
            account_id = url.rsplit("/", 1)[-1]
            featured = (
                {
                    "BundlesRemainingDurationInSeconds": 300,
                    "Bundles": [
                        {
                            "ID": f"offer-{account_id}",
                            "DataAssetID": "catalog-bundle",
                            "CurrencyID": VP_UUID,
                            "Items": [
                                {
                                    "Item": {
                                        "ItemTypeID": "weapon-skin",
                                        "ItemID": f"skin-{account_id}",
                                        "Amount": 2,
                                    },
                                    "CurrencyID": VP_UUID,
                                    "BasePrice": 100,
                                    "DiscountedPrice": 50,
                                },
                                {
                                    "Item": {
                                        "ItemTypeID": "weapon-skin",
                                        "ItemID": "non-vp-item",
                                    },
                                    "CurrencyID": KC_UUID,
                                    "BasePrice": 100,
                                    "DiscountedPrice": 10,
                                },
                            ],
                            "TotalBaseCost": 1000
                            if account_id == "bundle-account-one"
                            else 2000,
                            "TotalDiscountedCost": 500
                            if account_id == "bundle-account-one"
                            else 1500,
                            "TotalDiscountPercent": 50,
                            "DurationRemainingInSeconds": 600,
                        }
                    ],
                }
                if account_id != "bundle-account-malformed"
                else {"Bundles": [None, {"ID": "broken", "Items": "invalid"}]}
            )
            if account_id == "bundle-account-absent":
                featured = None
            return SimpleNamespace(
                status=200,
                data={
                    "SkinsPanelLayout": {
                        "SingleItemOffersRemainingDurationInSeconds": 3600,
                        "SingleItemOffers": [],
                    },
                    "FeaturedBundle": featured,
                },
            )

    service = ShopService(
        SimpleNamespace(use_shop_cache=True),
        HTTP(),
        Auth(),
        SimpleNamespace(
            get_skin=lambda _uuid: None, update_prices=lambda _offers: None
        ),
    )
    first = await service.storefront(
        SimpleNamespace(puuid="bundle-account-one", region="na")
    )
    second = await service.storefront(
        SimpleNamespace(puuid="bundle-account-two", region="na")
    )
    malformed = await service.storefront(
        SimpleNamespace(puuid="bundle-account-malformed", region="na")
    )
    absent = await service.storefront(
        SimpleNamespace(puuid="bundle-account-absent", region="na")
    )

    assert first.featured_bundles[0].total_discounted_cost == 500
    assert second.featured_bundles[0].total_discounted_cost == 1500
    assert first.featured_bundles[0].items[0].item_id == "skin-bundle-account-one"
    assert first.featured_bundles[0].items[0].amount == 2
    assert first.featured_bundles[0].items[0].discounted_price == 50
    assert first.featured_bundles[0].items[1].base_price is None
    assert first.featured_bundles[0].expires <= first.expires
    assert first.cache_expires == first.featured_bundles[0].expires
    assert malformed.featured_bundles[0].items == []
    assert malformed.featured_bundles[0].total_base_cost is None
    assert absent.featured_bundles == []


async def test_shop_wallet_normalizes_transient_http_failures() -> None:
    """Verify that shop wallet normalizes transient HTTP failures."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {}

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = ShopService(SimpleNamespace(), FailingHTTP(), Auth(), None)

    with pytest.raises(ShopUnavailable):
        await service.wallet(SimpleNamespace(puuid="wallet-http", region="na"))


async def test_concurrent_storefront_requests_share_one_fetch() -> None:
    """Verify that concurrent storefront requests share one fetch."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {}

    service = ShopService(
        SimpleNamespace(use_shop_cache=True),
        SimpleNamespace(),
        Auth(),
        SimpleNamespace(),
    )
    account = SimpleNamespace(puuid="shop-race")
    data = SimpleNamespace(expires=time.time() + 60)
    fetches = 0

    async def fetch(_account, _headers) -> SimpleNamespace:
        """Return the configured result from the fake query or HTTP client."""
        nonlocal fetches
        fetches += 1
        await asyncio.sleep(0.01)
        service._cache[account.puuid] = data
        return data

    service._fetch_storefront = fetch
    results = await asyncio.gather(
        service.storefront(account),
        service.storefront(account),
    )

    assert fetches == 1
    assert results == [data, data]


async def test_shop_service_releases_idle_account_locks() -> None:
    """Verify that shop service releases idle account locks."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            return {}

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="shop-lock")

    async def fetch(_account, _headers) -> SimpleNamespace:
        """Return the configured result from the fake query or HTTP client."""
        return SimpleNamespace(expires=time.time() + 60)

    service._fetch_storefront = fetch

    await service.storefront(account)
    gc.collect()

    assert account.puuid not in service._locks
