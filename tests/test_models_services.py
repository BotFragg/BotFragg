"""Tests for model invariants and account, authentication, shop, and catalog services."""

from __future__ import annotations

import asyncio
import base64
import gc
import json
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from tortoise.exceptions import IntegrityError

from src.models import (
    Account,
    Alert,
    CommandInvocation,
    ShardStatusMessage,
    Suggestion,
    SuggestionFollower,
    User,
)
from src.services import accounts as accounts_service
from src.services import catalog as catalog_module
from src.services.accounts import (
    account_for_user,
    count_registered_users,
    daily_shop_user_ids,
    delete_user_data,
    get_user,
    select_account,
    selected_account,
    update_user_preference,
)
from src.services.auth import AuthenticationRequired, AuthService, decode_jwt
from src.services.catalog import Accessory, Bundle, CatalogService
from src.services.crypto import AuthVault
from src.services.gameplay import GameplayService, GameplayUnavailable
from src.services.http import HTTPFailure
from src.services.shop import (
    KC_UUID,
    VP_UUID,
    AccessoryOffer,
    ShopData,
    ShopService,
    ShopUnavailable,
)


def _fake_access_token(expires_in: int = 3600) -> str:
    """Create a JWT-shaped access token with the requested expiry."""
    expiry = int(time.time()) + expires_in
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode())
        .decode()
        .rstrip("=")
    )
    return f"x.{payload}.x"


def _fake_jwt(**claims: object) -> str:
    """Create a JWT-shaped token containing the supplied claims."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{payload}.x"


@pytest.mark.usefixtures("database")
async def test_account_selection_preserves_invariant() -> None:
    """Verify that account selection preserves invariant."""
    user = await User.create(id=123)
    first = await Account.create(
        puuid="first", user=user, username="One#NA", region="na"
    )
    second = await Account.create(
        puuid="second", user=user, username="Two#EU", region="eu"
    )
    assert (await selected_account(user.id)).puuid == first.puuid
    resolved = await account_for_user(user.id, first.puuid)
    assert resolved is not None and resolved.puuid == first.puuid
    assert await account_for_user(999, first.puuid) is None
    await select_account(user.id, second)
    assert (await selected_account(user.id)).puuid == second.puuid


@pytest.mark.usefixtures("database")
async def test_selected_account_updates_user_timestamp() -> None:
    """Verify that selected account updates user timestamp."""
    user = await User.create(id=127)
    account = await Account.create(puuid="fallback", user=user, username="One#NA")
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    result = await selected_account(user.id)

    saved = await User.get(id=user.id)
    assert result is not None and result.puuid == account.puuid
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_user_preference_updates_user_timestamp() -> None:
    """Verify that user preference updates user timestamp."""
    user = await User.create(id=128)
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    assert await update_user_preference(user.id, "hide_ign", True)

    saved = await User.get(id=user.id)
    assert saved.hide_ign
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_select_account_updates_user_timestamp() -> None:
    """Verify that select account updates user timestamp."""
    user = await User.create(id=129)
    account = await Account.create(puuid="selected", user=user, username="One#NA")
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
    await User.filter(id=user.id).update(updated_at=old_timestamp)

    await select_account(user.id, account)

    saved = await User.get(id=user.id)
    assert saved.current_account_id == account.puuid
    assert saved.updated_at > old_timestamp


@pytest.mark.usefixtures("database")
async def test_user_preference_service_validates_and_updates_fields() -> None:
    """Verify that user preference service validates and updates fields."""
    user = await User.create(id=125)
    await User.create(id=126, daily_shop_enabled=True)

    assert await get_user(user.id) is not None
    assert await count_registered_users() == 2
    assert await daily_shop_user_ids() == {126}
    assert await update_user_preference(user.id, "hide_ign", True)
    assert (await get_user(user.id)).hide_ign is True
    assert not await update_user_preference(999, "hide_ign", True)
    with pytest.raises(ValueError, match="Unsupported user preference"):
        await update_user_preference(user.id, "auth_blob", True)


@pytest.mark.usefixtures("database")
async def test_selected_account_does_not_overwrite_concurrent_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that selected account does not overwrite concurrent selection."""
    user = await User.create(id=124)
    first = await Account.create(puuid="fallback-first", user=user, username="First#NA")
    second = await Account.create(
        puuid="fallback-second", user=user, username="Second#NA"
    )
    lookup_finished = asyncio.Event()
    continue_lookup = asyncio.Event()
    original_get_or_none = accounts_service.User.get_or_none
    lookup_count = 0

    async def paused_lookup(cls, *args, **kwargs):
        """Pause account selection until the test releases its synchronization gate."""
        nonlocal lookup_count
        result = await original_get_or_none(*args, **kwargs)
        lookup_count += 1
        if lookup_count == 1:
            lookup_finished.set()
            await continue_lookup.wait()
        return result

    monkeypatch.setattr(
        accounts_service.User, "get_or_none", classmethod(paused_lookup)
    )
    fallback = asyncio.create_task(selected_account(user.id))
    await asyncio.wait_for(lookup_finished.wait(), timeout=1)
    await select_account(user.id, second)
    continue_lookup.set()

    result = await asyncio.wait_for(fallback, timeout=1)
    saved = await User.get(id=user.id)
    assert result is not None and result.puuid == second.puuid
    assert saved.current_account_id == second.puuid
    assert first.puuid != second.puuid


@pytest.mark.usefixtures("database")
async def test_alert_unique_per_account_and_skin() -> None:
    """Verify that each account can have only one alert for a given skin."""
    user = await User.create(id=456)
    account = await Account.create(puuid="account", user=user, username="One#NA")
    skin = UUID("11111111-1111-1111-1111-111111111111")
    await Alert.create(account=account, skin_uuid=skin)
    with pytest.raises(IntegrityError):
        await Alert.create(account=account, skin_uuid=skin)


@pytest.mark.usefixtures("database")
async def test_command_analytics_keeps_dm_context_nullable() -> None:
    """Verify that command analytics keeps DM context nullable."""
    entry = await CommandInvocation.create(command="shop", user_id=789)
    assert (entry.command, entry.user_id, entry.guild_id, entry.channel_id) == (
        "shop",
        789,
        None,
        None,
    )


@pytest.mark.usefixtures("database")
async def test_delete_user_data_removes_personal_records() -> None:
    """Verify that delete user data removes personal records."""
    user = await User.create(id=901)
    account = await Account.create(puuid="delete-me", user=user, username="Delete#NA")
    await Alert.create(
        account=account, skin_uuid=UUID("11111111-1111-1111-1111-111111111111")
    )
    await CommandInvocation.create(command="shop", user_id=user.id)
    suggestion = await Suggestion.create(author_id=user.id, content="Remove me")
    await SuggestionFollower.create(suggestion=suggestion, user_id=user.id)

    assert await delete_user_data(user.id)
    assert not await User.exists(id=user.id)
    assert not await Account.exists(puuid=account.puuid)
    assert not await Alert.exists(account_id=account.puuid)
    assert not await CommandInvocation.exists(user_id=user.id)
    assert not await Suggestion.exists(author_id=user.id)
    assert not await SuggestionFollower.exists(user_id=user.id)


@pytest.mark.usefixtures("database")
async def test_suggestion_followers_are_unique_per_user() -> None:
    """Verify that suggestion followers are unique per user."""
    suggestion = await Suggestion.create(author_id=789, content="Add a feature")
    await SuggestionFollower.create(suggestion=suggestion, user_id=456)
    with pytest.raises(IntegrityError):
        await SuggestionFollower.create(suggestion=suggestion, user_id=456)


@pytest.mark.usefixtures("database")
async def test_shard_status_message_is_reused_per_channel() -> None:
    """Verify that shard status message is reused per channel."""
    message, created = await ShardStatusMessage.update_or_create(
        channel_id=123, defaults={"message_id": 456}
    )
    assert (message.message_id, created) == (456, True)
    message, created = await ShardStatusMessage.update_or_create(
        channel_id=123, defaults={"message_id": 789}
    )
    assert (message.message_id, created) == (789, False)


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


async def test_expired_shop_cache_entry_is_removed_when_auth_fails() -> None:
    """Verify that expired shop cache entry is removed when auth fails."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise AuthenticationRequired("Riot credentials are unavailable")

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="expired-shop-auth")
    service._cache[account.puuid] = ShopData([], [], [], int(time.time()) - 1, None)

    with pytest.raises(AuthenticationRequired):
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


@pytest.mark.usefixtures("database")
async def test_concurrent_auth_ensure_serializes_entitlement_repair() -> None:
    """Verify that concurrent auth ensure serializes entitlement repair."""
    user = await User.create(id=654)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-race",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class RejectingHTTP:
        """Reject entitlement requests to verify concurrent authentication checks serialize repair."""

        requests = 0

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            self.requests += 1
            return SimpleNamespace(status=400, data={"error": "invalid_grant"})

    http = RejectingHTTP()
    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        http,
        vault,
    )
    entitlement_started = asyncio.Event()
    release_entitlement = asyncio.Event()
    entitlement_calls = 0

    async def entitlement(_auth) -> str | None:
        """Return the configured fake entitlement response."""
        nonlocal entitlement_calls
        entitlement_calls += 1
        if entitlement_calls == 1:
            entitlement_started.set()
            await release_entitlement.wait()
            return "entitlement"
        return None

    service._entitlement = entitlement
    first = asyncio.create_task(service.ensure(account))
    await asyncio.wait_for(entitlement_started.wait(), timeout=1)
    second = asyncio.create_task(service.ensure(account))
    try:
        await asyncio.sleep(0.01)
    finally:
        release_entitlement.set()

    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )
    saved = await Account.get(puuid=account.puuid)
    assert first_result.success and second_result.success
    assert entitlement_calls == 1
    assert http.requests == 0
    assert vault.decrypt(saved.auth_blob)["ent"] == "entitlement"


@pytest.mark.usefixtures("database")
async def test_auth_refresh_transients_do_not_become_login_required() -> None:
    """Verify that auth refresh transients do not become login required."""
    user = await User.create(id=655)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-refresh-transient",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(expires_in=-1), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)

    saved = await Account.get(puuid=account.puuid)
    assert vault.decrypt(saved.auth_blob).get("refresh_token")


@pytest.mark.usefixtures("database")
async def test_entitlement_transients_do_not_become_login_required() -> None:
    """Verify that entitlement transients do not become login required."""
    user = await User.create(id=657)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-entitlement-transient",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)

    saved = await Account.get(puuid=account.puuid)
    assert "ent" not in vault.decrypt(saved.auth_blob)


@pytest.mark.parametrize("status", [408, 425, 500, 503])
@pytest.mark.usefixtures("database")
async def test_auth_refresh_transient_status_does_not_become_login_required(
    status,
) -> None:
    """Verify that auth refresh transient status does not become login required."""
    user = await User.create(id=658)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-refresh-http-error",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(expires_in=-1), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(status=status, data={})

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)


@pytest.mark.parametrize("status", [408, 425, 500, 503])
@pytest.mark.usefixtures("database")
async def test_entitlement_transient_status_does_not_become_login_required(
    status,
) -> None:
    """Verify that entitlement transient status does not become login required."""
    user = await User.create(id=659)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-entitlement-http-error",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(status=status, data={})

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)


async def test_shop_wallet_normalizes_transient_auth_failures() -> None:
    """Verify that shop wallet normalizes transient auth failures."""

    class FailingAuth:
        """Raise controlled credential errors so dependent services can classify login failures."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise HTTPFailure("transport unavailable")

    service = ShopService(SimpleNamespace(), None, FailingAuth(), None)

    with pytest.raises(ShopUnavailable):
        await service.wallet(SimpleNamespace(puuid="wallet-auth"))


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


async def test_gameplay_normalizes_transient_auth_failures() -> None:
    """Verify that gameplay normalizes transient auth failures."""

    class FailingAuth:
        """Raise controlled credential errors so dependent services can classify login failures."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise HTTPFailure("transport unavailable")

    service = GameplayService(None, FailingAuth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.battlepass(SimpleNamespace(puuid="gameplay", region="na"))


async def test_gameplay_normalizes_transient_http_failures() -> None:
    """Verify that gameplay normalizes transient HTTP failures."""

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

    service = GameplayService(FailingHTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.battlepass(SimpleNamespace(puuid="gameplay", region="na"))


async def test_gameplay_missions_join_contract_progress_with_catalog_metadata() -> None:
    """Verify that gameplay missions join contract progress with catalog metadata."""
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
                return SimpleNamespace(
                    status=200,
                    data={
                        "data": [
                            {
                                "uuid": "weekly-mission",
                                "title": "Kill players with headshots",
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

    missions = await service.missions(SimpleNamespace(puuid="player", region="na"))

    assert len(missions) == 1
    assert missions[0]["type"] == "Weekly Missions"
    assert missions[0]["title"] == "Kill players with headshots"
    assert missions[0]["xp"] == 20000
    assert missions[0]["tasks"] == [{"progress": 15, "target": 100}]
    assert missions[0]["expires"] == datetime(2026, 9, 28, tzinfo=UTC)
    assert sum("/contracts/v1/contracts/" in url for url in urls) == 1
    assert sum("/v1/missions?" in url for url in urls) == 1
    assert len(urls) == 2


async def test_gameplay_penalties_join_infractions_and_normalize_effects() -> None:
    """Verify penalties use the account shard and join Riot infraction metadata."""
    puuid = "2e2a6f06-0d0e-4b52-bf98-4d7b7ce9f5a4"
    infraction_id = "f5d4a5c9-5d4a-4ec6-bfe0-12b32cf08fe4"
    requests: list[tuple[str, str, dict[str, str]]] = []

    class Auth:
        """Return the authenticated headers expected by the Riot endpoint."""

        async def auth_headers(self, account) -> dict[str, str]:
            """Return test headers for the requested account."""
            assert account.puuid == puuid
            return {"Authorization": "Bearer token", "X-Riot-Entitlements-JWT": "ent"}

    class HTTP:
        """Return a representative Riot penalties response."""

        async def request(self, method, url, *, headers):
            """Record the request and return test penalty data."""
            requests.append((method, url, headers))
            return SimpleNamespace(
                status=200,
                data={
                    "Subject": puuid,
                    "Penalties": [
                        {
                            "InfractionID": infraction_id,
                            "Expiry": "2026-11-03T00:00:00.000Z",
                            "GamesRemaining": 2,
                            "ApplyToAllPlatforms": False,
                            "ApplyToPlatforms": ["PC"],
                            "ApplyToPlatformGroups": ["Competitive"],
                            "QueueRestrictionEffect": {"Duration": 300},
                            "RankedRatingPenaltyEffect": {"Amount": 5},
                            "WarningEffect": {
                                "WarningType": "QUEUE_DODGING",
                                "WarningTier": 2,
                            },
                        }
                    ],
                    "Infractions": [
                        {
                            "ID": infraction_id,
                            "Name": "Queue Dodging",
                            "RatingName": "Competitive restriction",
                        }
                    ],
                },
            )

    service = GameplayService(HTTP(), Auth(), None)

    penalties = await service.penalties(SimpleNamespace(puuid=puuid, region="br"))

    assert requests == [
        (
            "GET",
            "https://pd.na.a.pvp.net/restrictions/v3/penalties",
            {"Authorization": "Bearer token", "X-Riot-Entitlements-JWT": "ent"},
        )
    ]
    assert penalties == [
        {
            "infraction": "Queue Dodging",
            "expires": datetime(2026, 11, 3, tzinfo=UTC),
            "games_remaining": 2,
            "platform_scope": "PC, Competitive",
            "effects": ["queue-restriction", "ranked-rating-penalty", "warning"],
            "warning_type": "QUEUE_DODGING",
            "warning_tier": 2,
        }
    ]


async def test_gameplay_penalties_use_metadata_fallback_and_return_empty_list() -> None:
    """Verify missing infraction metadata falls back to its ID and empty data stays empty."""
    responses = [
        {
            "Subject": "player",
            "Penalties": [
                {"InfractionID": "rating-only"},
                {"InfractionID": "missing-metadata", "ApplyToAllPlatforms": True},
            ],
            "Infractions": [
                {"ID": "rating-only", "Name": None, "RatingName": "Rating fallback"}
            ],
        },
        {"Subject": "player", "Penalties": [], "Infractions": []},
    ]

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {"Authorization": "Bearer token"}

    class HTTP:
        """Return penalty responses in order."""

        async def request(self, *_args, **_kwargs):
            """Return the next configured response."""
            return SimpleNamespace(status=200, data=responses.pop(0))

    service = GameplayService(HTTP(), Auth(), None)
    account = SimpleNamespace(puuid="player", region="eu")

    penalties = await service.penalties(account)
    empty = await service.penalties(account)

    assert penalties[0]["infraction"] == "Rating fallback"
    assert penalties[1]["infraction"] == "missing-metadata"
    assert penalties[1]["platform_scope"] == "All platforms"
    assert empty == []


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status=503, data={}),
        SimpleNamespace(
            status=200, data={"Subject": "other", "Penalties": [], "Infractions": []}
        ),
        SimpleNamespace(
            status=200, data={"Subject": "player", "Penalties": {}, "Infractions": []}
        ),
        SimpleNamespace(
            status=200, data={"Subject": "player", "Penalties": [], "Infractions": None}
        ),
    ],
)
async def test_gameplay_penalties_reject_unusable_responses(response) -> None:
    """Verify penalties reject unsuccessful, cross-account, and malformed responses."""

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {}

    class HTTP:
        """Return the configured Riot response."""

        async def request(self, *_args, **_kwargs):
            """Return the configured response."""
            return response

    service = GameplayService(HTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.penalties(SimpleNamespace(puuid="player", region="eu"))


async def test_gameplay_penalties_normalize_transient_http_failures() -> None:
    """Verify the penalties service classifies HTTP transport failures."""

    class Auth:
        """Return usable credentials for service calls."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return test authorization headers."""
            return {}

    class HTTP:
        """Raise a controlled transport failure."""

        async def request(self, *_args, **_kwargs):
            """Raise a failure like the shared HTTP client does."""
            raise HTTPFailure("transport unavailable")

    service = GameplayService(HTTP(), Auth(), None)

    with pytest.raises(GameplayUnavailable):
        await service.penalties(SimpleNamespace(puuid="player", region="eu"))


@pytest.mark.usefixtures("database")
async def test_concurrent_login_callbacks_respect_account_limit() -> None:
    """Verify that concurrent login callbacks respect account limit."""
    discord_id = 656
    vault = AuthVault(Fernet.generate_key().decode())
    token_calls = 0
    detail_calls = 0
    first_token_started = asyncio.Event()
    both_tokens_started = asyncio.Event()
    all_details_started = asyncio.Event()
    nonces: dict[str, str] = {}

    class LoginHTTP:
        """Provide controlled OAuth responses for concurrent login and account-limit scenarios."""

        async def request(self, method, url, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            nonlocal token_calls, detail_calls
            if url.endswith("/token"):
                form = parse_qs(kwargs["data"])
                code = form["code"][0]
                token_calls += 1
                if token_calls == 1:
                    first_token_started.set()
                if token_calls == 2:
                    both_tokens_started.set()
                await both_tokens_started.wait()
                puuid = f"riot-{code}"
                return SimpleNamespace(
                    status=200,
                    data={
                        "access_token": _fake_jwt(
                            sub=puuid, exp=int(time.time()) + 3600
                        ),
                        "id_token": _fake_jwt(nonce=nonces[code]),
                    },
                )

            detail_calls += 1
            if detail_calls == 6:
                all_details_started.set()
            await all_details_started.wait()
            if url.endswith("/userinfo"):
                authorization = kwargs["headers"]["Authorization"]
                puuid = decode_jwt(authorization.removeprefix("Bearer "))["sub"]
                return SimpleNamespace(
                    status=200,
                    data={"acct": {"game_name": puuid, "tag_line": "NA"}},
                )
            if url.endswith("/api/token/v1"):
                return SimpleNamespace(
                    status=200, data={"entitlements_token": "entitlement"}
                )
            if url.endswith("/product/valorant"):
                return SimpleNamespace(status=200, data={"affinities": {"live": "na"}})
            raise AssertionError(f"Unexpected Riot URL: {url}")

    service = AuthService(SimpleNamespace(max_accounts_per_user=1), LoginHTTP(), vault)

    first_url = service.login_url(discord_id)
    nonces["first"] = parse_qs(urlparse(first_url).query)["nonce"][0]
    first = asyncio.create_task(
        service.redeem_callback(discord_id, "http://localhost/redirect?code=first")
    )
    await asyncio.wait_for(first_token_started.wait(), timeout=1)

    second_url = service.login_url(discord_id)
    nonces["second"] = parse_qs(urlparse(second_url).query)["nonce"][0]
    second = asyncio.create_task(
        service.redeem_callback(discord_id, "http://localhost/redirect?code=second")
    )
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=2
    )

    assert sorted((first_result.success, second_result.success)) == [False, True]
    assert "link at most 1 accounts" in (
        first_result.error or second_result.error or ""
    )
    assert await Account.filter(user_id=discord_id).count() == 1


@pytest.mark.usefixtures("database")
async def test_logout_clears_credentials_saved_during_refresh() -> None:
    """Verify that logout clears credentials saved during refresh."""
    user = await User.create(id=655)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="logout-race",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class RefreshHTTP:
        """Pause token refresh requests so logout can protect credentials updated concurrently."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(
                status=200, data={"access_token": _fake_access_token()}
            )

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        RefreshHTTP(),
        vault,
    )
    entitlement_started = asyncio.Event()
    release_entitlement = asyncio.Event()

    async def entitlement(_auth) -> str:
        """Return the configured fake entitlement response."""
        entitlement_started.set()
        await release_entitlement.wait()
        return "entitlement"

    service._entitlement = entitlement
    refreshing = asyncio.create_task(service.refresh(account, force=True))
    await asyncio.wait_for(entitlement_started.wait(), timeout=1)
    logout = asyncio.create_task(service.clear_credentials(account))
    await asyncio.sleep(0)
    release_entitlement.set()

    result = await asyncio.wait_for(refreshing, timeout=1)
    await asyncio.wait_for(logout, timeout=1)
    saved = await Account.get(puuid=account.puuid)
    assert result.success
    assert saved.auth_blob is None


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
    """Verify skin chromas survive catalog build, save, and load."""
    with tempfile.TemporaryDirectory(prefix=".catalog-test-", dir=Path.cwd()) as folder:
        path = Path(folder) / "skins.json"

        class CatalogHTTP:
            """Provide deterministic version, skin, and bundle responses."""

            async def request(self, _method: str, url: str):
                """Return the requested catalog fixture."""
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
                                    "displayName": "Test Bundle",
                                    "displayNameSubText": "Limited Edition",
                                    "description": "A test bundle",
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
                                        "displayName": "Skin",
                                        "assetPath": "ShooterGame/Content/Weapons/Skin",
                                        "levels": [
                                            {
                                                "uuid": "level",
                                                "streamedVideo": "https://example.com/level.mp4",
                                            }
                                        ],
                                        "chromas": [
                                            {
                                                "uuid": "chroma",
                                                "displayName": "Skin Green",
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

        skin = loaded.get_skin("skin")
        assert skin is not None
        assert skin.chromas == [
            {
                "uuid": "chroma",
                "displayName": "Skin Green",
                "streamedVideo": "https://example.com/chroma.mp4",
            }
        ]
        assert skin.levels[0]["streamedVideo"] == "https://example.com/level.mp4"
        bundle = loaded.get_bundle("bundle")
        assert bundle == Bundle(
            "bundle",
            "Test Bundle",
            "Limited Edition",
            "A test bundle",
            "https://example.com/bundle.png",
        )


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

    class HTTP:
        """Stub the shared Riot client so request handling and shutdown can be observed."""

        async def request(self, _method: str, _url: str):
            """Record request arguments and return the configured HTTP response."""
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return SimpleNamespace(
                status=200,
                data={
                    "data": [
                        {
                            "uuid": "buddy-base",
                            "displayName": "Buddy",
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
