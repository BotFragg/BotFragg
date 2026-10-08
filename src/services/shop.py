"""Normalize authenticated VALORANT shop, featured bundle, and wallet data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakValueDictionary

from ..config import Settings
from ..models import Account
from .auth import AuthenticationRequired, AuthService, riot_region
from .catalog import Accessory, CatalogService, Skin
from .http import HTTPClient, HTTPFailure, HTTPResult

VP_UUID = "85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"
RP_UUID = "e59aa87c-4cbf-517a-5983-6e81511be9b7"
KC_UUID = "85ca954a-41f2-ce94-9b45-8ca3dd39a00d"


@dataclass(slots=True)
class Offer:
    """Represent a skin offer with its standard price and optional discount."""

    skin: Skin
    price: int
    expires: int
    discount_price: int | None = None
    discount_percent: int | None = None


@dataclass(slots=True)
class AccessoryOffer:
    """Represent one accessory and its Kingdom Credit price."""

    item: Accessory
    price: int


@dataclass(slots=True)
class FeaturedBundleItem:
    """Represent one account-specific item and its exact bundle offer pricing."""

    item_type_id: str
    item_id: str
    amount: int
    base_price: int | None
    discounted_price: int | None


@dataclass(slots=True)
class FeaturedBundle:
    """Represent one currently featured bundle from an account's storefront."""

    id: str
    data_asset_id: str
    items: list[FeaturedBundleItem]
    total_base_cost: int | None
    total_discounted_cost: int | None
    total_discount_percent: int | None
    expires: int | None


@dataclass(slots=True)
class ShopData:
    """Hold account-specific shop offers and separate display/cache expiries."""

    offers: list[Offer]
    accessory: list[dict[str, Any]]
    night_market: list[Offer]
    expires: int
    night_market_expires: int | None
    featured_bundles: list[FeaturedBundle] = field(default_factory=list)
    cache_expires: int | None = None


class ShopService:
    """Retrieve and normalize Riot storefronts and wallet balances."""

    def __init__(
        self,
        config: Settings,
        http: HTTPClient,
        auth: AuthService,
        catalog: CatalogService,
    ) -> None:
        """Bind dependencies and initialize storefront data and per-account locks."""
        self.config = config
        self.http = http
        self.auth = auth
        self.catalog = catalog
        self._cache: dict[str, ShopData] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _account_lock(self, account_id: str) -> asyncio.Lock:
        """Return the shared in-process lock used for one account's shop requests."""
        return self._locks.setdefault(account_id, asyncio.Lock())

    async def clear_cached_storefront(self, account_id: str) -> None:
        """Remove an account's cached storefront after coordinating with active fetches."""
        async with self._account_lock(account_id):
            self._cache.pop(account_id, None)

    def prune_expired(self) -> None:
        """Release expired storefronts, including accounts no longer queried."""
        now = time.time()
        self._cache = {
            key: data
            for key, data in self._cache.items()
            if (data.cache_expires if data.cache_expires is not None else data.expires)
            > now
        }

    async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData:
        """Return a fresh or unexpired cached storefront for the linked account."""
        async with self._account_lock(account.puuid):
            cached = self._cache.get(account.puuid)
            cache_expires = getattr(cached, "cache_expires", None)
            if cached and cache_expires is not None:
                expired = cache_expires <= time.time()
            else:
                expired = bool(cached and cached.expires <= time.time())
            if cached and expired:
                self._cache.pop(account.puuid, None)
                cached = None
            try:
                headers = await self.auth.auth_headers(account)
                if use_cache and self.config.use_shop_cache and cached:
                    return cached
                return await self._fetch_storefront(account, headers)
            except HTTPFailure as exc:
                raise ShopUnavailable(str(exc)) from exc

    async def _fetch_storefront(
        self, account: Account, headers: dict[str, str]
    ) -> ShopData:
        """Fetch, repair claims, normalize all shop offers, and cache the result."""
        response = await self._storefront_request(account, headers)
        raw = response.data if isinstance(response.data, dict) else {}
        if response.status in {400, 401} and raw.get("errorCode") == "BAD_CLAIMS":
            repaired = await self.auth.ensure(account, force=True)
            if not repaired.success or not repaired.account:
                raise AuthenticationRequired("Riot rejected the stored credentials")
            account = repaired.account
            headers = await self.auth.auth_headers(account)
            response = await self._storefront_request(account, headers)
            raw = response.data if isinstance(response.data, dict) else {}
            if response.status in {400, 401} and raw.get("errorCode") == "BAD_CLAIMS":
                raise AuthenticationRequired("Riot rejected the stored credentials")

        panel = _mapping(raw.get("SkinsPanelLayout"))
        if response.status != 200 or not panel:
            if raw.get("errorCode") == "SCHEDULED_DOWNTIME":
                raise ShopUnavailable("VALORANT is undergoing scheduled maintenance")
            raise ShopUnavailable("Riot returned an invalid storefront response")
        now = int(time.time())
        duration = _int_at_least(
            panel.get("SingleItemOffersRemainingDurationInSeconds"), 0
        )
        if duration is None:
            raise ShopUnavailable("Riot returned an invalid storefront duration")
        expires = now + duration
        offer_ids = panel.get("SingleItemOffers")
        if offer_ids is None:
            offer_ids = []
        if not isinstance(offer_ids, list):
            raise ShopUnavailable("Riot returned invalid daily offers")
        prices = self._offer_prices(raw)
        offers = [
            Offer(skin, prices.get(str(offer_id), skin.price or 0), expires)
            for offer_id in offer_ids
            if (skin := self.catalog.get_skin(str(offer_id)))
        ]
        bonus = _mapping(raw.get("BonusStore"))
        night_duration = _int_at_least(
            bonus.get("BonusStoreRemainingDurationInSeconds"), 0
        )
        night_expires = now + night_duration if night_duration is not None else None
        night_market: list[Offer] = []
        for entry in _rows(bonus.get("BonusStoreOffers")):
            offer = _mapping(entry.get("Offer"))
            skin = self.catalog.get_skin(str(offer.get("OfferID") or ""))
            price = _vp_price(offer.get("Cost"), VP_UUID)
            discounted = _vp_price(entry.get("DiscountCosts"), VP_UUID)
            percent = _int_at_least(entry.get("DiscountPercent", 0), 0)
            if (
                skin
                and price is not None
                and discounted is not None
                and percent is not None
                and percent <= 100
            ):
                night_market.append(
                    Offer(
                        skin,
                        price,
                        night_expires or expires,
                        discounted,
                        percent,
                    )
                )
        featured = _mapping(raw.get("FeaturedBundle"))
        bundle_remaining = _int_at_least(
            featured.get("BundlesRemainingDurationInSeconds"), 0
        )
        bundle_expiry = now + bundle_remaining if bundle_remaining is not None else None
        featured_bundles: list[FeaturedBundle] = []
        for entry in _rows(featured.get("Bundles")):
            bundle_id = str(entry.get("ID") or entry.get("DataAssetID") or "")
            data_asset_id = str(entry.get("DataAssetID") or bundle_id)
            if not bundle_id:
                continue
            currency_uuid = str(entry.get("CurrencyID") or VP_UUID)
            duration = _int_at_least(entry.get("DurationRemainingInSeconds"), 0)
            expiry_candidates = [
                expiry
                for expiry in (
                    bundle_expiry,
                    now + duration if duration is not None else None,
                )
                if expiry is not None
            ]
            items: list[FeaturedBundleItem] = []
            for raw_item in _rows(entry.get("Items")):
                item = _mapping(raw_item.get("Item"))
                item_type_id = str(item.get("ItemTypeID") or "")
                item_id = str(item.get("ItemID") or "")
                if not item_type_id or not item_id:
                    continue
                item_currency = str(raw_item.get("CurrencyID") or currency_uuid)
                items.append(
                    FeaturedBundleItem(
                        item_type_id=item_type_id,
                        item_id=item_id,
                        amount=_int_at_least(
                            raw_item.get("Quantity")
                            or raw_item.get("BundleItemQty")
                            or item.get("Amount"),
                            1,
                        )
                        or 1,
                        base_price=_vp_price(raw_item.get("BasePrice"), item_currency),
                        discounted_price=_vp_price(
                            raw_item.get("DiscountedPrice"), item_currency
                        ),
                    )
                )
            featured_bundles.append(
                FeaturedBundle(
                    id=bundle_id,
                    data_asset_id=data_asset_id,
                    items=items,
                    total_base_cost=_vp_price(
                        entry.get("TotalBaseCost"), currency_uuid
                    ),
                    total_discounted_cost=_vp_price(
                        entry.get("TotalDiscountedCost"), currency_uuid
                    ),
                    total_discount_percent=_int_at_least(
                        entry.get("TotalDiscountPercent"), 0
                    ),
                    expires=min(expiry_candidates) if expiry_candidates else None,
                )
            )
        cache_expiries = [expires]
        if night_expires is not None:
            cache_expiries.append(night_expires)
        cache_expiries.extend(
            offer.expires for offer in featured_bundles if offer.expires is not None
        )
        data = ShopData(
            offers=offers,
            accessory=_rows(
                _mapping(raw.get("AccessoryStore")).get("AccessoryStoreOffers")
            ),
            night_market=night_market,
            expires=expires,
            night_market_expires=night_expires,
            featured_bundles=featured_bundles,
            cache_expires=min(cache_expiries),
        )
        self.catalog.update_prices(prices)
        if self.config.use_shop_cache:
            self._cache[account.puuid] = data
        return data

    async def _storefront_request(
        self, account: Account, headers: dict[str, str]
    ) -> HTTPResult:
        """Request one account's regional storefront."""
        return await self.http.request(
            "POST",
            f"https://pd.{riot_region(account.region)}.a.pvp.net/store/v3/storefront/{account.puuid}",
            headers=headers,
            json={},
        )

    async def wallet(self, account: Account) -> dict[str, int]:
        """Return VP, Radianite, and Kingdom Credit balances for an account."""
        try:
            headers = await self.auth.auth_headers(account)
            response = await self.http.request(
                "GET",
                f"https://pd.{riot_region(account.region)}.a.pvp.net/store/v1/wallet/{account.puuid}",
                headers=headers,
            )
        except HTTPFailure as exc:
            raise ShopUnavailable(str(exc)) from exc
        if response.status != 200 or not isinstance(response.data, dict):
            raise ShopUnavailable("Could not fetch the wallet")
        balances = response.data.get("Balances")
        if not isinstance(balances, dict):
            raise ShopUnavailable("Riot returned invalid wallet balances")
        values: dict[str, int] = {}
        for name, currency in (("vp", VP_UUID), ("rp", RP_UUID), ("kc", KC_UUID)):
            value = _int_at_least(balances.get(currency, 0), 0)
            if value is None:
                raise ShopUnavailable("Riot returned invalid wallet balances")
            values[name] = value
        return values

    async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]:
        """Resolve the storefront's accessory rewards and their Kingdom Credit prices."""
        offers = []
        for entry in _rows(data.accessory):
            offer = _mapping(entry.get("Offer"))
            price = _int_at_least(_mapping(offer.get("Cost")).get(KC_UUID), 0)
            if price is None:
                continue
            for reward in _rows(offer.get("Rewards")):
                item_type = reward.get("ItemTypeID")
                item_id = reward.get("ItemID")
                if (
                    not isinstance(item_type, str)
                    or not item_type
                    or not isinstance(item_id, str)
                    or not item_id
                ):
                    continue
                item = await self.catalog.accessory(
                    item_type,
                    item_id,
                )
                if item:
                    offers.append(AccessoryOffer(item, price))
        return offers

    @staticmethod
    def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the raw single-item store offers across Riot response shapes."""
        panel = _mapping(raw.get("SkinsPanelLayout"))
        return _rows(
            panel.get("SingleItemStoreOffers") or raw.get("SingleItemStoreOffers") or []
        )

    def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]:
        """Build a skin-offer-to-VP-price lookup from the storefront payload."""
        prices: dict[str, int] = {}
        for entry in self._raw_offers(raw):
            nested = entry.get("Offer")
            offer = nested if isinstance(nested, dict) else entry
            identifier = str(offer.get("OfferID") or "")
            cost = _mapping(offer.get("Cost"))
            if identifier and cost:
                price = _int_at_least(
                    cost.get(VP_UUID, next(iter(cost.values()), 0)), 0
                )
                if price is not None:
                    prices[identifier] = price
        return prices


class ShopUnavailable(RuntimeError):
    """Raised when Riot does not return a usable storefront or wallet."""


def _int_at_least(value: Any, minimum: int) -> int | None:
    """Parse an integer only when it meets the requested minimum."""
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except TypeError, ValueError, OverflowError:
        return None
    return result if result >= minimum else None


def _mapping(value: Any) -> dict[str, Any]:
    """Treat malformed optional mappings as absent."""
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    """Keep only mapping entries from an optional Riot list."""
    return (
        [row for row in value if isinstance(row, dict)]
        if isinstance(value, list)
        else []
    )


def _vp_price(value: Any, currency_uuid: str) -> int | None:
    """Return a price only when the source entry explicitly uses VALORANT Points."""
    if currency_uuid != VP_UUID:
        return None
    if isinstance(value, dict):
        value = value.get(VP_UUID)
    return _int_at_least(value, 0)
