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
        lock = self._locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[account_id] = lock
        return lock

    async def clear_cached_storefront(self, account_id: str) -> None:
        """Remove an account's cached storefront after coordinating with active fetches."""
        async with self._account_lock(account_id):
            self._cache.pop(account_id, None)

    async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData:
        """Return a fresh or unexpired cached storefront for the linked account."""
        async with self._account_lock(account.puuid):
            cached = self._cache.get(account.puuid)
            if cached and getattr(cached, "cache_expires", None) is not None:
                expired = cached.cache_expires <= time.time()
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
            if not repaired.success:
                raise AuthenticationRequired("Riot rejected the stored credentials")
            account = await Account.get(puuid=account.puuid)
            headers = await self.auth.auth_headers(account)
            response = await self._storefront_request(account, headers)
            raw = response.data if isinstance(response.data, dict) else {}
            if response.status in {400, 401} and raw.get("errorCode") == "BAD_CLAIMS":
                raise AuthenticationRequired("Riot rejected the stored credentials")

        if response.status != 200 or not raw.get("SkinsPanelLayout"):
            if raw.get("errorCode") == "SCHEDULED_DOWNTIME":
                raise ShopUnavailable("VALORANT is undergoing scheduled maintenance")
            raise ShopUnavailable("Riot returned an invalid storefront response")
        now = int(time.time())
        panel = raw["SkinsPanelLayout"]
        expires = now + int(panel.get("SingleItemOffersRemainingDurationInSeconds", 0))
        offer_ids = panel.get("SingleItemOffers") or []
        prices = self._offer_prices(raw)
        offers = [
            Offer(skin, prices.get(str(offer_id), skin.price or 0), expires)
            for offer_id in offer_ids
            if (skin := self.catalog.get_skin(str(offer_id)))
        ]
        night_raw = (raw.get("BonusStore") or {}).get("BonusStoreOffers") or []
        night_expires = (
            now
            + int(
                (raw.get("BonusStore") or {}).get(
                    "BonusStoreRemainingDurationInSeconds", 0
                )
            )
            if raw.get("BonusStore")
            else None
        )
        night_market: list[Offer] = []
        for entry in night_raw:
            offer = entry.get("Offer") or {}
            skin = self.catalog.get_skin(str(offer.get("OfferID") or ""))
            if skin:
                night_market.append(
                    Offer(
                        skin,
                        int((offer.get("Cost") or {}).get(VP_UUID, 0)),
                        night_expires or expires,
                        int((entry.get("DiscountCosts") or {}).get(VP_UUID, 0)),
                        int(entry.get("DiscountPercent", 0)),
                    )
                )
        featured = raw.get("FeaturedBundle")
        featured = featured if isinstance(featured, dict) else {}
        bundle_remaining = _nonnegative_int(
            featured.get("BundlesRemainingDurationInSeconds")
        )
        bundle_expiry = now + bundle_remaining if bundle_remaining is not None else None
        featured_bundles: list[FeaturedBundle] = []
        for entry in featured.get("Bundles") or []:
            if not isinstance(entry, dict):
                continue
            bundle_id = str(entry.get("ID") or entry.get("DataAssetID") or "")
            data_asset_id = str(entry.get("DataAssetID") or bundle_id)
            if not bundle_id:
                continue
            currency_uuid = str(entry.get("CurrencyID") or VP_UUID)
            duration = _nonnegative_int(entry.get("DurationRemainingInSeconds"))
            expiry_candidates = [
                expiry
                for expiry in (
                    bundle_expiry,
                    now + duration if duration is not None else None,
                )
                if expiry is not None
            ]
            items: list[FeaturedBundleItem] = []
            for raw_item in entry.get("Items") or []:
                if not isinstance(raw_item, dict):
                    continue
                item = raw_item.get("Item") or {}
                if not isinstance(item, dict):
                    continue
                item_type_id = str(item.get("ItemTypeID") or "")
                item_id = str(item.get("ItemID") or "")
                if not item_type_id or not item_id:
                    continue
                item_currency = str(raw_item.get("CurrencyID") or currency_uuid)
                items.append(
                    FeaturedBundleItem(
                        item_type_id=item_type_id,
                        item_id=item_id,
                        amount=_positive_int(
                            raw_item.get("Quantity")
                            or raw_item.get("BundleItemQty")
                            or item.get("Amount")
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
                    total_discount_percent=_nonnegative_int(
                        entry.get("TotalDiscountPercent")
                    ),
                    expires=min(expiry_candidates) if expiry_candidates else None,
                )
            )
        cache_expiries = [expires]
        cache_expiries.extend(
            offer.expires for offer in featured_bundles if offer.expires is not None
        )
        data = ShopData(
            offers=offers,
            accessory=(raw.get("AccessoryStore") or {}).get("AccessoryStoreOffers")
            or [],
            night_market=night_market,
            expires=expires,
            night_market_expires=night_expires,
            featured_bundles=featured_bundles,
            cache_expires=min(cache_expiries),
        )
        self.catalog.update_prices(self._raw_offers(raw))
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
        balances = response.data.get("Balances") or {}
        return {
            "vp": int(balances.get(VP_UUID, 0)),
            "rp": int(balances.get(RP_UUID, 0)),
            "kc": int(balances.get(KC_UUID, 0)),
        }

    async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]:
        """Resolve the storefront's accessory rewards and their Kingdom Credit prices."""
        offers = []
        for entry in data.accessory:
            offer = entry.get("Offer") or {}
            price = int((offer.get("Cost") or {}).get(KC_UUID, 0))
            for reward in offer.get("Rewards") or []:
                item = await self.catalog.accessory(
                    str(reward.get("ItemTypeID") or ""),
                    str(reward.get("ItemID") or ""),
                )
                if item:
                    offers.append(AccessoryOffer(item, price))
        return offers

    @staticmethod
    def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the raw single-item store offers across Riot response shapes."""
        panel = raw.get("SkinsPanelLayout") or {}
        return (
            panel.get("SingleItemStoreOffers") or raw.get("SingleItemStoreOffers") or []
        )

    def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]:
        """Build a skin-offer-to-VP-price lookup from the storefront payload."""
        prices: dict[str, int] = {}
        for entry in self._raw_offers(raw):
            offer = (
                entry.get("Offer") if isinstance(entry.get("Offer"), dict) else entry
            )
            identifier = str(offer.get("OfferID") or "")
            cost = offer.get("Cost") or {}
            if identifier and cost:
                prices[identifier] = int(
                    cost.get(VP_UUID, next(iter(cost.values()), 0))
                )
        return prices


class ShopUnavailable(RuntimeError):
    """Raised when Riot does not return a usable storefront or wallet."""


def _positive_int(value: Any) -> int | None:
    """Parse a positive storefront number without rejecting the whole payload."""
    try:
        result = int(value)
    except TypeError, ValueError:
        return None
    return result if result > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    """Parse a duration where zero means that the offer has already expired."""
    try:
        result = int(value)
    except TypeError, ValueError:
        return None
    return result if result >= 0 else None


def _vp_price(value: Any, currency_uuid: str) -> int | None:
    """Return a price only when the source entry explicitly uses VALORANT Points."""
    if currency_uuid != VP_UUID:
        return None
    if isinstance(value, dict):
        value = value.get(VP_UUID)
    try:
        result = int(value)
    except TypeError, ValueError:
        return None
    return result if result >= 0 else None
